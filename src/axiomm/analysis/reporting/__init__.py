"""Reporting subsystem (stage two, S4).

Turns a run — a ``PipelineResult`` or a single stage's output — into a readable
report. A report is composed of per-stage **sections** assembled by a pluggable
**backend** (``html`` first). New formats register in :data:`reporters`; new
stage sections register in :data:`sections`; both resolve lazily so importing
this package never pulls in matplotlib.

    from axiomm.analysis.reporting import render_report
    report = render_report(result, backend="html")
    report.write("run.html")
"""

from __future__ import annotations

from axiomm.analysis.reporting.base import Reporter, SectionRenderer
from axiomm.analysis.reporting.core import render_report
from axiomm.analysis.reporting.hub import HubEntry, build_hub
from axiomm.analysis.reporting.models import (
    Block,
    Figure,
    Html,
    Report,
    ReportConfig,
    ReportSection,
    Svg,
    Table,
)
from axiomm.analysis.reporting.registry import reporters, sections

__all__ = [
    "Block",
    "Figure",
    "Html",
    "HubEntry",
    "Report",
    "ReportConfig",
    "ReportSection",
    "Reporter",
    "SectionRenderer",
    "Svg",
    "Table",
    "build_hub",
    "render_report",
    "reporters",
    "sections",
]
