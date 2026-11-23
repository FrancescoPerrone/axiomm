"""Categorical phase/cluster-map palette — a configurable setting (default batlowS)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.reporting.palettes import (
    BUILTIN_PALETTES,
    CRAMERI_BATLOWS,
    DEFAULT_PALETTE,
    available_palettes,
    resolve_palette,
)


def test_default_is_crameri_batlows():
    assert DEFAULT_PALETTE == "batlowS"
    assert resolve_palette(None, 1) == [CRAMERI_BATLOWS[0]]
    assert "batlowS" in available_palettes()


def test_builtin_batlows_has_100_distinct_entries():
    # the headline property: many phases stay separable without colour reuse
    assert len(CRAMERI_BATLOWS) == 100
    assert len(set(CRAMERI_BATLOWS)) == 100
    cols = resolve_palette("batlowS", 40)
    assert len(cols) == 40 and len(set(cols)) == 40   # no wrap-around up to 100


def test_builtin_names_need_no_matplotlib():
    # resolving an embedded palette must not require matplotlib (headless core)
    assert resolve_palette("okabe_ito", 3) == list(BUILTIN_PALETTES["okabe_ito"][:3])


def test_explicit_colour_list_is_used_verbatim_and_cycles():
    assert resolve_palette(["#111111", "#222222"], 3) == ["#111111", "#222222", "#111111"]


def test_builtin_palette_cycles_past_its_length():
    # declared exhaustion policy: a fixed-length built-in repeats past its capacity
    cols = resolve_palette("okabe_ito", 10)                 # okabe_ito has 8
    assert len(cols) == 10
    assert cols[8] == cols[0] and cols[9] == cols[1]        # cycled, not errored


def test_reserve_pins_a_slot():
    cols = resolve_palette("batlowS", 3, reserve={1: "#8a8f98"})
    assert cols[1] == "#8a8f98" and cols[0] == CRAMERI_BATLOWS[0]


def test_matplotlib_colormap_name_resolves_when_available():
    pytest.importorskip("matplotlib")
    cols = resolve_palette("tab20", 6)
    assert len(cols) == 6 and all(c.startswith("#") for c in cols)


def test_unknown_name_raises():
    with pytest.raises(PayloadValidationError):
        resolve_palette("definitely_not_a_colormap", 3)


def test_bad_spec_type_raises():
    with pytest.raises(PayloadValidationError):
        resolve_palette(42, 3)


def test_empty_request_returns_empty():
    assert resolve_palette("batlowS", 0) == []


def test_categorical_map_png_accepts_palette():
    pytest.importorskip("matplotlib")
    import numpy as np

    from axiomm.analysis.reporting.figures import categorical_map_png

    arr = np.array([[0, 1, 2], [2, 1, 0]])
    png = categorical_map_png(arr, [0, 1, 2], palette="batlowS", reserve={2: "#8a8f98"})
    assert isinstance(png, bytes) and len(png) > 1000
    # an explicit palette is honoured too
    png2 = categorical_map_png(arr, [0, 1, 2], palette=["#101010", "#202020", "#303030"])
    assert isinstance(png2, bytes) and len(png2) > 1000


def test_report_config_defaults_to_batlows():
    from axiomm.analysis.reporting.models import ReportConfig

    assert ReportConfig().palette == "batlowS"
