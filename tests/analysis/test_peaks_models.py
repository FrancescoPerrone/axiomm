"""Tests for peaks result payloads + protocol (Stage two, S3b)."""

from __future__ import annotations

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.peaks.base import PeakMeasurer
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet


def test_measurement_set_net_by_label():
    ms = PeakMeasurementSet(
        measurements=(
            PeakMeasurement("Si", 1.74, 100.0, 130.0, 10.0, 3, True),
            PeakMeasurement("K", 3.31, 0.0, 0.0, 0.0, 0, False),
        ),
        provenance=AnalysisProvenance(tool="peaks", backend="net_intensity"),
    )
    assert ms.net_by_label() == {"Si": 100.0, "K": 0.0}
    assert ms.measurements[1].in_range is False
    assert ms.diagnostics == []


def test_conforming_object_satisfies_protocol():
    class Dummy:
        name = "d"

        def measure(self, spectrum, energy_axis, line_energies):
            return None

    assert isinstance(Dummy(), PeakMeasurer)
