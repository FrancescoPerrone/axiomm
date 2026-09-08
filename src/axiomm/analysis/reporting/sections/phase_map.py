"""Phase-map section — the spatial result + modal fractions (stage two, S4b).

Renders the per-pixel phase map as an embedded categorical image with a legend,
plus a per-phase pixel / area-fraction table. Applies only when a phase map was
produced. If matplotlib is unavailable the table still renders and a diagnostic
notes the skipped figure — the report never crashes on a missing optional dep.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.reporting.figures import figure_to_png, import_matplotlib, new_agg_figure
from axiomm.analysis.reporting.models import Figure, ReportSection, Table


class PhaseMapSection:
    id = "phase_map"

    def applies(self, result) -> bool:
        return getattr(result, "phase_map", None) is not None

    def render(self, result, config) -> ReportSection:
        pm = np.asarray(result.phase_map)
        names, counts = np.unique(pm, return_counts=True)
        total = int(counts.sum()) or 1
        order = np.argsort(-counts)
        rows = [[str(names[i]), int(counts[i]), round(100.0 * counts[i] / total, 2)]
                for i in order]
        table = Table(["phase", "pixels", "area %"], rows, "phase modal fractions")

        blocks: list = []
        diags: list[Diagnostic] = []
        try:
            png = _phase_map_png(pm, list(names))
            blocks.append(Figure(png, alt="phase map", caption="per-pixel phase map"))
        except AnalysisDependencyError as exc:
            diags.append(Diagnostic("warning", "figure_skipped_dependency", str(exc)))
        blocks.append(table)
        return ReportSection("phase_map", "Phase map", blocks, diagnostics=diags)


def _phase_map_png(pm: np.ndarray, names: list) -> bytes:
    mpl = import_matplotlib()
    from matplotlib.patches import Patch

    code = {n: i for i, n in enumerate(names)}
    codes = np.vectorize(code.__getitem__)(pm).astype(int)
    cmap = mpl.colormaps["tab20"].resampled(max(len(names), 1))

    fig = new_agg_figure(figsize=(5.0, 4.0))
    ax = fig.add_subplot(111)
    ax.imshow(codes, cmap=cmap, vmin=-0.5, vmax=len(names) - 0.5, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    handles = [Patch(facecolor=cmap(i), label=str(n)) for i, n in enumerate(names)]
    ax.legend(handles=handles, bbox_to_anchor=(1.02, 1.0), loc="upper left",
              fontsize=8, frameon=False)
    return figure_to_png(fig)


__all__ = ["PhaseMapSection"]
