"""Tests for :mod:`axiomm.io.converters.presets` (Phase 4, Chunk 17).

Covers the named-preset registry + the
:class:`XRMMapH5Calibration` dataclass shape. The Chunk-17
resolution-ladder enforcement tests live in
``test_calibration_resolution.py`` and ``test_xrmmap_h5_reader.py``;
this file is focused on the preset module itself.
"""

from __future__ import annotations

import dataclasses

import pytest

from axiomm.io.converters import (
    XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1,
    XRMMapH5Calibration,
    get_preset,
    iter_presets,
    register_preset,
)


# ---------------------------------------------------------------------------
# XRMMapH5Calibration — split off from the old XRMMapH5Config
# ---------------------------------------------------------------------------

def test_calibration_has_seven_documented_fields():
    """Phase 4, Chunk 18: added roi_limit_units, field_width_um,
    field_height_um, pixel_size_um; renamed fallback → legacy."""
    fields = {f.name for f in dataclasses.fields(XRMMapH5Calibration)}
    assert fields == {
        "energy_scale",
        "roi_limit_units",
        "field_width_um",
        "field_height_um",
        "pixel_size_um",
        "legacy_field_width_um",
        "roi_variant_index",
    }


def test_calibration_defaults_are_all_none():
    cal = XRMMapH5Calibration()
    assert cal.energy_scale is None
    assert cal.roi_limit_units is None
    assert cal.field_width_um is None
    assert cal.field_height_um is None
    assert cal.pixel_size_um is None
    assert cal.legacy_field_width_um is None
    assert cal.roi_variant_index is None


def test_calibration_is_frozen():
    cal = XRMMapH5Calibration()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cal.energy_scale = 0.01  # type: ignore[misc]


def test_calibration_explicit_values_are_preserved():
    cal = XRMMapH5Calibration(
        energy_scale=0.005,
        roi_limit_units="keV",
        field_width_um=200.0,
        field_height_um=150.0,
        pixel_size_um=1.5,
        legacy_field_width_um=300.0,
        roi_variant_index=2,
    )
    assert cal.energy_scale == 0.005
    assert cal.roi_limit_units == "keV"
    assert cal.field_width_um == 200.0
    assert cal.field_height_um == 150.0
    assert cal.pixel_size_um == 1.5
    assert cal.legacy_field_width_um == 300.0
    assert cal.roi_variant_index == 2


# ---------------------------------------------------------------------------
# XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1 — historic constants
# ---------------------------------------------------------------------------

def test_legacy_preset_carries_historic_values():
    p = XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1
    assert p.energy_scale == pytest.approx(40.96 / 4096)
    assert p.roi_limit_units == "channel_index"
    assert p.legacy_field_width_um == 500.0
    assert p.roi_variant_index == 0
    # Chunk 18: the preset doesn't pre-set explicit-geometry fields.
    assert p.field_width_um is None
    assert p.field_height_um is None
    assert p.pixel_size_um is None


def test_legacy_preset_is_xrmmap_h5_calibration_instance():
    assert isinstance(
        XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1, XRMMapH5Calibration,
    )


# ---------------------------------------------------------------------------
# Preset registry (lazy "module:attr" factories)
# ---------------------------------------------------------------------------

def test_iter_presets_lists_the_legacy_preset():
    names = iter_presets()
    assert "xrmmap_legacy_aps_13_id_e_v1" in names


def test_get_preset_returns_xrmmap_calibration_instance():
    p = get_preset("xrmmap_legacy_aps_13_id_e_v1")
    assert isinstance(p, XRMMapH5Calibration)
    assert p is XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1


def test_get_preset_raises_for_unknown_name():
    with pytest.raises(KeyError, match="Unknown calibration preset"):
        get_preset("does_not_exist")


def test_register_preset_makes_it_discoverable(monkeypatch):
    """register_preset is a public extension point. Mutate the registry
    inside a monkeypatched context so the module-global registry is
    restored after the test."""
    from axiomm.io.converters import presets as presets_module
    original = dict(presets_module._PRESETS)
    try:
        register_preset(
            "test_only_preset",
            "axiomm.io.converters.presets:XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1",
        )
        assert "test_only_preset" in iter_presets()
        p = get_preset("test_only_preset")
        assert isinstance(p, XRMMapH5Calibration)
    finally:
        presets_module._PRESETS = original  # restore
