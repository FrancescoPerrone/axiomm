"""Tests for the clusterers registry (name -> class) (Stage two, S2)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import BackendNotFoundError


def test_get_clusterer_returns_gmm_class():
    from axiomm.analysis.clustering import get_clusterer
    from axiomm.analysis.clustering.gmm import GMMClusterer

    assert get_clusterer("gmm") is GMMClusterer


def test_get_clusterer_class_constructs_and_conforms():
    from axiomm.analysis.clustering import get_clusterer
    from axiomm.analysis.clustering.base import Clusterer

    inst = get_clusterer("gmm")(n_clusters=2)
    assert isinstance(inst, Clusterer)


def test_unknown_clusterer_raises():
    from axiomm.analysis.clustering import get_clusterer

    with pytest.raises(BackendNotFoundError):
        get_clusterer("nope")
