"""HDBSCAN clustering backend (stage two, S6).

Density-based clustering over ``features.loadings`` via
``sklearn.cluster.HDBSCAN`` (bundled with scikit-learn >= 1.3 — no extra
dependency). Unlike the GMM backend there is no fixed cluster count: HDBSCAN
discovers clusters and marks unassigned pixels as noise (label ``-1``), which is
carried through as a cluster id so downstream stages stay noise-safe. scikit-learn
is imported lazily.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiomm.analysis.clustering.models import ClusteringResult
from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic


@dataclass(frozen=True)
class HDBSCANConfig:
    """Tuning parameters for :class:`HDBSCANClusterer` (scikit-learn defaults)."""

    min_cluster_size: int = 5
    min_samples: int | None = None
    cluster_selection_epsilon: float = 0.0
    metric: str = "euclidean"
    cluster_selection_method: str = "eom"


class HDBSCANClusterer:
    """Cluster decomposition loadings with HDBSCAN (no fixed cluster count)."""

    name = "hdbscan"

    def __init__(self, config: HDBSCANConfig | None = None) -> None:
        self.config = config or HDBSCANConfig()

    def cluster(self, features) -> ClusteringResult:
        loadings = np.asarray(features.loadings)
        if loadings.ndim != 2:
            raise PayloadValidationError(
                f"features.loadings must be 2-D (n_pixels, n_features); got shape {loadings.shape}.")
        if not np.all(np.isfinite(loadings)):
            raise PayloadValidationError(
                "features.loadings contains non-finite values (NaN or inf).")

        from sklearn.cluster import HDBSCAN

        cfg = self.config
        model = HDBSCAN(
            min_cluster_size=cfg.min_cluster_size,
            min_samples=cfg.min_samples,
            cluster_selection_epsilon=cfg.cluster_selection_epsilon,
            metric=cfg.metric,
            cluster_selection_method=cfg.cluster_selection_method,
            copy=True,   # do not mutate the caller's loadings (also silences a FutureWarning)
        )
        labels = model.fit_predict(loadings)
        nav_shape = tuple(int(d) for d in features.nav_shape)
        label_map = labels.reshape(nav_shape)
        cluster_ids = np.unique(labels)                      # includes -1 (noise) if present
        n_real = int(np.sum(cluster_ids >= 0))

        diagnostics: list[Diagnostic] = [
            Diagnostic("info", "hdbscan_clusters",
                       f"HDBSCAN found {n_real} cluster(s) (min_cluster_size={cfg.min_cluster_size}).")]
        n_noise = int(np.sum(labels == -1))
        if n_noise:
            diagnostics.append(Diagnostic(
                "info", "hdbscan_noise",
                f"{n_noise} of {labels.size} pixels unassigned (noise, label -1)."))

        return ClusteringResult(
            labels=labels,
            label_map=label_map,
            cluster_ids=cluster_ids,
            n_clusters=int(cluster_ids.size),
            provenance=AnalysisProvenance(
                tool="clustering", backend=self.name,
                params={"min_cluster_size": cfg.min_cluster_size,
                        "min_samples": cfg.min_samples, "metric": cfg.metric}),
            diagnostics=diagnostics,
        )


__all__ = ["HDBSCANClusterer", "HDBSCANConfig"]
