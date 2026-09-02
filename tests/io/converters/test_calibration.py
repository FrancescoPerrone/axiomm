"""Tests for :mod:`axiomm.io.converters.calibration` (Phase 4, Chunk 15).

Phase 4 of the AXIOMM converter introduces per-value calibration
provenance. Chunk 15 is *types + plumbing only* — no reader behaviour
change. These tests therefore cover the primitives directly
(``CalibrationSource``, ``ConversionMode``, ``ResolvedValue``), the
new metadata transformer (``nest_calibration_section``), the additive
``"calibration"`` subkey in ``build_axiomm_namespace``, and the
payload-level round-trip through both the HyperSpy builder path (via
the metadata composer) and the manifest writer.

Backwards-compat is a hard requirement: payloads with
``resolved_calibration=None`` must produce a namespace shape
byte-identical to the pre-Phase-4 layout. The "subkey omitted when
empty" tests guard that.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from axiomm.io.converters.calibration import (
    CalibrationSource,
    ConversionMode,
    ResolvedValue,
)
from axiomm.io.converters.metadata import (
    build_axiomm_namespace,
    nest_calibration_section,
)
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.io.converters.writers.manifest import build_manifest_dict


# ---------------------------------------------------------------------------
# CalibrationSource — StrEnum-style enum
# ---------------------------------------------------------------------------

def test_calibration_source_has_five_documented_members():
    assert {s.value for s in CalibrationSource} == {
        "source_metadata",
        "user_config",
        "legacy_preset",
        "inferred",
        "unknown",
    }


def test_calibration_source_is_str_subclass_for_json_friendliness():
    """``str`` subclassing lets ``json.dump`` emit the bare token."""
    assert isinstance(CalibrationSource.SOURCE_METADATA, str)
    assert CalibrationSource.SOURCE_METADATA == "source_metadata"
    assert json.dumps(CalibrationSource.LEGACY_PRESET) == '"legacy_preset"'


# ---------------------------------------------------------------------------
# ConversionMode — StrEnum-style enum
# ---------------------------------------------------------------------------

def test_conversion_mode_has_four_documented_members():
    assert {m.value for m in ConversionMode} == {
        "legacy",
        "generic",
        "strict",
        "diagnostic",
    }


def test_conversion_mode_is_str_subclass():
    assert isinstance(ConversionMode.LEGACY, str)
    assert ConversionMode.GENERIC == "generic"


# ---------------------------------------------------------------------------
# ResolvedValue — frozen dataclass with provenance
# ---------------------------------------------------------------------------

def test_resolved_value_carries_value_source_and_optional_note():
    rv = ResolvedValue(
        value=0.01,
        source=CalibrationSource.LEGACY_PRESET,
        note="APS 13-ID-E preset v1",
    )
    assert rv.value == 0.01
    assert rv.source is CalibrationSource.LEGACY_PRESET
    assert rv.note == "APS 13-ID-E preset v1"


def test_resolved_value_note_defaults_to_none():
    rv = ResolvedValue(value=1.0, source=CalibrationSource.USER_CONFIG)
    assert rv.note is None


def test_resolved_value_is_frozen():
    rv = ResolvedValue(value=1.0, source=CalibrationSource.USER_CONFIG)
    with pytest.raises(dataclasses.FrozenInstanceError):
        rv.value = 2.0  # type: ignore[misc]


def test_resolved_value_equality_is_value_based():
    a = ResolvedValue(value=0.01, source=CalibrationSource.LEGACY_PRESET, note="x")
    b = ResolvedValue(value=0.01, source=CalibrationSource.LEGACY_PRESET, note="x")
    assert a == b


def test_resolved_value_is_hashable():
    rv = ResolvedValue(value=0.01, source=CalibrationSource.LEGACY_PRESET)
    assert hash(rv) == hash(rv)
    {rv}  # set membership exercises __hash__


def test_resolved_value_accepts_non_float_values():
    """``value: Any`` so we can carry strings (units literals) too."""
    rv = ResolvedValue(value="channel_index", source=CalibrationSource.USER_CONFIG)
    assert rv.value == "channel_index"


# ---------------------------------------------------------------------------
# nest_calibration_section — JSON-friendly serialiser
# ---------------------------------------------------------------------------

def test_nest_calibration_section_serialises_each_entry_to_a_dict():
    section = nest_calibration_section({
        "energy_scale": ResolvedValue(
            value=0.01,
            source=CalibrationSource.LEGACY_PRESET,
            note="APS 13-ID-E v1",
        ),
        "navigation_scale": ResolvedValue(
            value=2.5,
            source=CalibrationSource.SOURCE_METADATA,
            note="/xrmmap/config/environ/value:Beam_Size__Nominal",
        ),
    })
    assert section == {
        "energy_scale": {
            "value": 0.01,
            "source": "legacy_preset",
            "note": "APS 13-ID-E v1",
        },
        "navigation_scale": {
            "value": 2.5,
            "source": "source_metadata",
            "note": "/xrmmap/config/environ/value:Beam_Size__Nominal",
        },
    }


def test_nest_calibration_section_returns_none_for_none_input():
    """Backwards-compat: omit the subkey when no calibration is resolved."""
    assert nest_calibration_section(None) is None


def test_nest_calibration_section_returns_none_for_empty_mapping():
    """Empty dict also omits the subkey — same byte-shape as legacy."""
    assert nest_calibration_section({}) is None


def test_nest_calibration_section_preserves_unknown_source():
    section = nest_calibration_section({
        "roi_limit_units": ResolvedValue(
            value=None,
            source=CalibrationSource.UNKNOWN,
            note="ambiguous: centi-keV vs channel-index degenerate at "
                 "energy_scale=0.01 keV/channel",
        ),
    })
    assert section["roi_limit_units"]["source"] == "unknown"
    assert section["roi_limit_units"]["value"] is None


# ---------------------------------------------------------------------------
# build_axiomm_namespace — additive "calibration" subkey
# ---------------------------------------------------------------------------

def _base_namespace_kwargs():
    return dict(
        reader_name="test_reader",
        reader_version="0.0.0",
        config={},
        axes=(AxisSpec("Energy", "signal", 16, units="keV", index_in_array=0),),
        provenance=None,
        classification=None,
        diagnostics=[],
    )


def test_build_namespace_omits_calibration_when_resolved_is_none():
    """Backwards-compat: pre-Phase-4 payload shape is byte-identical."""
    ns = build_axiomm_namespace(**_base_namespace_kwargs())
    assert "calibration" not in ns


def test_build_namespace_omits_calibration_when_resolved_is_empty():
    ns = build_axiomm_namespace(**_base_namespace_kwargs(), resolved_calibration={})
    assert "calibration" not in ns


def test_build_namespace_includes_calibration_when_resolved_is_populated():
    ns = build_axiomm_namespace(
        **_base_namespace_kwargs(),
        resolved_calibration={
            "energy_scale": ResolvedValue(
                value=0.01,
                source=CalibrationSource.LEGACY_PRESET,
                note="APS 13-ID-E v1",
            ),
        },
    )
    assert ns["calibration"] == {
        "energy_scale": {
            "value": 0.01,
            "source": "legacy_preset",
            "note": "APS 13-ID-E v1",
        },
    }


# ---------------------------------------------------------------------------
# AxiommSignalPayload — new optional field
# ---------------------------------------------------------------------------

def test_payload_default_resolved_calibration_is_none():
    """Default ``None`` is the backwards-compatible shape."""
    payload = AxiommSignalPayload(
        data=[[0.0]],
        axes=(AxisSpec("Energy", "signal", 1, index_in_array=0),),
        signal_kind="signal1d",
    )
    assert payload.resolved_calibration is None


def test_payload_accepts_resolved_calibration_dict():
    payload = AxiommSignalPayload(
        data=[[0.0]],
        axes=(AxisSpec("Energy", "signal", 1, index_in_array=0),),
        signal_kind="signal1d",
        resolved_calibration={
            "energy_scale": ResolvedValue(
                value=0.01, source=CalibrationSource.LEGACY_PRESET,
            ),
        },
    )
    assert "energy_scale" in payload.resolved_calibration
    assert payload.resolved_calibration["energy_scale"].source is (
        CalibrationSource.LEGACY_PRESET
    )


# ---------------------------------------------------------------------------
# Manifest — propagation through build_manifest_dict
# ---------------------------------------------------------------------------

def test_manifest_omits_calibration_subkey_when_payload_has_none():
    payload = AxiommSignalPayload(
        data=[[0.0]],
        axes=(AxisSpec("Energy", "signal", 1, index_in_array=0),),
        signal_kind="signal1d",
    )
    manifest = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="test_reader",
        writer_name="hspy",
        payload=payload,
    )
    assert "calibration" not in manifest["axiomm_metadata"]


def test_manifest_includes_calibration_subkey_when_payload_populates_it():
    payload = AxiommSignalPayload(
        data=[[0.0]],
        axes=(AxisSpec("Energy", "signal", 1, index_in_array=0),),
        signal_kind="signal1d",
        resolved_calibration={
            "energy_scale": ResolvedValue(
                value=0.01,
                source=CalibrationSource.LEGACY_PRESET,
                note="APS 13-ID-E v1",
            ),
            "navigation_scale": ResolvedValue(
                value=None,
                source=CalibrationSource.UNKNOWN,
                note="no beam_size in environ table",
            ),
        },
    )
    manifest = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="test_reader",
        writer_name="hspy",
        payload=payload,
    )
    cal = manifest["axiomm_metadata"]["calibration"]
    assert set(cal) == {"energy_scale", "navigation_scale"}
    assert cal["energy_scale"]["source"] == "legacy_preset"
    assert cal["navigation_scale"]["source"] == "unknown"
    assert cal["navigation_scale"]["value"] is None


def test_manifest_calibration_round_trips_through_json():
    payload = AxiommSignalPayload(
        data=[[0.0]],
        axes=(AxisSpec("Energy", "signal", 1, index_in_array=0),),
        signal_kind="signal1d",
        resolved_calibration={
            "energy_scale": ResolvedValue(
                value=0.01, source=CalibrationSource.LEGACY_PRESET, note="x",
            ),
        },
    )
    manifest = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="test_reader",
        writer_name="hspy",
        payload=payload,
    )
    decoded = json.loads(json.dumps(manifest, default=str))
    assert decoded["axiomm_metadata"]["calibration"]["energy_scale"] == {
        "value": 0.01,
        "source": "legacy_preset",
        "note": "x",
    }


# ---------------------------------------------------------------------------
# Public-API re-exports
# ---------------------------------------------------------------------------

def test_calibration_primitives_are_reexported_at_package_level():
    """Surface check: hand-coding ergonomics rule — top-level imports
    must Just Work for the documented primitives."""
    from axiomm.io.converters import (  # noqa: F401
        CalibrationSource as _CS,
        ConversionMode as _CM,
        ResolvedValue as _RV,
    )
    assert _CS is CalibrationSource
    assert _CM is ConversionMode
    assert _RV is ResolvedValue
