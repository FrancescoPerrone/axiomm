"""Tests for clustering result payloads (Stage two, S2)."""

from __future__ import annotations

import numpy as np

from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.clustering.models import ClusterMeanSpectra, ClusteringResult


def test_clustering_result_masks_property_aligns_to_cluster_ids():
    label_map = np.array([[0, 1], [1, 2]])
    result = ClusteringResult(
        labels=label_map.reshape(-1),
        label_map=label_map,
        cluster_ids=np.array([0, 1, 2]),
        n_clusters=3,
        provenance=AnalysisProvenance(tool="clustering", backend="gmm"),
    )
    masks = result.masks
    assert masks.shape == (3, 2, 2)
    assert masks[0].tolist() == [[True, False], [False, False]]
    assert masks[1].tolist() == [[False, True], [True, False]]
    assert masks[2].tolist() == [[False, False], [False, True]]
    assert result.diagnostics == []


def test_cluster_mean_spectra_holds_aligned_arrays():
    cms = ClusterMeanSpectra(
        means=np.zeros((3, 8)),
        pixel_counts=np.array([5, 0, 7]),
        cluster_ids=np.array([0, 1, 2]),
        n_clusters=3,
        diagnostics=[Diagnostic("warning", "empty_cluster", "1 empty")],
    )
    assert cms.means.shape == (3, 8)
    assert cms.pixel_counts.tolist() == [5, 0, 7]
    assert cms.cluster_ids.tolist() == [0, 1, 2]
    assert cms.diagnostics[0].code == "empty_cluster"


def test_cluster_mean_spectra_quality_fields_default_none():
    import numpy as np
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    cms = ClusterMeanSpectra(means=np.zeros((2, 3)), pixel_counts=np.array([1, 1]),
                             cluster_ids=np.array([0, 1]), n_clusters=2)
    assert cms.heterogeneity is None and cms.total_counts is None
