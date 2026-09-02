"""Clustering tool (stage two, S2).

Pure clustering over the decomposition feature seam; per-cluster mean
spectra are a separate aggregation (:func:`compute_cluster_means`).

Because clustering backends are *configured* (e.g. ``n_clusters``), they
do not fit S0's instance-returning registry. The ``clusterers`` registry
therefore resolves a name to the backend **class**; the caller
constructs it with its typed config. Entry-point plugin discovery for
clusterers is deferred until a class-resolving registry variant is needed
(second backend / plugin, S6).
"""

from __future__ import annotations

from axiomm.analysis.registry import Registry
from axiomm.analysis.clustering.base import Clusterer
from axiomm.analysis.clustering.gmm import GMMClusterer, GMMConfig
from axiomm.analysis.clustering.means import compute_cluster_means
from axiomm.analysis.clustering.models import ClusterMeanSpectra, ClusteringResult

#: Registry mapping a stable name to a clusterer **class** (not instance).
clusterers: Registry = Registry("clusterer")
clusterers.register("gmm", lambda: GMMClusterer)


def get_clusterer(name: str):
    """Return the clusterer **class** registered under ``name``.

    Construct it with its own typed config, e.g.
    ``get_clusterer("gmm")(n_clusters=7, config=GMMConfig(random_state=0))``.
    """
    return clusterers.get(name)


__all__ = [
    "Clusterer",
    "ClusterMeanSpectra",
    "ClusteringResult",
    "GMMClusterer",
    "GMMConfig",
    "clusterers",
    "compute_cluster_means",
    "get_clusterer",
]
