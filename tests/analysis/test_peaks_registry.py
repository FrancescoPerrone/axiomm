"""Tests for the peaks registry + batch helper (Stage two, S3b)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import BackendNotFoundError
from axiomm.analysis.clustering.models import ClusterMeanSpectra
from axiomm.io.converters.models import AxisSpec


def _axis(n=1000, scale=0.01):
    return AxisSpec("Energy", "signal", n, units="keV", scale=scale, offset=0.0)


def test_get_peak_measurer_returns_net_intensity_class():
    from axiomm.analysis.peaks import get_peak_measurer
    from axiomm.analysis.peaks.net_intensity import NetIntensityMeasurer

    assert get_peak_measurer("net_intensity") is NetIntensityMeasurer


def test_unknown_measurer_raises():
    from axiomm.analysis.peaks import get_peak_measurer

    with pytest.raises(BackendNotFoundError):
        get_peak_measurer("nope")


def test_measure_cluster_means_aligns_to_clusters():
    from axiomm.analysis.peaks import get_peak_measurer, measure_cluster_means

    means = ClusterMeanSpectra(
        means=np.full((2, 1000), 5.0),
        pixel_counts=np.array([3, 4]),
        cluster_ids=np.array([0, 1]),
        n_clusters=2,
    )
    measurer = get_peak_measurer("net_intensity")()
    sets = measure_cluster_means(means, _axis(), {"Fe": 6.40}, measurer=measurer)
    assert len(sets) == 2
    assert all(s.measurements[0].label == "Fe" for s in sets)
