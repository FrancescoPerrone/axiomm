"""Protocols for the reporting subsystem (stage two, S4).

A :class:`SectionRenderer` turns one stage's output into a :class:`ReportSection`
and says whether it applies to a given result (so a clusters-only run omits the
mineral sections rather than erroring). A :class:`Reporter` assembles rendered
sections into a :class:`Report` in one output format.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from axiomm.analysis.reporting.models import Report, ReportConfig, ReportSection


@runtime_checkable
class SectionRenderer(Protocol):
    """Renders one stage/aspect of a result into a section."""

    id: str

    def applies(self, result) -> bool:
        """Whether this section has something to say about ``result``."""
        ...

    def render(self, result, config: ReportConfig) -> ReportSection:
        """Produce the section (assumes :meth:`applies` returned True)."""
        ...


@runtime_checkable
class Reporter(Protocol):
    """Assembles rendered sections into a single artifact of one format."""

    name: str

    def assemble(self, sections: list[ReportSection], config: ReportConfig) -> Report:
        ...


__all__ = ["Reporter", "SectionRenderer"]
