"""Emission-line overlap detection (Layer A of the phase-map fix chain)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.quant.overlaps import detect_line_overlaps
from axiomm.pipeline.config import PipelineConfig


def test_ba_la_ti_ka_overlap_is_grouped():
    # Ba La 4.466 and Ti Ka 4.508 are 0.042 keV apart -> unresolvable at ~0.13.
    groups = detect_line_overlaps(
        {"Ba": 4.466, "Ti": 4.508, "Ca": 3.69, "Fe": 6.40}, 0.13)
    assert groups == [("Ba", "Ti")]   # Ca and Fe are cleanly resolved


def test_no_overlap_returns_empty():
    assert detect_line_overlaps({"Si": 1.74, "Ca": 3.69, "Fe": 6.40}, 0.13) == []


def test_zero_resolution_disables_detection():
    assert detect_line_overlaps({"Ba": 4.466, "Ti": 4.508}, 0.0) == []


def test_chained_near_lines_form_one_group():
    groups = detect_line_overlaps({"A": 1.00, "B": 1.10, "C": 1.20, "D": 2.00}, 0.12)
    assert groups == [("A", "B", "C")]


def test_config_accepts_exclude_and_resolution():
    cfg = PipelineConfig(exclude_elements={"Ba"}, line_resolution_kev=0.1)
    assert cfg.exclude_elements == frozenset({"Ba"})
    assert cfg.line_resolution_kev == 0.1


@pytest.mark.parametrize("bad", [{2}, {""}, ["Ba", 2]])
def test_config_rejects_bad_exclude_elements(bad):
    with pytest.raises(PayloadValidationError, match="exclude_elements"):
        PipelineConfig(exclude_elements=bad)


@pytest.mark.parametrize("bad", [-0.1, float("inf"), "x"])
def test_config_rejects_bad_resolution(bad):
    with pytest.raises(PayloadValidationError, match="line_resolution_kev"):
        PipelineConfig(line_resolution_kev=bad)
