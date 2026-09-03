"""Tests for compute_cluster_means (Stage two, S2)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.clustering.means import compute_cluster_means
from axiomm.analysis.clustering.models import ClusteringResult
from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _source(data):
    axes = (
        AxisSpec("x", "navigation", data.shape[0], index_in_array=0),
        AxisSpec("y", "navigation", data.shape[1], index_in_array=1),
        AxisSpec("Energy", "signal", data.shape[2], index_in_array=2),
    )
    return AxiommSignalPayload(data=data, axes=axes, signal_kind="signal1d")


def _clustering(labels, nav_shape, cluster_ids):
    labels = np.asarray(labels)
    return ClusteringResult(
        labels=labels,
        label_map=labels.reshape(nav_shape),
        cluster_ids=np.asarray(cluster_ids),
        n_clusters=len(cluster_ids),
        provenance=AnalysisProvenance(tool="clustering", backend="gmm"),
    )


def test_means_match_hand_computation_aligned_to_cluster_ids():
    # 4 pixels (2x2), 3 channels. labels: pixels 0,3 -> cluster 0; 1,2 -> cluster 1.
    data = np.array(
        [[[1.0, 1, 1], [3, 3, 3]], [[3, 3, 3], [1, 1, 1]]]
    )  # shape (2, 2, 3)
    result = _clustering([0, 1, 1, 0], (2, 2), [0, 1])
    cms = compute_cluster_means(result, _source(data))
    assert cms.means.shape == (2, 3)
    assert cms.pixel_counts.tolist() == [2, 2]
    np.testing.assert_allclose(cms.means[0], [1, 1, 1])
    np.testing.assert_allclose(cms.means[1], [3, 3, 3])
    assert cms.cluster_ids.tolist() == [0, 1]


def test_empty_cluster_yields_nan_and_diagnostic():
    data = np.ones((2, 2, 3))
    result = _clustering([0, 0, 0, 0], (2, 2), [0, 1])  # cluster 1 empty
    cms = compute_cluster_means(result, _source(data))
    assert cms.pixel_counts.tolist() == [4, 0]
    assert np.all(np.isnan(cms.means[1]))
    assert any(d.code == "empty_cluster" for d in cms.diagnostics)


def test_one_pixel_cluster_mean_is_that_pixel():
    data = np.arange(2 * 2 * 3, dtype=float).reshape(2, 2, 3)
    result = _clustering([0, 1, 1, 1], (2, 2), [0, 1])  # cluster 0 == pixel 0
    cms = compute_cluster_means(result, _source(data))
    np.testing.assert_allclose(cms.means[0], data.reshape(4, 3)[0])
    assert cms.pixel_counts.tolist() == [1, 3]


def test_pixel_count_mismatch_raises():
    data = np.ones((2, 2, 3))  # 4 pixels
    result = _clustering([0, 1, 0], (3, 1), [0, 1])  # 3 labels
    with pytest.raises(PayloadValidationError, match="pixels"):
        compute_cluster_means(result, _source(data))


def test_cluster_means_emit_heterogeneity_and_total_counts():
    # cluster 0: two identical spectra (homogeneous); cluster 1: two different shapes (mixed)
    data = np.array([[[1.0, 1, 1], [1, 1, 1]], [[1, 0, 0], [0, 0, 1]]])  # (2,2,3)
    result = _clustering([0, 0, 1, 1], (2, 2), [0, 1])
    cms = compute_cluster_means(result, _source(data))
    assert cms.heterogeneity[0] == pytest.approx(0.0, abs=1e-9)
    assert cms.heterogeneity[1] > 0.2
    assert cms.total_counts[0] == pytest.approx(3.0)   # mean [1,1,1]
    assert cms.total_counts[1] == pytest.approx(1.0)   # mean [0.5,0,0.5]


def test_blank_majority_cluster_not_reported_homogeneous():
    # P11: a cluster of two DIFFERENT signal phases plus a majority of blank
    # (zero-count) pixels must not read as homogeneous. If blanks were scored
    # as distance 0 and kept, the median would be pulled to 0 (false 0). They
    # must be excluded so the genuine phase spread survives.
    # 6 pixels: [1,0], [0,1], and four [0,0] blanks -> one cluster.
    rows = np.array([[1.0, 0.0], [0.0, 1.0], [0, 0], [0, 0], [0, 0], [0, 0]])
    data = rows.reshape(2, 3, 2)
    result = _clustering([0, 0, 0, 0, 0, 0], (2, 3), [0])
    cms = compute_cluster_means(result, _source(data))
    assert cms.heterogeneity[0] > 0.2       # not falsely 0
    assert any(d.code == "blank_members_excluded" for d in cms.diagnostics)


def test_all_blank_cluster_heterogeneity_undefined():
    # P11: a degenerate all-zero cluster mean has undefined direction; its
    # heterogeneity is NaN (undefined), never a false 0 (perfectly homogeneous).
    data = np.zeros((2, 2, 3))
    result = _clustering([0, 0, 0, 0], (2, 2), [0])
    cms = compute_cluster_means(result, _source(data))
    assert np.isnan(cms.heterogeneity[0])
    assert any(d.code == "heterogeneity_undefined" for d in cms.diagnostics)


def test_heterogeneity_within_admissible_interval():
    # finding 4: cosine distance must lie in [0, 2]. Across varied mixtures,
    # every finite heterogeneity the tool reports stays in that interval.
    rng = np.random.default_rng(0)
    data = rng.random((6, 6, 5))
    labels = rng.integers(0, 3, size=36)
    result = _clustering(labels.tolist(), (6, 6), [0, 1, 2])
    cms = compute_cluster_means(result, _source(data))
    finite = cms.heterogeneity[np.isfinite(cms.heterogeneity)]
    assert np.all((finite >= 0.0) & (finite <= 2.0))
