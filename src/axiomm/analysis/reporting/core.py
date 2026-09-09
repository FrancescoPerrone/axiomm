"""The report assembler (stage two, S4).

:func:`render_report` collects the applicable section renderers from the
:data:`sections` registry, renders each, and hands them to the chosen backend
from the :data:`reporters` registry. Section order follows an explicit config
order, else a canonical pipeline order, else registration order.
"""

from __future__ import annotations

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.reporting.models import Report, ReportConfig
from axiomm.analysis.reporting.registry import reporters, sections

#: Canonical section order (pipeline order) used when a config gives none.
DEFAULT_ORDER = (
    "overview", "decomposition", "clustering", "embedding", "cluster_means",
    "peaks", "quant", "reliability", "minerals", "phase_map",
)


def _ordered_ids(config: ReportConfig) -> list[str]:
    registered = set(sections.names())
    if config.sections is not None:
        ordered = [s for s in config.sections if s in registered]
    else:
        ordered = [s for s in DEFAULT_ORDER if s in registered]
        ordered += sorted(registered - set(ordered))
    if config.include is not None:
        keep = set(config.include)
        ordered = [s for s in ordered if s in keep]
    drop = set(config.exclude)
    return [s for s in ordered if s not in drop]


def render_report(result, *, backend: str = "html", config: ReportConfig | None = None) -> Report:
    """Render ``result`` into a :class:`Report` using the named ``backend``."""
    config = config or ReportConfig()
    reporter = reporters.get(backend)
    rendered = []
    for sid in _ordered_ids(config):
        renderer = sections.get(sid)
        if renderer.applies(result):
            rendered.append(renderer.render(result, config))
    report = reporter.assemble(rendered, config)
    if report.provenance is None:
        report.provenance = AnalysisProvenance(
            tool="axiomm.analysis.reporting", backend=backend,
            params={"sections": [s.id for s in rendered]})
    for section in rendered:
        report.diagnostics.extend(section.diagnostics)
    return report


__all__ = ["DEFAULT_ORDER", "render_report"]
