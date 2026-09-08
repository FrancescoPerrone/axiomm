"""Format-agnostic report data model (stage two, S4).

A report is a list of :class:`ReportSection`, each a sequence of *blocks* — plain
text, a :class:`Table`, or a :class:`Figure` (raw image bytes). Blocks carry no
markup, so any backend (HTML first; Markdown / PDF later) can render the same
sections. :class:`ReportConfig` selects and orders sections and leaves a theme
hook for the deferred styling pass. :class:`Report` is the assembled artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic


@dataclass(frozen=True)
class Figure:
    """An image block — raw bytes so it can be embedded, never linked."""

    data: bytes
    mime: str = "image/png"
    alt: str = ""
    caption: str = ""


@dataclass(frozen=True)
class Table:
    """A simple tabular block."""

    headers: list[str]
    rows: list[list]
    caption: str = ""


#: One renderable unit of a section. ``str`` is a paragraph of plain text.
Block = str | Figure | Table


@dataclass
class ReportSection:
    """One stage's (or aspect's) contribution to a report."""

    id: str
    title: str
    blocks: list[Block] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class ReportConfig:
    """What goes in a report and in what order. Style is a deferred seam."""

    title: str = "AXIOMM run report"
    include: tuple[str, ...] | None = None   # section ids to keep (None = all applicable)
    exclude: tuple[str, ...] = ()            # section ids to drop
    sections: tuple[str, ...] | None = None  # explicit order (None = registration order)
    embed_figures: bool = True               # figures inline as data URIs (only mode for now)
    theme: str | None = None                 # reserved for the later styling pass
    options: dict = field(default_factory=dict)  # per-section settings: {section_id: {...}}
    metadata: dict = field(default_factory=dict)

    def options_for(self, section_id: str) -> dict:
        """Per-section options (customisation seam); ``{}`` when none given."""
        opts = self.options.get(section_id, {})
        return dict(opts) if isinstance(opts, dict) else {}


@dataclass
class Report:
    """An assembled report artifact plus its provenance and diagnostics."""

    backend: str
    content: str
    mime: str = "text/html"
    sections: list[ReportSection] = field(default_factory=list)
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def write(self, path, *, overwrite: bool = False) -> Path:
        """Write the report to ``path``; refuse silent overwrite."""
        path = Path(path)
        if path.exists() and not overwrite:
            raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.content, encoding="utf-8")
        return path


__all__ = ["Block", "Figure", "Report", "ReportConfig", "ReportSection", "Table"]
