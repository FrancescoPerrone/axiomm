"""The ``html`` report backend (stage two, S4).

Assembles sections into one **self-contained** page: inline CSS, figures embedded
as base64 data URIs, no external asset references. Pure string building — it needs
no matplotlib (section renderers produce figure bytes; this only embeds them).

By default the page is **interactive** (``ReportConfig.interactive``): each section
is a draggable module and the title/lede/section text edit in place, persisted
per-viewer — see :mod:`axiomm.analysis.reporting.interactive`. The theme is
token-based and adapts to the viewer's light/dark preference.
"""

from __future__ import annotations

import base64
from html import escape

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.reporting.interactive import INTERACTIVE_CSS, INTERACTIVE_JS
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
:root {
  --bg:#f5f7f8; --surface:#ffffff; --ink:#14181d; --muted:#5c6673; --border:#dbe1e7;
  --accent:#0d7d88; --accent-soft:#e4f1f2; --peak-window:#cf9b3a;
  --good:#1a7f4b; --warn:#b06a1a; --bad:#b23a3a;
  --sans:'IBM Plex Sans',system-ui,-apple-system,sans-serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
  color-scheme: light dark;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --bg:#0e1114; --surface:#161a1f; --ink:#e7ebef; --muted:#97a2af; --border:#29313a;
  --accent:#3bbcc9; --accent-soft:#123236; --peak-window:#d9a441;
  --good:#4cc38a; --warn:#e0a45c; --bad:#e06868;
}}
:root[data-theme="dark"]{
  --bg:#0e1114; --surface:#161a1f; --ink:#e7ebef; --muted:#97a2af; --border:#29313a;
  --accent:#3bbcc9; --accent-soft:#123236; --peak-window:#d9a441;
  --good:#4cc38a; --warn:#e0a45c; --bad:#e06868;
}
body { background:var(--bg); color:var(--ink); font-family:var(--sans);
  font-size:15px; line-height:1.6; margin:0; padding:2.5rem 1.25rem 4rem;
  max-width:46rem; margin-inline:auto; }
.eyebrow { font-family:var(--mono); font-size:.72rem; letter-spacing:.14em;
  text-transform:uppercase; color:var(--accent); margin:0 0 .35rem; }
h1 { font-size:1.9rem; font-weight:600; margin:0 0 .4rem; letter-spacing:-.01em;
  text-wrap:balance; }
.lede { color:var(--muted); margin:0 0 1.5rem; max-width:40rem; }
.report-grid { display:flex; flex-direction:column; gap:1.25rem; }
section { background:var(--surface); border:1px solid var(--border); border-radius:10px;
  padding:1.4rem 1.5rem; display:flex; flex-direction:column; gap:.7rem; }
h2 { font-size:1.05rem; font-weight:600; margin:0 0 .2rem; padding-left:.7rem;
  border-left:3px solid var(--accent); line-height:1.25; }
section p { margin:0; }
.muted, p.muted { color:var(--muted); font-size:.9em; }
table { border-collapse:collapse; width:100%; font-size:.86rem;
  font-variant-numeric:tabular-nums; display:block; overflow-x:auto; }
caption { font-family:var(--mono); font-size:.7rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); text-align:left; padding-bottom:.4rem; }
th, td { border-bottom:1px solid var(--border); padding:.38rem .8rem; text-align:right;
  white-space:nowrap; }
th { font-weight:500; color:var(--muted); font-size:.76rem; letter-spacing:.03em; }
th:first-child, td:first-child { text-align:left; }
tbody tr:last-child td { border-bottom:none; }
figure { margin:0; border:1px solid var(--border); border-radius:8px; padding:.75rem;
  background:var(--bg); }
figcaption { font-family:var(--mono); font-size:.72rem; color:var(--muted);
  padding-top:.5rem; letter-spacing:.06em; text-transform:uppercase; }
img, svg { max-width:100%; height:auto; display:block; margin-inline:auto; }
.chip { display:inline-block; padding:.05em .55em; border-radius:999px; font-family:var(--mono);
  font-size:.72rem; margin:0 .2em .25em 0; border:1px solid; }
.chip-good { color:var(--good); border-color:color-mix(in srgb,var(--good) 45%,transparent); }
.chip-warn { color:var(--warn); border-color:color-mix(in srgb,var(--warn) 45%,transparent); }
.chip-bad  { color:var(--bad);  border-color:color-mix(in srgb,var(--bad) 45%,transparent); }
.rel-cluster { display:flex; flex-direction:column; gap:.4rem; padding:.6rem 0; }
.rel-cluster + .rel-cluster { border-top:1px solid var(--border); }
.rel-head { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }
.rel-elems { display:flex; flex-wrap:wrap; gap:.35rem 1rem; }
.rel-el { display:inline-flex; align-items:center; gap:.4rem; white-space:nowrap; font-size:.92em; }
.rel-el .chip { margin:0; }
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


def _editable(interactive: bool, eid: str) -> str:
    return f' data-editable="{escape(eid)}"' if interactive else ""


def _render_section(s: ReportSection, interactive: bool) -> str:
    parts, pnum = [], 0
    for b in s.blocks:
        if isinstance(b, str):
            pnum += 1
            parts.append(f"<p{_editable(interactive, f'{s.id}-p{pnum}')}>{escape(b)}</p>")
        else:
            parts.append(_render_block(b))
    body = "".join(parts) or '<p class="muted">(nothing to show)</p>'
    handle = '<div class="module-handle" aria-hidden="true"></div>' if interactive else ""
    return (f'<section class="module" id="{escape(s.id)}" data-module="{escape(s.id)}">'
            f'{handle}<h2{_editable(interactive, f"{s.id}-title")}>{escape(s.title)}</h2>'
            f'{body}</section>')


class HtmlReporter:
    """Self-contained single-page HTML backend (interactive by default)."""

    name = "html"

    def assemble(self, sections: list[ReportSection], config: ReportConfig) -> Report:
        interactive = bool(config.interactive)
        title = escape(config.title)

        head_bits = []
        if config.eyebrow:
            head_bits.append(f'<p class="eyebrow"{_editable(interactive, "page-eyebrow")}>'
                             f'{escape(config.eyebrow)}</p>')
        head_bits.append(f'<h1{_editable(interactive, "page-title")}>{title}</h1>')
        if config.subtitle:
            head_bits.append(f'<p class="lede"{_editable(interactive, "page-lede")}>'
                             f'{escape(config.subtitle)}</p>')

        if sections:
            grid_body = "".join(_render_section(s, interactive) for s in sections)
        else:
            grid_body = '<p class="muted">No sections to display.</p>'
        grid = (f'<div class="report-grid" id="report-grid" data-report-id="{title}">'
                f'{grid_body}</div>')

        style = _STYLE + (("\n" + INTERACTIVE_CSS) if interactive else "")
        script = f"<script>{INTERACTIVE_JS}</script>\n" if interactive else ""
        content = (
            "<!doctype html>\n<html lang=\"en\">\n<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{title}</title>\n<style>{style}</style>\n</head>\n<body>\n"
            f"{''.join(head_bits)}\n{grid}\n{script}</body>\n</html>\n"
        )
        return Report(
            backend="html", content=content, mime="text/html", sections=list(sections),
            provenance=AnalysisProvenance(
                tool="axiomm.analysis.reporting", backend="html",
                params={"sections": [s.id for s in sections], "theme": config.theme,
                        "interactive": interactive}),
        )


__all__ = ["HtmlReporter"]
