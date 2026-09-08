"""The ``html`` report backend (stage two, S4).

Assembles sections into one **self-contained** page: inline CSS, figures embedded
as base64 data URIs, no external asset references. Pure string building — it needs
no matplotlib (section renderers produce figure bytes; this only embeds them).
"""

from __future__ import annotations

import base64
from html import escape

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.reporting.models import (
    Figure,
    Html,
    Report,
    ReportConfig,
    ReportSection,
    Svg,
    Table,
)

_STYLE = """
:root { color-scheme: light dark; }
body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 2rem;
       max-width: 60rem; margin-inline: auto; }
h1 { font-size: 1.5rem; } h2 { font-size: 1.15rem; margin-top: 2rem;
     border-bottom: 1px solid #8884; padding-bottom: .25rem; }
section { margin-bottom: 1.5rem; }
table { border-collapse: collapse; margin: .5rem 0; }
th, td { border: 1px solid #8886; padding: .25rem .6rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
figure { margin: .75rem 0; } figcaption { color: #8a8a8a; font-size: .85em; }
img, svg { max-width: 100%; height: auto; }
.muted { color: #8a8a8a; }
.chip { display: inline-block; padding: .05em .5em; border-radius: 999px;
        font-size: .8em; margin: 0 .2em .2em 0; border: 1px solid #8884; }
.chip-good { color: #1a7f4b; border-color: #1a7f4b66; }
.chip-warn { color: #b06a1a; border-color: #b06a1a66; }
.chip-bad  { color: #b23a3a; border-color: #b23a3a66; }
""".strip()


def _cell(value) -> str:
    return escape(f"{value}")


def _render_table(t: Table) -> str:
    head = "".join(f"<th>{escape(str(h))}</th>" for h in t.headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in row) + "</tr>" for row in t.rows
    )
    caption = f"<caption>{escape(t.caption)}</caption>" if t.caption else ""
    return f"<table>{caption}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _render_figure(f: Figure) -> str:
    b64 = base64.b64encode(f.data).decode("ascii")
    cap = f"<figcaption>{escape(f.caption)}</figcaption>" if f.caption else ""
    return (f'<figure><img src="data:{escape(f.mime)};base64,{b64}" '
            f'alt="{escape(f.alt)}">{cap}</figure>')


def _render_svg(s: Svg) -> str:
    cap = f"<figcaption>{escape(s.caption)}</figcaption>" if s.caption else ""
    return f"<figure>{s.markup}{cap}</figure>"


def _render_block(block) -> str:
    if isinstance(block, Table):
        return _render_table(block)
    if isinstance(block, Figure):
        return _render_figure(block)
    if isinstance(block, Svg):
        return _render_svg(block)
    if isinstance(block, Html):
        return block.markup
    return f"<p>{escape(str(block))}</p>"


def _render_section(s: ReportSection) -> str:
    body = "".join(_render_block(b) for b in s.blocks) or '<p class="muted">(nothing to show)</p>'
    return f'<section id="{escape(s.id)}"><h2>{escape(s.title)}</h2>{body}</section>'


class HtmlReporter:
    """Self-contained single-page HTML backend."""

    name = "html"

    def assemble(self, sections: list[ReportSection], config: ReportConfig) -> Report:
        title = escape(config.title)
        if sections:
            body = "".join(_render_section(s) for s in sections)
        else:
            body = '<p class="muted">No sections to display.</p>'
        content = (
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            f'<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{title}</title>\n<style>{_STYLE}</style>\n</head>\n<body>\n"
            f"<h1>{title}</h1>\n{body}\n</body>\n</html>\n"
        )
        return Report(
            backend="html", content=content, mime="text/html", sections=list(sections),
            provenance=AnalysisProvenance(
                tool="axiomm.analysis.reporting", backend="html",
                params={"sections": [s.id for s in sections], "theme": config.theme}),
        )


__all__ = ["HtmlReporter"]
