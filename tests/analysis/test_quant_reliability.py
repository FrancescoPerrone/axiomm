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
