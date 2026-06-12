"""Tests for the calibration resolution ladder (Phase 4, Chunk 16).

Chunk 16 plumbs the resolution-ladder helpers into both
:class:`XRMMapH5Reader` and :class:`GenericHDF5MapReader`. Behaviour
in legacy mode is byte-identical to pre-Chunk-16; the only addition
is per-value provenance on ``payload.resolved_calibration`` and two
new info diagnostics (``calibration_resolved_from_preset``,
``calibration_resolved_from_metadata``, plus
``calibration_inferred`` and ``calibration_unresolved_strict_failure``
declared for later wiring).

The 2026-06-12 metadata audit on the inherited APS 13-ID-E dataset
(``melts/data/metadata_audit_report.md``) confirms that integer ROI
limits at ``/xrmmap/config/rois/limits`` are channel indices and the
historic ``roi_limit_scale=0.01`` matches ``mca_calib/slope`` — so
the Chunk-16 ROI-unit inference returns ``"channel_index"`` (with
provenance ``INFERRED``), not the misleading ``"centi_keV"`` that an
earlier helper draft used.
"""

from __future__ import annotations

import pytest

from axiomm.io.converters import (
    CalibrationSource,
    CalibrationUnresolvedError,
    ConversionMode,
    GenericHDF5MapReader,
    HDF5MapConfig,
    XRMMAP_H5_SCHEMA,
    XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1,
    XRMMapH5Calibration,
    XRMMapH5Reader,
)
from axiomm.io.converters.readers.hdf5_helpers import (
    resolve_energy_scale,
    resolve_navigation_scale_calibration,
    resolve_roi_limit_interpretation,
)


# ---------------------------------------------------------------------------
# Module-level helpers — tested directly per the modularity rule
# ---------------------------------------------------------------------------

def test_resolve_energy_scale_marks_user_config_when_user_value_set():
    rv = resolve_energy_scale(
        user_value=0.005, preset_value=0.01, mode=ConversionMode.LEGACY,
    )
    assert rv.value == pytest.approx(0.005)
    assert rv.source is CalibrationSource.USER_CONFIG


def test_resolve_energy_scale_falls_back_to_preset_in_legacy_mode():
    rv = resolve_energy_scale(
        user_value=None, preset_value=40.96 / 4096,
        mode=ConversionMode.LEGACY,
    )
    assert rv.value == pytest.approx(0.01)
    assert rv.source is CalibrationSource.LEGACY_PRESET


def test_resolve_energy_scale_marks_unknown_in_strict_mode():
    rv = resolve_energy_scale(
        user_value=None, preset_value=0.01, mode=ConversionMode.STRICT,
    )
    assert rv.value is None
    assert rv.source is CalibrationSource.UNKNOWN


def test_resolve_energy_scale_user_wins_over_preset_even_in_strict():
    rv = resolve_energy_scale(
        user_value=0.005, preset_value=0.01, mode=ConversionMode.STRICT,
    )
    assert rv.value == pytest.approx(0.005)
    assert rv.source is CalibrationSource.USER_CONFIG


def test_resolve_roi_limit_interpretation_infers_channel_index_for_0_01():
    """Audit-supported interpretation: 0.01 multiplier on integer
    /xrmmap/config/rois/limits is a channel→keV conversion using
    the same slope as mca_calib, not a centi-keV unit scaling."""
    rv = resolve_roi_limit_interpretation(
        user_value=None, preset_value=0.01, mode=ConversionMode.LEGACY,
    )
    assert rv.value == "channel_index"
    assert rv.source is CalibrationSource.INFERRED


def test_resolve_roi_limit_interpretation_marks_unknown_for_unfamiliar_scale():
    rv = resolve_roi_limit_interpretation(
        user_value=None, preset_value=1.5, mode=ConversionMode.LEGACY,
    )
    assert rv.value == "unknown"
    assert rv.source is CalibrationSource.INFERRED


def test_resolve_roi_limit_interpretation_returns_unknown_in_strict_mode():
    """Strict mode refuses inference."""
    rv = resolve_roi_limit_interpretation(
        user_value=None, preset_value=0.01, mode=ConversionMode.STRICT,
    )
    assert rv.value == "unknown"
    assert rv.source is CalibrationSource.UNKNOWN


def test_resolve_navigation_scale_marks_source_metadata_when_environ_has_beam_size():
    rv, _ = resolve_navigation_scale_calibration(
        {"Experiment.Beam_Size__Nominal": "2 um"},
        beam_size_key="Experiment.Beam_Size__Nominal",
        user_fallback_um=None,
        preset_fallback_um=500.0,
        xdim=10,
        mode=ConversionMode.LEGACY,
    )
    assert rv.value == pytest.approx(2.0)
    assert rv.source is CalibrationSource.SOURCE_METADATA


def test_resolve_navigation_scale_marks_legacy_preset_when_fallback_applies():
    rv, _ = resolve_navigation_scale_calibration(
        {},  # no environ → fallback path
        beam_size_key="Experiment.Beam_Size__Nominal",
        user_fallback_um=None,
        preset_fallback_um=500.0,
        xdim=10,
        mode=ConversionMode.LEGACY,
    )
    assert rv.value == pytest.approx(50.0)
    assert rv.source is CalibrationSource.LEGACY_PRESET


def test_resolve_navigation_scale_marks_user_config_when_user_fallback_used():
    rv, _ = resolve_navigation_scale_calibration(
        {},
        beam_size_key="Experiment.Beam_Size__Nominal",
        user_fallback_um=300.0,
        preset_fallback_um=500.0,
        xdim=10,
        mode=ConversionMode.LEGACY,
    )
    assert rv.value == pytest.approx(30.0)
    assert rv.source is CalibrationSource.USER_CONFIG


def test_resolve_navigation_scale_marks_unknown_when_no_fallback():
    rv, _ = resolve_navigation_scale_calibration(
        {},
        beam_size_key="Experiment.Beam_Size__Nominal",
        user_fallback_um=None,
        preset_fallback_um=None,
        xdim=10,
        mode=ConversionMode.LEGACY,
    )
    assert rv.value == 1.0
    assert rv.source is CalibrationSource.UNKNOWN


def test_resolve_navigation_scale_skips_preset_in_strict_mode():
    """Strict mode never falls back to preset; UNKNOWN even when preset set."""
    rv, _ = resolve_navigation_scale_calibration(
        {},
        beam_size_key="Experiment.Beam_Size__Nominal",
        user_fallback_um=None,
        preset_fallback_um=500.0,
        xdim=10,
        mode=ConversionMode.STRICT,
    )
    assert rv.source is CalibrationSource.UNKNOWN


# ---------------------------------------------------------------------------
# XRMMapH5Reader — mode parameter + resolved_calibration on payload
# ---------------------------------------------------------------------------

def test_xrmmap_reader_default_mode_is_legacy():
    reader = XRMMapH5Reader()
    assert reader.mode is ConversionMode.LEGACY


def test_xrmmap_reader_accepts_mode_kw_only():
    reader = XRMMapH5Reader(mode=ConversionMode.STRICT)
    assert reader.mode is ConversionMode.STRICT


def test_xrmmap_reader_attaches_resolved_calibration(synthetic_xrmmap_h5):
    """All three calibration entries land on the payload with the
    expected provenance — legacy-mode defaults applied."""
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    rc = payload.resolved_calibration
    assert set(rc) == {"energy_scale", "navigation_scale", "roi_limit_units"}
    assert rc["energy_scale"].source is CalibrationSource.LEGACY_PRESET
    # Synthetic fixture's environ table has Experiment.Beam_Size__Nominal,
    # so the navigation scale comes from source metadata.
    assert rc["navigation_scale"].source is CalibrationSource.SOURCE_METADATA
    assert rc["roi_limit_units"].source is CalibrationSource.INFERRED
    assert rc["roi_limit_units"].value == "channel_index"


def test_xrmmap_reader_user_calibration_overrides_preset(synthetic_xrmmap_h5):
    """Explicit XRMMapH5Calibration values are stamped USER_CONFIG and
    take priority over the legacy preset."""
    reader = XRMMapH5Reader(
        calibration=XRMMapH5Calibration(energy_scale=0.005),
    )
    payload = reader.read(synthetic_xrmmap_h5("user_cal.h5"))
    rc = payload.resolved_calibration
    assert rc["energy_scale"].source is CalibrationSource.USER_CONFIG
    assert rc["energy_scale"].value == pytest.approx(0.005)


def test_xrmmap_reader_emits_preset_and_inferred_diagnostics(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    codes = {d.code for d in payload.diagnostics}
    assert "calibration_resolved_from_preset" in codes
    assert "calibration_resolved_from_metadata" in codes
    assert "calibration_inferred" in codes


def test_xrmmap_reader_marks_navigation_legacy_preset_when_environ_missing(
    synthetic_xrmmap_h5,
):
    """Without the environ table, navigation scale falls back to the
    legacy preset's fallback_field_width_um (500 µm / xdim)."""
    path = synthetic_xrmmap_h5("noenv.h5", include_environ=False)
    payload = XRMMapH5Reader().read(path)
    rc = payload.resolved_calibration
    assert rc["navigation_scale"].source is CalibrationSource.LEGACY_PRESET


def test_xrmmap_reader_resolved_calibration_propagates_to_manifest(
    synthetic_xrmmap_h5, tmp_path,
):
    """The new resolved_calibration must flow into the manifest sidecar
    via the additive "calibration" subkey added in Chunk 15."""
    from axiomm.io.converters.writers.manifest import build_manifest_dict
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    manifest = build_manifest_dict(
        input_path=tmp_path / "in.h5",
        output_path=tmp_path / "out.hspy",
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    cal = manifest["axiomm_metadata"]["calibration"]
    assert set(cal) == {"energy_scale", "navigation_scale", "roi_limit_units"}
    assert cal["energy_scale"]["source"] == "legacy_preset"
    assert cal["roi_limit_units"]["source"] == "inferred"


# ---------------------------------------------------------------------------
# GenericHDF5MapReader — same shape of plumbing
# ---------------------------------------------------------------------------

def test_generic_reader_default_mode_is_legacy():
    reader = GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA)
    assert reader.mode is ConversionMode.LEGACY


def test_generic_reader_accepts_mode_kw_only():
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA, mode=ConversionMode.DIAGNOSTIC,
    )
    assert reader.mode is ConversionMode.DIAGNOSTIC


def test_generic_reader_attaches_resolved_calibration(synthetic_xrmmap_h5):
    """Generic reader configured with the XRM-Map schema treats every
    explicitly-passed HDF5MapConfig field as USER_CONFIG (the generic
    reader has no named preset of its own — Chunk 17 design)."""
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        config=HDF5MapConfig(
            energy_scale=0.01,
            roi_limit_scale=0.01,
            fallback_field_width_um=500.0,
        ),
    )
    payload = reader.read(synthetic_xrmmap_h5("ok.h5"))
    rc = payload.resolved_calibration
    assert set(rc) == {"energy_scale", "navigation_scale", "roi_limit_units"}
    assert rc["energy_scale"].source is CalibrationSource.USER_CONFIG
    assert rc["roi_limit_units"].source is CalibrationSource.INFERRED
    assert rc["roi_limit_units"].value == "channel_index"


def test_generic_reader_strict_mode_marks_roi_units_unknown(synthetic_xrmmap_h5):
    """Strict mode short-circuits the channel-index inference and
    marks roi_limit_units UNKNOWN — the Chunk-17 raise of
    CalibrationUnresolvedError is not wired yet."""
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        config=HDF5MapConfig(roi_limit_scale=0.01),
        mode=ConversionMode.STRICT,
    )
    payload = reader.read(synthetic_xrmmap_h5("ok.h5"))
    assert payload.resolved_calibration["roi_limit_units"].source is (
        CalibrationSource.UNKNOWN
    )


# ---------------------------------------------------------------------------
# CalibrationUnresolvedError — declared but not yet raised
# ---------------------------------------------------------------------------

def test_calibration_unresolved_error_is_in_public_api():
    """Exception is exposed at the package top-level so Chunk-17 code
    and external callers can both reference the same class."""
    assert issubclass(CalibrationUnresolvedError, Exception)


def test_calibration_unresolved_error_inherits_axiomm_base():
    from axiomm.io.converters import AxiommConverterError
    assert issubclass(CalibrationUnresolvedError, AxiommConverterError)
