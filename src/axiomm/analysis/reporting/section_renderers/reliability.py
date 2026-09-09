"""Reliability section — trust verdicts as status chips (stage two, S4d).

The reliability gate's per-cluster and per-element verdicts, shown as semantic
chips (good / caution / invalid — a colour axis separate from the accent) so
"can I trust this" reads at a glance.
"""

from __future__ import annotations

from html import escape

from axiomm.analysis.reporting.models import Html, ReportSection

_GOOD = {"reportable", "reportable_estimate"}
_WARN = {"below_count_floor", "exploratory_only"}


def _chip(status: str, text: str | None = None) -> str:
    cls = "chip-good" if status in _GOOD else "chip-warn" if status in _WARN else "chip-bad"
    return f'<span class="chip {cls}">{escape(text or status)}</span>'


class ReliabilitySection:
    id = "reliability"

    def applies(self, result) -> bool:
        return bool(getattr(result, "reliability", None))

    def render(self, result, config) -> ReportSection:
        blocks: list = ["Reliability verdicts from the quantification gate - a cluster "
                        "mean is never automatically a validated composition."]
        for rep in result.reliability:
            cid = rep.cluster_id
            elems = "".join(
                f'<span class="rel-el">{escape(sym)}{_chip(st)}</span>'
                for sym, st in sorted(dict(rep.element_status).items()))
            reasons = ""
            if getattr(rep, "reasons", ()):
                reasons = f'<span class="muted">{escape("; ".join(rep.reasons))}</span>'
            blocks.append(Html(
                f'<div class="rel-cluster"><div class="rel-head">'
                f'<strong>cluster {cid}</strong>{_chip(rep.cluster_status)}{reasons}</div>'
                f'<div class="rel-elems">{elems}</div></div>'))
        return ReportSection("reliability", "Reliability", blocks)


__all__ = ["ReliabilitySection"]
