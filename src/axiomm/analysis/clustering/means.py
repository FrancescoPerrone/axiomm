"""Per-cluster mean spectra — a separate aggregation over the source signal.

This is intentionally *not* part of the clusterer: the clusterer never
depends on the source signal. Means are aligned row-for-row to the
clustering's ``cluster_ids`` so the relationship survives serialization.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.reshape import pixels_by_channels
from axiomm.analysis.clustering.models import ClusterMeanSpectra, ClusteringResult


def compute_cluster_means(result: ClusteringResult, source) -> ClusterMeanSpectra:
    """Average ``source`` spectra by ``result`` label, aligned to cluster_ids."""
    flat = pixels_by_channels(source)
    labels = np.asarray(result.labels)
    if flat.n_pixels != labels.size:
        raise PayloadValidationError(
            f"source has {flat.n_pixels} pixels but the clustering labelled "
            f"{labels.size}."
        )

    X = flat.matrix
    cluster_ids = np.asarray(result.cluster_ids)
    means = np.full((cluster_ids.size, flat.n_channels), np.nan, dtype=float)
    counts = np.zeros(cluster_ids.size, dtype=int)
    diagnostics: list[Diagnostic] = []

    for i, cid in enumerate(cluster_ids):
        mask = labels == cid
        count = int(mask.sum())
        counts[i] = count
        if count == 0:
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "empty_cluster",
                    f"Cluster {int(cid)} has no pixels; its mean spectrum is NaN.",
                )
            )
            continue
        means[i] = X[mask].mean(axis=0)

    heterogeneity = np.full(cluster_ids.size, np.nan, dtype=float)
    total_counts = np.zeros(cluster_ids.size, dtype=float)
    for i, cid in enumerate(cluster_ids):
        total_counts[i] = float(means[i].sum())
        if counts[i] == 0:
            continue
        member = X[labels == cid]
        mean_i = means[i]
        mean_norm = float(np.linalg.norm(mean_i))
        row_norms = np.linalg.norm(member, axis=1)
        denom = row_norms * mean_norm
        dots = member @ mean_i
        with np.errstate(invalid="ignore", divide="ignore"):
            cos = np.where(denom > 0, dots / denom, 1.0)
        heterogeneity[i] = float(np.median(1.0 - cos))

    src_backend = result.provenance.backend if result.provenance else "unknown"
    provenance = AnalysisProvenance(
        tool="clustering",
        backend=src_backend,
        params={"aggregation": "cluster_means", "n_clusters": int(result.n_clusters)},
    )
    return ClusterMeanSpectra(
        means=means,
        pixel_counts=counts,
        cluster_ids=cluster_ids.copy(),
        n_clusters=int(result.n_clusters),
        heterogeneity=heterogeneity,
        total_counts=total_counts,
        provenance=provenance,
        diagnostics=diagnostics,
    )


__all__ = ["compute_cluster_means"]
