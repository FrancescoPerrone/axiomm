"""Embedding section — the reduction scatter, coloured by cluster (stage two).

Plots the pixels in the decomposition/embedding space (first two components) as a
theme-aware inline-SVG scatter coloured by cluster, so a reader can see how well
the clusters separate. **Scientifically gated:** the axes are reduced components,
not physical quantities — for UMAP especially, distances and directions are not
metric, so this is an exploratory visual aid, never evidence of phase validity.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.reporting.models import ReportSection, Svg
from axiomm.analysis.reporting.svg import scatter_svg


class EmbeddingSection:
    id = "embedding"

    def applies(self, result) -> bool:
        decomp = getattr(result, "decomposition", None)
        clustering = getattr(result, "clustering", None)
        if decomp is None or clustering is None:
            return False
        loadings = getattr(decomp, "loadings", None)
        return loadings is not None and np.asarray(loadings).ndim == 2 \
            and np.asarray(loadings).shape[1] >= 2

    def render(self, result, config) -> ReportSection:
        opts = config.options_for(self.id)
        decomp = result.decomposition
        loadings = np.asarray(decomp.loadings, dtype=float)
        labels = np.asarray(result.clustering.labels)
        backend = getattr(getattr(decomp, "provenance", None), "backend", "reduction")

        categories = [int(c) for c in np.unique(labels)]
        labels_text = {c: ("noise" if c == -1 else f"cluster {c}") for c in categories}
        note = (
            f"Pixels in the {backend} embedding (components 1 and 2), coloured by "
            "cluster. The axes are reduced components, not physical quantities; "
            "distances and directions are not compositional — an exploratory view of "
            "cluster separation, not a validated result.")
        svg = scatter_svg(
            loadings[:, 0], loadings[:, 1], labels,
            categories=categories, labels_text=labels_text,
            axis_labels=(f"{backend} 1", f"{backend} 2"),
            max_points=int(opts.get("max_points", 3000)),
            seed=int(opts.get("seed", 0)))
        blocks = [note, Svg(svg, caption=f"{backend} embedding")]
        return ReportSection("embedding", "Embedding", blocks)


__all__ = ["EmbeddingSection"]
