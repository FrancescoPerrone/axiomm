"""Decomposition section — scree / explained variance (stage two, S4c).

Shows how much of the signal the kept components capture: a scree bar chart with
a cumulative line, and a per-component explained-variance table. Honours a
``max_components`` option (customisation seam) to cap how many are shown.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.reporting.figures import figure_to_png, new_agg_figure
from axiomm.analysis.reporting.models import Figure, ReportSection, Table


class DecompositionSection:
    id = "decomposition"

    def applies(self, result) -> bool:
        return getattr(result, "decomposition", None) is not None

    def render(self, result, config) -> ReportSection:
        decomp = result.decomposition
        ev = np.asarray(decomp.explained_variance_ratio, dtype=float)
        kept = int(getattr(decomp, "n_components", len(ev)))
        opts = config.options_for(self.id)
        show = min(int(opts.get("max_components", len(ev))), len(ev))

        cum = np.cumsum(ev)
        blocks: list = [
            f"{kept} components kept, capturing {cum[-1] * 100:.1f}% of the variance."
        ]

        diags: list[Diagnostic] = []
        try:
            blocks.append(Figure(_scree_png(ev, show), alt="scree plot",
                                 caption="explained variance per component"))
        except AnalysisDependencyError as exc:
            diags.append(Diagnostic("warning", "figure_skipped_dependency", str(exc)))

        rows = [[i + 1, round(ev[i] * 100, 2), round(cum[i] * 100, 2)] for i in range(show)]
        blocks.append(Table(["component", "variance %", "cumulative %"], rows,
                           "explained variance"))
        return ReportSection("decomposition", "Decomposition", blocks, diagnostics=diags)


def _scree_png(ev: np.ndarray, show: int) -> bytes:
    fig = new_agg_figure(figsize=(5.5, 3.2))
    ax = fig.add_subplot(111)
    idx = np.arange(1, show + 1)
    ax.bar(idx, ev[:show] * 100, color="#0d7d88", width=0.7)
    ax.set_xlabel("component")
    ax.set_ylabel("variance %")
    ax.set_xticks(idx)
    ax2 = ax.twinx()
    ax2.plot(idx, np.cumsum(ev[:show]) * 100, color="#b4632f", marker="o", markersize=3)
    ax2.set_ylabel("cumulative %")
    ax2.set_ylim(0, 100)
    return figure_to_png(fig)


__all__ = ["DecompositionSection"]
