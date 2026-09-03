"""Per-cluster mean spectra — a separate aggregation over the source signal.

This is intentionally *not* part of the clusterer: the clusterer never
depends on the source signal. Means are aligned row-for-row to the
clustering's ``cluster_ids`` so the relationship survives serialization.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.clustering.models import ClusteringResult, ClusterMeanSpectra
from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.reshape import pixels_by_channels


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
    # Heterogeneity = median cosine distance of member spectra to the mean.
    # KNOWN LIMITATIONS (deferred, see docs/user/analysis.md): the median is
    # insensitive to a minority (<50%) mixed population, and cosine distance
    # confounds genuine compositional mixing with Poisson counting noise at
    # low counts. Choosing an upper-quantile / fraction-exceeding metric and
    # a noise model is a scientific design decision pending count-controlled
    # validation. What is fixed here: a zero-norm member (a blank pixel)
    # carries no directional information and must NOT be scored as distance 0
    # (identical to the mean); it is excluded, and a degenerate all-zero mean
    # yields an undefined (NaN) heterogeneity rather than a false 0.
    for i, cid in enumerate(cluster_ids):
        total_counts[i] = float(means[i].sum())
        if counts[i] == 0:
            continue
        member = X[labels == cid]
        mean_i = means[i]
        mean_norm = float(np.linalg.norm(mean_i))
        row_norms = np.linalg.norm(member, axis=1)
        valid = row_norms > 0
        n_blank = int((~valid).sum())
        if mean_norm == 0.0 or not valid.any():
            heterogeneity[i] = np.nan
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "heterogeneity_undefined",
                    f"Cluster {int(cid)}: mean or all members have zero norm; "
                    "heterogeneity is undefined (NaN).",
                )
            )
            continue
        if n_blank:
            diagnostics.append(
                Diagnostic(
                    "info",
                    "blank_members_excluded",
                    f"Cluster {int(cid)}: {n_blank} zero-norm member spectra "
                    "excluded from the heterogeneity estimate.",
                )
            )
        mv = member[valid]
        denom = row_norms[valid] * mean_norm
        cos = (mv @ mean_i) / denom
        distances = 1.0 - cos
        # A cosine distance must lie in [0, 2]. Small floating-point excursions
        # past the ends are clamped; anything beyond tolerance signals corrupt
        # input (e.g. non-finite spectra that slipped a norm check) and makes
        # the estimate undefined rather than silently out-of-range (finding 4).
        tol = 1e-9
        if not np.all(np.isfinite(distances)) or float(distances.min()) < -tol \
                or float(distances.max()) > 2.0 + tol:
            heterogeneity[i] = np.nan
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "heterogeneity_undefined",
                    f"Cluster {int(cid)}: cosine distance outside the admissible "
                    "[0, 2] interval; heterogeneity is undefined (NaN).",
                )
            )
            continue
        distances = np.clip(distances, 0.0, 2.0)
        heterogeneity[i] = float(np.median(distances))

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
