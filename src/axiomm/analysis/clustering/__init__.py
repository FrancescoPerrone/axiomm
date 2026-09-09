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
from axiomm.analysis.clustering.hdbscan import HDBSCANClusterer, HDBSCANConfig
from axiomm.analysis.clustering.means import compute_cluster_means
from axiomm.analysis.clustering.models import ClusterMeanSpectra, ClusteringResult

#: Registry mapping a stable name to a clusterer **class** (not instance).
clusterers: Registry = Registry("clusterer")
clusterers.register("gmm", lambda: GMMClusterer)
clusterers.register("hdbscan", lambda: HDBSCANClusterer)


def get_clusterer(name: str):
    """Return the clusterer **class** registered under ``name``.

    Construct it with its own typed config, e.g.
    ``get_clusterer("gmm")(n_clusters=7, config=GMMConfig(random_state=0))``.
    """
    return clusterers.get(name)


def _accepts(cls, param: str) -> bool:
    import inspect
    try:
        return param in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins without a signature
        return False


def cluster(features, *, backend: str = "gmm", n_clusters: int | None = None, config=None):
    """Cluster decomposition ``features`` with the named ``backend``, in one call.

    The friendly sibling of :func:`axiomm.analysis.decomposition.decompose`.
    Fixed-count backends (GMM) require ``n_clusters``; density backends (HDBSCAN)
    ignore it and discover the count. Pass the backend's typed ``config`` for
    finer control.
    """
    from axiomm.analysis.errors import PayloadValidationError

    cls = get_clusterer(backend)
    kwargs: dict = {}
    if _accepts(cls, "n_clusters"):
        if n_clusters is None:
            raise PayloadValidationError(
                f"clustering backend {backend!r} requires n_clusters.")
        kwargs["n_clusters"] = n_clusters
    if config is not None:
        kwargs["config"] = config
    return cls(**kwargs).cluster(features)


__all__ = [
    "Clusterer",
    "ClusterMeanSpectra",
    "ClusteringResult",
    "GMMClusterer",
    "GMMConfig",
    "HDBSCANClusterer",
    "HDBSCANConfig",
    "cluster",
    "clusterers",
    "compute_cluster_means",
    "get_clusterer",
]
