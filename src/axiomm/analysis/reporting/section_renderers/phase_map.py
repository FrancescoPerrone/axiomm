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
from axiomm.analysis.reporting.figures import categorical_map_png
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
            png = categorical_map_png(pm, list(names))
            blocks.append(Figure(png, alt="phase map", caption="per-pixel phase map"))
        except AnalysisDependencyError as exc:
            diags.append(Diagnostic("warning", "figure_skipped_dependency", str(exc)))
        blocks.append(table)
        return ReportSection("phase_map", "Phase map", blocks, diagnostics=diags)


__all__ = ["PhaseMapSection"]
