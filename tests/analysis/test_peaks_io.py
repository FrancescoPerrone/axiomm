"""Tests for peaks file adapters (Stage two, S3b)."""

from __future__ import annotations

import json

import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet
from axiomm.analysis.peaks.io import SCHEMA_VERSION, read_peaks, write_peaks


def _pset():
    return PeakMeasurementSet(
        measurements=(
            PeakMeasurement("Si", 1.74, 100.0, 130.0, 10.0, 3, True),
            PeakMeasurement("K", 3.31, 0.0, 0.0, 0.0, 0, False),
        ),
        provenance=AnalysisProvenance(tool="peaks", backend="net_intensity",
                                      params={"half_width_kev": 0.06}),
        diagnostics=[Diagnostic("info", "line_out_of_range", "x")],
    )


def test_roundtrip(tmp_path):
    write_peaks(_pset(), tmp_path, "sample")
    back = read_peaks(tmp_path, "sample")
    assert back.net_by_label() == {"Si": 100.0, "K": 0.0}
    assert back.measurements[1].in_range is False
    assert back.provenance.backend == "net_intensity"
    assert back.diagnostics[0].code == "line_out_of_range"


def test_schema_version_recorded(tmp_path):
    write_peaks(_pset(), tmp_path, "sample")
    doc = json.loads((tmp_path / "sample_peaks.json").read_text())
    assert doc["schema_version"] == SCHEMA_VERSION


def test_refuses_silent_overwrite(tmp_path):
    write_peaks(_pset(), tmp_path, "sample")
    with pytest.raises(OutputExistsError):
        write_peaks(_pset(), tmp_path, "sample")
    write_peaks(_pset(), tmp_path, "sample", overwrite=True)
