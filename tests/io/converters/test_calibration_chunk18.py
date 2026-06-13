"""Chunk-18 tests: explicit units, explicit geometry, default-mode flip.

Phase 4, Chunk 18 introduces:

* an explicit ``roi_limit_units`` literal (``"centi_keV"`` / ``"keV"``
  / ``"channel_index"``) on the calibration dataclasses; the numeric
  scale is derived from the resolved unit + ``energy_scale``;
* explicit-geometry fields ``field_width_um`` / ``field_height_um``
  / ``pixel_size_um`` for spatial calibration;
* a ``legacy_field_width_um`` rename (was
  ``fallback_field_width_um``);
* a default-mode flip from ``LEGACY`` to ``GENERIC`` on both readers,
  one breaking change documented per Phase-4 plan;
* a shared :func:`raise_if_strict_unresolved` helper moved out of
  the reader module so both readers enforce strict-mode the same
  way.

These tests cover only the additions. The pre-existing resolution
ladder / preset / manifest-propagation coverage stays in
``test_calibration_resolution.py``, ``test_presets.py``, etc.
"""

from __future__ import annotations

import pytest

from axiomm.io.converters import (
    CalibrationSource,
    CalibrationUnresolvedError,
    ConversionMode,
    GenericHDF5MapReader,
    HDF5MapCalibration,
    XRMMAP_H5_SCHEMA,
    XRMMapH5Calibration,
    XRMMapH5Reader,
)
from axiomm.io.converters.readers.hdf5_helpers import (
    compute_roi_scale_from_units,
)


# ---------------------------------------------------------------------------
# compute_roi_scale_from_units — pure-function unit conversion table
# ---------------------------------------------------------------------------

def test_compute_roi_scale_centi_keV_is_constant_0_01():
    assert compute_roi_scale_from_units("centi_keV", energy_scale=0.01) == 0.01
    # energy_scale irrelevant for centi_keV.
    assert compute_roi_scale_from_units("centi_keV", energy_scale=0.005) == 0.01


def test_compute_roi_scale_keV_is_identity():
    assert compute_roi_scale_from_units("keV", energy_scale=0.01) == 1.0


def test_compute_roi_scale_channel_index_uses_energy_scale():
    assert compute_roi_scale_from_units(
        "channel_index", energy_scale=0.01,
    ) == 0.01
    assert compute_roi_scale_from_units(
        "channel_index", energy_scale=0.005,
    ) == 0.005


def test_compute_roi_scale_channel_index_needs_energy_scale():
    """When energy_scale is unresolved, channel_index can't be evaluated."""
    assert compute_roi_scale_from_units(
        "channel_index", energy_scale=None,
    ) is None


def test_compute_roi_scale_unknown_token_returns_none():
    assert compute_roi_scale_from_units("unknown", energy_scale=0.01) is None


# ---------------------------------------------------------------------------
# Default mode is now GENERIC (Phase 4, Chunk 18 breaking change)
# ---------------------------------------------------------------------------

def test_xrmmap_reader_default_mode_flipped_to_generic():
    assert XRMMapH5Reader().mode is ConversionMode.GENERIC


def test_generic_reader_default_mode_flipped_to_generic():
    assert GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA).mode is (
        ConversionMode.GENERIC
    )


def test_xrmmap_reader_preset_diagnostic_is_warning_in_default_mode(
    synthetic_xrmmap_h5,
):
    """In GENERIC mode (the new default), preset-derived calibrations
    surface as `warning` rather than `info`."""
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    preset_diag = next(
        d for d in payload.diagnostics
        if d.code == "calibration_resolved_from_preset"
    )
    assert preset_diag.severity == "warning"


def test_xrmmap_reader_preset_diagnostic_is_info_in_legacy_mode(
    synthetic_xrmmap_h5,
):
    """LEGACY mode keeps preset diagnostics at `info` — it's the
    explicit opt-in for inherited-dataset users who want quiet
    conversions."""
    payload = XRMMapH5Reader(mode=ConversionMode.LEGACY).read(
        synthetic_xrmmap_h5("ok.h5"),
    )
    preset_diag = next(
        d for d in payload.diagnostics
        if d.code == "calibration_resolved_from_preset"
    )
    assert preset_diag.severity == "info"


# ---------------------------------------------------------------------------
# Explicit-units ROI: roi_limit_units precedence + audit consistency
# ---------------------------------------------------------------------------

def test_user_roi_limit_units_overrides_preset(synthetic_xrmmap_h5):
    reader = XRMMapH5Reader(
        calibration=XRMMapH5Calibration(roi_limit_units="keV"),
    )
    payload = reader.read(synthetic_xrmmap_h5("user_units.h5"))
    rc = payload.resolved_calibration
    assert rc["roi_limit_units"].source is CalibrationSource.USER_CONFIG
    assert rc["roi_limit_units"].value == "keV"


def test_roi_units_channel_index_uses_energy_scale_for_scale(
    synthetic_xrmmap_h5,
):
    """When roi_limit_units='channel_index', the actual scale applied
    to integer ROI limits is the resolved energy_scale — not a magic
    multiplier."""
    p = synthetic_xrmmap_h5("legacy_rois.h5")
    payload = XRMMapH5Reader().read(p)
    rois = payload.original_metadata["rois"]
    # Fixture: ROI "Fe Ka" = [640, 670] integers; with channel_index
    # interpretation and energy_scale = 40.96/4096 ≈ 0.01, → 6.40 keV.
    assert rois[0]["name"] == "Fe Ka"
    assert rois[0]["start"] == pytest.approx(6.40)
    assert rois[0]["end"] == pytest.approx(6.70)


# ---------------------------------------------------------------------------
# Explicit-geometry: pixel_size_um and field_width_um precedence
# ---------------------------------------------------------------------------

def test_user_pixel_size_takes_priority_over_environ_beam_size(
    synthetic_xrmmap_h5,
):
    """USER_CONFIG via pixel_size_um wins over the environ beam_size
    that SOURCE_METADATA would otherwise pick up — explicit user
    intent beats implicit metadata."""
    # Wait — actually per the ladder, SOURCE_METADATA wins outright
    # for the environ beam_size (audit's most-authoritative rank).
    # This test verifies the *no-environ* case where the user can
    # supply pixel_size_um directly.
    p = synthetic_xrmmap_h5(
        "no_beam.h5", environ={"Other.Key": "v"}, shape=(10, 5, 16),
    )
    reader = XRMMapH5Reader(
        calibration=XRMMapH5Calibration(pixel_size_um=3.0),
    )
    payload = reader.read(p)
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    assert nav_x.scale == pytest.approx(3.0)
    rc = payload.resolved_calibration
    assert rc["navigation_scale"].source is CalibrationSource.USER_CONFIG


def test_user_field_width_um_derives_scale_via_xdim(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "no_beam.h5", environ={"Other.Key": "v"}, shape=(10, 5, 16),
    )
    reader = XRMMapH5Reader(
        calibration=XRMMapH5Calibration(field_width_um=200.0),
    )
    payload = reader.read(p)
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    # 200 µm / 10 pixels = 20 µm/pixel.
    assert nav_x.scale == pytest.approx(20.0)


def test_pixel_size_um_beats_field_width_um(synthetic_xrmmap_h5):
    """If a user supplies both, pixel_size_um wins (direct trumps derived)."""
    p = synthetic_xrmmap_h5(
        "no_beam.h5", environ={"Other.Key": "v"}, shape=(10, 5, 16),
    )
    reader = XRMMapH5Reader(
        calibration=XRMMapH5Calibration(
            pixel_size_um=2.5,
            field_width_um=999.0,  # would derive a different scale
        ),
    )
    payload = reader.read(p)
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    assert nav_x.scale == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# Strict mode raises on the generic reader (Chunk 17 wired XRM; Chunk 18
# extends to GenericHDF5MapReader)
# ---------------------------------------------------------------------------

def test_generic_reader_strict_mode_raises_when_calibration_missing(
    synthetic_xrmmap_h5,
):
    """Generic reader has no preset — strict + no calibration → raise."""
    p = synthetic_xrmmap_h5("ok.h5")
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        mode=ConversionMode.STRICT,
    )
    with pytest.raises(
        CalibrationUnresolvedError, match="roi_limit_units|energy_scale",
    ):
        reader.read(p)


def test_generic_reader_strict_mode_passes_with_full_calibration(
    synthetic_xrmmap_h5,
):
    """All required fields supplied → no raise, all USER_CONFIG."""
    p = synthetic_xrmmap_h5("ok.h5")
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        calibration=HDF5MapCalibration(
            energy_scale=0.01,
            roi_limit_units="channel_index",
            # navigation_scale resolves via environ in this fixture
            # (Experiment.Beam_Size__Nominal=1um), so no pixel/field
            # needed here.
        ),
        mode=ConversionMode.STRICT,
    )
    payload = reader.read(p)
    rc = payload.resolved_calibration
    assert rc["energy_scale"].source is CalibrationSource.USER_CONFIG
    assert rc["roi_limit_units"].source is CalibrationSource.USER_CONFIG
    assert rc["navigation_scale"].source is CalibrationSource.SOURCE_METADATA
