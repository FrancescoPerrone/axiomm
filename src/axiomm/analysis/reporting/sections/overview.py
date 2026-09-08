"""Overview section — the at-a-glance view of a run (stage two, S4b).

Run settings, the per-cluster "what it found" table, and any diagnostics. Applies
to anything that looks like a pipeline result (has clusters or a label map).
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.reporting.models import ReportSection, Table


class OverviewSection:
    id = "overview"

    def applies(self, result) -> bool:
        return hasattr(result, "clusters") or hasattr(result, "label_map")

    def render(self, result, config) -> ReportSection:
        blocks: list = []

        label_map = getattr(result, "label_map", None)
        shape = tuple(int(d) for d in np.asarray(label_map).shape) if label_map is not None else None
        clusters = list(getattr(result, "clusters", []) or [])
        minerals_run = getattr(result, "minerals", None) is not None
        blocks.append(
            f"{len(clusters)} clusters over map {shape}. "
            f"Minerals: {'run' if minerals_run else 'not run'}."
        )

        cfg = getattr(result, "config", {}) or {}
        if cfg:
            blocks.append(Table(["setting", "value"], [[k, cfg[k]] for k in cfg], "run settings"))

        if clusters:
            headers = ["cluster", "pixels", "best match", "score", "reliability"]
            rows = [[c.get("cluster_id"), c.get("pixels"), c.get("best_match"),
                     c.get("score"), c.get("reliability")] for c in clusters]
            blocks.append(Table(headers, rows, "clusters"))

        diags = list(getattr(result, "diagnostics", []) or [])
        if diags:
            rows = [[d.severity, d.code, d.message] for d in diags]
            blocks.append(Table(["severity", "code", "message"], rows, "diagnostics"))

        return ReportSection("overview", "Overview", blocks)


__all__ = ["OverviewSection"]
