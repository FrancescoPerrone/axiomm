"""Tests for the Clusterer protocol + GMMClusterer (Stage two, S2)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.decomposition.models import DecompositionResult


def _features(n_pixels=40, nav_shape=(8, 5)):
    """A DecompositionResult with two well-separated blobs in 3-D loadings."""
    rng = np.random.default_rng(0)
    half = n_pixels // 2
    a = rng.normal(-5, 0.2, size=(half, 3))
    b = rng.normal(5, 0.2, size=(n_pixels - half, 3))
    loadings = np.vstack([a, b])
    return DecompositionResult(
        factors=np.zeros((8, 3)),
        loadings=loadings,
        explained_variance_ratio=np.array([0.6, 0.3, 0.1]),
        nav_shape=nav_shape,
        n_components=3,
    )


def test_gmm_class_satisfies_protocol():
    from axiomm.analysis.clustering.base import Clusterer
    from axiomm.analysis.clustering.gmm import GMMClusterer

    assert isinstance(GMMClusterer(n_clusters=2), Clusterer)


def test_gmm_cluster_shapes_and_ids():
    pytest.importorskip("sklearn")
    from axiomm.analysis.clustering.gmm import GMMClusterer

    result = GMMClusterer(n_clusters=2).cluster(_features())
    assert result.labels.shape == (40,)
    assert result.label_map.shape == (8, 5)
    assert result.cluster_ids.tolist() == [0, 1]
    assert result.n_clusters == 2
    assert result.masks.shape == (2, 8, 5)
    assert result.provenance.tool == "clustering"
    assert result.provenance.backend == "gmm"
    assert result.provenance.params["n_clusters"] == 2


def test_gmm_is_deterministic_by_partition_with_fixed_seed():
    pytest.importorskip("sklearn")
    from sklearn.metrics import adjusted_rand_score

    from axiomm.analysis.clustering.gmm import GMMClusterer, GMMConfig

    features = _features()
    a = GMMClusterer(n_clusters=2, config=GMMConfig(random_state=7)).cluster(features)
    b = GMMClusterer(n_clusters=2, config=GMMConfig(random_state=7)).cluster(features)
    # Same partition, compared by grouping equivalence (not exact label ints).
    assert adjusted_rand_score(a.labels, b.labels) == pytest.approx(1.0)


@pytest.mark.parametrize("bad", [0, -1, 999])
def test_gmm_invalid_n_clusters_raises(bad):
    from axiomm.analysis.clustering.gmm import GMMClusterer

    with pytest.raises(PayloadValidationError):
        GMMClusterer(n_clusters=bad).cluster(_features())


def test_gmm_non_finite_features_raise():
    from axiomm.analysis.clustering.gmm import GMMClusterer

    features = _features()
    features.loadings[0, 0] = np.inf
    with pytest.raises(PayloadValidationError, match="non-finite"):
        GMMClusterer(n_clusters=2).cluster(features)
