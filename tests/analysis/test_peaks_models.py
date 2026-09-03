"""Tests for peaks result payloads + protocol (Stage two, S3b).

Includes the S3d repair-pass regression cases (findings 1, 5): duplicate
labels are rejected, and the retained LOD/LOQ facts (gross / background /
window) are validated at construction.
"""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
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


# --- finding 1: duplicate labels rejected (not silently overwritten) -------

def test_duplicate_labels_rejected():
    with pytest.raises(PayloadValidationError, match="duplicate"):
        PeakMeasurementSet(measurements=(
            PeakMeasurement("Si", 1.74, 100.0, 100.0, 0.0, 1, True),
            PeakMeasurement("Si", 1.74, 50.0, 50.0, 0.0, 1, True),
        ))


def test_cluster_id_must_be_integer():
    with pytest.raises(PayloadValidationError, match="cluster_id"):
        PeakMeasurementSet(
            measurements=(PeakMeasurement("Si", 1.74, 1.0, 1.0, 0.0, 1, True),),
            cluster_id=1.5,
        )


# --- finding 5: retained peak facts validated at construction --------------

@pytest.mark.parametrize("kwargs,frag", [
    (dict(gross=-1.0), "gross"),
    (dict(background=-1.0), "background"),
    (dict(net=float("nan")), "finite"),
    (dict(gross=float("inf")), "finite"),
    (dict(n_channels=-1), "n_channels"),
    (dict(n_channels=True), "n_channels"),   # bool is not a channel count
    (dict(n_channels=2.0), "n_channels"),    # float is not a channel count
])
def test_invalid_peak_facts_rejected(kwargs, frag):
    base = dict(label="Si", center_kev=1.74, net=10.0, gross=10.0,
                background=0.0, n_channels=1, in_range=True)
    base.update(kwargs)
    with pytest.raises(PayloadValidationError, match=frag):
        PeakMeasurement(**base)


def test_negative_net_allowed_when_gross_nonnegative():
    # net may be negative (background over-subtracted); the constraint is on
    # the retained facts, not on net.
    m = PeakMeasurement("Fe", 6.4, -5.0, 0.0, 5.0, 1, True)
    assert m.net == -5.0
