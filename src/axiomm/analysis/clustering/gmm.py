"""Gaussian-Mixture clustering backend.

Pure clustering over ``features.loadings``; never touches the source
signal. scikit-learn is imported lazily. No situated defaults:
``n_clusters`` is required; ``random_state`` defaults to ``None``;
``covariance_type`` defaults to scikit-learn's own ``"full"``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.clustering.models import ClusteringResult


@dataclass(frozen=True)
class GMMConfig:
    """Tuning parameters for :class:`GMMClusterer` (all scikit-learn defaults)."""

    covariance_type: str = "full"
    random_state: int | None = None
    n_init: int = 1
    max_iter: int = 100
    tol: float = 1e-3
    reg_covar: float = 1e-6


class GMMClusterer:
    """Cluster decomposition loadings with a Gaussian mixture."""

    name = "gmm"

    def __init__(self, n_clusters: int, config: GMMConfig | None = None) -> None:
        self.n_clusters = n_clusters
        self.config = config or GMMConfig()

    def cluster(self, features) -> ClusteringResult:
        loadings = np.asarray(features.loadings)
        if loadings.ndim != 2:
            raise PayloadValidationError(
                f"features.loadings must be 2-D (n_pixels, n_features); "
                f"got shape {loadings.shape}."
            )
        if not np.all(np.isfinite(loadings)):
            raise PayloadValidationError(
                "features.loadings contains non-finite values (NaN or inf)."
            )

        n_pixels = loadings.shape[0]
        if self.n_clusters < 1:
            raise PayloadValidationError(
                f"n_clusters must be >= 1; got {self.n_clusters}."
            )
        if self.n_clusters > n_pixels:
            raise PayloadValidationError(
                f"n_clusters={self.n_clusters} exceeds n_pixels={n_pixels}."
            )

        from sklearn.mixture import GaussianMixture

        cfg = self.config
        gmm = GaussianMixture(
            n_components=self.n_clusters,
            covariance_type=cfg.covariance_type,
            random_state=cfg.random_state,
            n_init=cfg.n_init,
            max_iter=cfg.max_iter,
            tol=cfg.tol,
            reg_covar=cfg.reg_covar,
        )
        labels = gmm.fit_predict(loadings)
        nav_shape = tuple(int(d) for d in features.nav_shape)
        label_map = labels.reshape(nav_shape)
        cluster_ids = np.arange(self.n_clusters)

        return ClusteringResult(
            labels=labels,
            label_map=label_map,
            cluster_ids=cluster_ids,
            n_clusters=self.n_clusters,
            provenance=AnalysisProvenance(
                tool="clustering",
                backend=self.name,
                params={
                    "n_clusters": self.n_clusters,
                    "covariance_type": cfg.covariance_type,
                    "random_state": cfg.random_state,
                },
            ),
        )


__all__ = ["GMMClusterer", "GMMConfig"]
