"""Clustering result payloads.

Both carry ``provenance``/``diagnostics`` by composition (not by
inheriting a metadata base). Everything aligns to an explicit
``cluster_ids`` ordering so labels are treated as identifiers, not a
contiguous 0..k-1 range (HDBSCAN-noise safe).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from axiomm.analysis.models import AnalysisProvenance, Diagnostic


@dataclass
class ClusteringResult:
    """Labels for each pixel plus their navigation-shaped map.

    ``masks`` is a computed property (single source of truth =
    ``label_map`` + ``cluster_ids``), so it is never serialized
    redundantly and cannot drift. There is deliberately no ``means``
    field — mean spectra are produced separately by
    :func:`axiomm.analysis.clustering.means.compute_cluster_means`.
    """

    labels: np.ndarray
    label_map: np.ndarray
    cluster_ids: np.ndarray
    n_clusters: int
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def masks(self) -> np.ndarray:
        """Boolean masks ``(n_clusters, *nav_shape)`` aligned to ``cluster_ids``."""
        return np.stack(
            [self.label_map == cid for cid in self.cluster_ids], axis=0
        )


@dataclass
class ClusterMeanSpectra:
    """Per-cluster mean spectra, aligned row-for-row to ``cluster_ids``."""

    means: np.ndarray
    pixel_counts: np.ndarray
    cluster_ids: np.ndarray
    n_clusters: int
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


__all__ = ["ClusterMeanSpectra", "ClusteringResult"]
