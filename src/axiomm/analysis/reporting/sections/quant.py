"""Quantification section — per-cluster element / oxide wt% (stage two, S4d).

The wt% are an *uncorrected* theoretical sensitivity-ratio estimate (no matrix
correction), never a validated composition — the reliability section qualifies
them. ``observation_status`` records how each element was observed.
"""

from __future__ import annotations

from axiomm.analysis.reporting.models import ReportSection, Table


class QuantSection:
    id = "quant"

    def applies(self, result) -> bool:
        return bool(getattr(result, "quantification", None))

    def render(self, result, config) -> ReportSection:
        rows = []
        for q in result.quantification:
            cid = q.cluster_id
            status = dict(getattr(q, "observation_status", {}) or {})
            for el in sorted(q.wt_percent_element):
                rows.append([cid, el,
                             round(float(q.wt_percent_element.get(el, 0.0)), 2),
                             round(float(q.wt_percent_oxide.get(el, 0.0)), 2),
                             status.get(el, "")])
        table = Table(["cluster", "element", "wt% element", "wt% oxide", "observed as"],
                      rows, "uncorrected wt% estimate")
        note = ("Uncorrected sensitivity-ratio estimate (no matrix correction) — an "
                "exploratory read-out, not a standards-validated composition.")
        return ReportSection("quant", "Quantification", [note, table])


__all__ = ["QuantSection"]
