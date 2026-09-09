"""Clustering section — the label map and cluster sizes (stage two, S4c).

Shows the spatial partition (per-pixel cluster id, as a categorical image with a
legend) and a per-cluster table of size and, when available, within-cluster
spectral heterogeneity and total counts.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.reporting.figures import categorical_map_png
from axiomm.analysis.reporting.models import Figure, ReportSection, Table


class ClusteringSection:
    id = "clustering"

    def applies(self, result) -> bool:
        return (getattr(result, "clustering", None) is not None
                or getattr(result, "cluster_means", None) is not None)

    def render(self, result, config) -> ReportSection:
        clustering = getattr(result, "clustering", None)
        means = getattr(result, "cluster_means", None)
        cluster_ids = self._ids(clustering, means)
        n = len(cluster_ids)
        blocks: list = [f"{n} clusters."]

        diags: list[Diagnostic] = []
        label_map = getattr(result, "label_map", None)
        if label_map is None and clustering is not None:
            label_map = getattr(clustering, "label_map", None)
        if label_map is not None:
            try:
                png = categorical_map_png(np.asarray(label_map), list(cluster_ids),
                                          labels=[f"cluster {c}" for c in cluster_ids])
                blocks.append(Figure(png, alt="cluster label map", caption="cluster label map"))
            except AnalysisDependencyError as exc:
                diags.append(Diagnostic("warning", "figure_skipped_dependency", str(exc)))

        blocks.append(self._sizes_table(cluster_ids, means, label_map))
        return ReportSection("clustering", "Clustering", blocks, diagnostics=diags)

    def _ids(self, clustering, means):
        for src in (means, clustering):
            ids = getattr(src, "cluster_ids", None)
            if ids is not None:
                return [int(c) for c in np.asarray(ids)]
        return []

    def _sizes_table(self, cluster_ids, means, label_map) -> Table:
        counts = getattr(means, "pixel_counts", None)
        if counts is not None:
            counts = [int(c) for c in np.asarray(counts)]
        elif label_map is not None:
            lm = np.asarray(label_map)
            counts = [int(np.sum(lm == c)) for c in cluster_ids]
        else:
            counts = [None] * len(cluster_ids)

        het = getattr(means, "heterogeneity", None)
        tot = getattr(means, "total_counts", None)
        headers = ["cluster", "pixels"]
        if het is not None:
            headers.append("heterogeneity")
        if tot is not None:
            headers.append("total counts")
        rows = []
        for i, cid in enumerate(cluster_ids):
            row = [cid, counts[i]]
            if het is not None:
                row.append(round(float(np.asarray(het)[i]), 4))
            if tot is not None:
                row.append(round(float(np.asarray(tot)[i]), 1))
            rows.append(row)
        return Table(headers, rows, "cluster sizes")


__all__ = ["ClusteringSection"]
