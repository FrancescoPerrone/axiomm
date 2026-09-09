"""The reports hub — a general index across many runs (stage two, S4e).

Takes a list of :class:`HubEntry` (one per run) and builds one self-contained,
themed HTML index that links to each run's report. It is deliberately
**general**: entries carry arbitrary ``metadata`` (sample, date, instrument,
group count, …), rendered generically, so the hub captures many samples, users
and data cases rather than one fixed layout. No external assets.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from html import escape

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.reporting.html import _STYLE
from axiomm.analysis.reporting.models import Figure, Report, Svg

_HUB_CSS = """
.hub-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(15rem,1fr)); gap:1rem; }
.hub-card { display:flex; flex-direction:column; gap:.6rem; background:var(--surface);
  border:1px solid var(--border); border-radius:10px; padding:1.1rem 1.2rem; text-decoration:none;
  color:inherit; transition:border-color .15s, box-shadow .15s; }
a.hub-card:hover { border-color:var(--accent); box-shadow:0 6px 20px rgba(0,0,0,.08); }
.hub-thumb { border:1px solid var(--border); border-radius:7px; overflow:hidden; background:var(--bg);
  aspect-ratio:16/10; display:flex; align-items:center; justify-content:center; }
.hub-thumb img, .hub-thumb svg { width:100%; height:100%; object-fit:contain; }
.hub-card h3 { margin:0; font-size:1rem; font-weight:600; }
.hub-summary { margin:0; color:var(--muted); font-size:.9rem; }
.hub-meta { display:flex; flex-wrap:wrap; gap:.3rem .6rem; margin-top:auto; }
.hub-kv { font-family:var(--mono); font-size:.72rem; color:var(--muted); white-space:nowrap; }
.hub-kv b { color:var(--ink); font-weight:500; }
""".strip()


@dataclass
class HubEntry:
    """One run in the hub. ``metadata`` is free-form and rendered generically."""

    title: str
    href: str | None = None
    summary: str | None = None
    metadata: dict = field(default_factory=dict)
    thumbnail: Figure | Svg | None = None


def _thumb_html(thumb) -> str:
    if isinstance(thumb, Svg):
        return f'<div class="hub-thumb">{thumb.markup}</div>'
    if isinstance(thumb, Figure):
        b64 = base64.b64encode(thumb.data).decode("ascii")
        return (f'<div class="hub-thumb"><img src="data:{escape(thumb.mime)};base64,{b64}" '
                f'alt="{escape(thumb.alt)}"></div>')
    return ""


def _entry_html(e: HubEntry) -> str:
    parts = []
    if e.thumbnail is not None:
        parts.append(_thumb_html(e.thumbnail))
    parts.append(f"<h3>{escape(e.title)}</h3>")
    if e.summary:
        parts.append(f'<p class="hub-summary">{escape(e.summary)}</p>')
    if e.metadata:
        chips = "".join(f'<span class="hub-kv">{escape(str(k))} <b>{escape(str(v))}</b></span>'
                        for k, v in e.metadata.items())
        parts.append(f'<div class="hub-meta">{chips}</div>')
    inner = "".join(parts)
    if e.href:
        return f'<a class="hub-card" href="{escape(e.href)}">{inner}</a>'
    return f'<div class="hub-card">{inner}</div>'


def build_hub(entries, *, title: str = "AXIOMM reports", subtitle: str | None = None) -> Report:
    """Build a self-contained HTML index over ``entries`` (one per run)."""
    entries = list(entries)
    head = f"<h1>{escape(title)}</h1>"
    if subtitle:
        head += f'<p class="lede">{escape(subtitle)}</p>'
    if entries:
        body = f'<div class="hub-grid">{"".join(_entry_html(e) for e in entries)}</div>'
    else:
        body = '<p class="muted">No runs yet.</p>'
    content = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escape(title)}</title>\n<style>{_STYLE}\n{_HUB_CSS}</style>\n</head>\n<body>\n"
        f"{head}\n{body}\n</body>\n</html>\n"
    )
    return Report(
        backend="hub", content=content, mime="text/html",
        provenance=AnalysisProvenance(tool="axiomm.analysis.reporting", backend="hub",
                                      params={"n_entries": len(entries)}),
    )


__all__ = ["HubEntry", "build_hub"]
