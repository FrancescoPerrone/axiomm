"""Tests for clustering file adapters (Stage two, S2)."""

from __future__ import annotations

import json

import numpy as np
import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.clustering.models import ClusterMeanSpectra, ClusteringResult
from axiomm.analysis.clustering.io import (
    SCHEMA_VERSION,
    read_cluster_means,
    read_clustering,
    write_cluster_means,
    write_clustering,
)


def _clustering():
    label_map = np.array([[0, 1], [1, 2]], dtype=np.int64)
    return ClusteringResult(
        labels=label_map.reshape(-1),
        label_map=label_map,
        cluster_ids=np.array([0, 1, 2]),
        n_clusters=3,
        provenance=AnalysisProvenance(
            tool="clustering", backend="gmm", params={"n_clusters": 3}
        ),
    )


def _means():
    return ClusterMeanSpectra(
        means=np.arange(9, dtype=float).reshape(3, 3),
        pixel_counts=np.array([2, 1, 1]),
        cluster_ids=np.array([0, 1, 2]),
        n_clusters=3,
        provenance=AnalysisProvenance(tool="clustering", backend="gmm"),
        diagnostics=[Diagnostic("warning", "empty_cluster", "x")],
    )


def test_clustering_roundtrip_preserves_dtype_and_ids(tmp_path):
    write_clustering(_clustering(), tmp_path, "sample")
    back = read_clustering(tmp_path, "sample")
    assert np.array_equal(back.label_map, _clustering().label_map)
    assert back.label_map.dtype == np.int64
    assert back.cluster_ids.tolist() == [0, 1, 2]
    assert back.n_clusters == 3
    assert back.provenance.backend == "gmm"


def test_clustering_sidecar_records_schema_version(tmp_path):
    write_clustering(_clustering(), tmp_path, "sample")
    sidecar = json.loads((tmp_path / "sample_clustering.json").read_text())
    assert sidecar["schema_version"] == SCHEMA_VERSION


def test_cluster_means_roundtrip(tmp_path):
    write_cluster_means(_means(), tmp_path, "sample")
    back = read_cluster_means(tmp_path, "sample")
    assert np.array_equal(back.means, _means().means)
    assert back.pixel_counts.tolist() == [2, 1, 1]
    assert back.cluster_ids.tolist() == [0, 1, 2]
    assert back.diagnostics[0].code == "empty_cluster"


def test_write_refuses_silent_overwrite(tmp_path):
    write_clustering(_clustering(), tmp_path, "sample")
    with pytest.raises(OutputExistsError):
        write_clustering(_clustering(), tmp_path, "sample")
    write_clustering(_clustering(), tmp_path, "sample", overwrite=True)
