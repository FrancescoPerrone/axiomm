"""Tests for the quantification reliability gate (Stage two, S3c-3)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.quant.models import QuantResult
from axiomm.analysis.quant.reliability import (
    ReliabilityConfig,
    ReliabilityReport,
    assess_reliability,
)


def _quant(nets):
    return QuantResult(net_intensities=nets, wt_percent_element={}, wt_percent_oxide={},
                       reference_element="Si")


def test_config_and_report_construct():
    cfg = ReliabilityConfig()
    assert cfg.min_net_counts == 50.0
    r = ReliabilityReport(cluster_status="quantitative", element_status={"Si": "valid"},
                          reasons=())
    assert r.cluster_status == "quantitative"


def test_element_below_floor_flagged():
    r = assess_reliability(_quant({"Si": 100.0, "K": 6.0}), pixel_count=100,
                           heterogeneity=0.05, total_counts=1e5)
    assert r.element_status["K"] == "below_quantification_limit"
    assert r.element_status["Si"] == "valid"
    assert r.cluster_status == "quantitative"


def test_clean_cluster_is_quantitative():
    r = assess_reliability(_quant({"Si": 100.0}), pixel_count=100,
                           heterogeneity=0.05, total_counts=1e5)
    assert r.cluster_status == "quantitative" and r.reasons == ()


@pytest.mark.parametrize("kw,frag", [
    (dict(pixel_count=5, heterogeneity=0.05, total_counts=1e5), "pixel_count"),
    (dict(pixel_count=100, heterogeneity=0.4, total_counts=1e5), "heterogeneity"),
    (dict(pixel_count=100, heterogeneity=0.05, total_counts=100.0), "total_counts"),
    (dict(pixel_count=100, heterogeneity=float("nan"), total_counts=1e5), "heterogeneity undefined"),
])
def test_cluster_flagged_exploratory(kw, frag):
    r = assess_reliability(_quant({"Si": 100.0}), **kw)
    assert r.cluster_status == "exploratory_only"
    assert any(frag in reason for reason in r.reasons)
