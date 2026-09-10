"""Auto-generated workflow graph from a run's provenance (stage two).

Turns what a run actually did into a node-and-edge **workflow figure** — which
AXIOMM tools were used, how they connect, with which backends/parameters. The
graph is a general DAG (it renders branches, so hierarchical clustering or any
free-composed tool use lays out too, not just the linear pipeline).

Two outputs:

* :func:`workflow_svg` — one self-contained, theme-aware **SVG**: the
  publication-ready vector figure that *is* the export. ``theme="clean"`` is a
  crisp UML-like look; ``theme="sketch"`` is an ink-and-watercolour look (SVG
  turbulence wobble + layered washes). Each theme exports independently.
* :func:`workflow_canvas_html` — an editable canvas fragment (HTML nodes with
  ``contenteditable`` title/sub over an SVG edge layer, ``data-*`` hooks for a
  thin drag layer). The UX/demo styles it and wires drag + a theme switch.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from html import escape


@dataclass(frozen=True)
class WorkflowNode:
    id: str
    title: str
    sublabel: str = ""
    kind: str = "step"


@dataclass(frozen=True)
class WorkflowEdge:
    src: str
    dst: str


@dataclass
class WorkflowGraph:
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)


def workflow_from_result(result) -> WorkflowGraph:
    """Build the workflow graph a :class:`PipelineResult` implies (from its config)."""
    cfg = dict(getattr(result, "config", {}) or {})
    n_clusters = len(getattr(result, "clusters", []) or [])
    nodes = [
        WorkflowNode("signal", "Signal", "spectrum image", "input"),
        WorkflowNode("reduce", "Decomposition",
                     f"{cfg.get('reduction', 'pca')} · {cfg.get('components', '?')} components", "reduce"),
        WorkflowNode("cluster", "Clustering",
                     f"{cfg.get('clustering', 'gmm')} · {cfg.get('groups', '?')} groups", "cluster"),
        WorkflowNode("means", "Cluster spectra", f"{n_clusters} clusters", "aggregate"),
    ]
    edges = [WorkflowEdge("signal", "reduce"), WorkflowEdge("reduce", "cluster"),
             WorkflowEdge("cluster", "means")]
    if getattr(result, "minerals", None) is not None:
        nodes += [
            WorkflowNode("peaks", "Peak intensities", "net line intensities", "measure"),
            WorkflowNode("quant", "Quantification",
                         f"Cliff-Lorimer · {cfg.get('beam_energy_kev', '?')} keV", "quant"),
            WorkflowNode("reliability", "Reliability gate", "per-cluster grading", "gate"),
            WorkflowNode("minerals", "Mineral match", f"ref: {cfg.get('reference', '?')}", "match"),
            WorkflowNode("phase", "Phase map", "per-pixel phases", "output"),
        ]
        edges += [WorkflowEdge("means", "peaks"), WorkflowEdge("peaks", "quant"),
                  WorkflowEdge("quant", "reliability"), WorkflowEdge("reliability", "minerals"),
                  WorkflowEdge("minerals", "phase")]
    return WorkflowGraph(nodes, edges)


_W, _H, _VGAP, _HGAP, _PAD = 230, 54, 40, 40, 22


def _layout(graph: WorkflowGraph):
    """Layered top-down layout by longest-path depth (renders general DAGs)."""
    depth = {n.id: 0 for n in graph.nodes}
    changed = True
    while changed:                       # relax to longest path from any root
        changed = False
        for e in graph.edges:
            if e.src in depth and e.dst in depth and depth[e.dst] < depth[e.src] + 1:
                depth[e.dst] = depth[e.src] + 1
                changed = True
    by_level: dict[int, list[str]] = defaultdict(list)
    for n in graph.nodes:
        by_level[depth[n.id]].append(n.id)
    max_w = max((len(v) for v in by_level.values()), default=1)
    n_levels = (max(by_level) + 1) if by_level else 1
    pos: dict[str, tuple[float, float]] = {}
    for lvl, ids in by_level.items():
        offset = (max_w - len(ids)) / 2
        for j, nid in enumerate(ids):
            pos[nid] = (_PAD + (offset + j) * (_W + _HGAP), _PAD + lvl * (_H + _VGAP))
    width = 2 * _PAD + max_w * _W + max(max_w - 1, 0) * _HGAP
    height = 2 * _PAD + n_levels * _H + max(n_levels - 1, 0) * _VGAP
    return pos, width, height


def _edge_path(pos, e: WorkflowEdge) -> str:
    x0, y0 = pos[e.src]
    x1, y1 = pos[e.dst]
    sx, sy, tx, ty = x0 + _W / 2, y0 + _H, x1 + _W / 2, y1
    if abs(sx - tx) < 0.5:
        return f"M {sx:.1f} {sy:.1f} L {tx:.1f} {ty:.1f}"
    my = (sy + ty) / 2
    return f"M {sx:.1f} {sy:.1f} C {sx:.1f} {my:.1f} {tx:.1f} {my:.1f} {tx:.1f} {ty:.1f}"


def workflow_svg(graph: WorkflowGraph, *, theme: str = "clean", title: str | None = None) -> str:
    """Render the workflow as one self-contained, exportable SVG (``clean``/``sketch``)."""
    pos, width, height = _layout(graph)
    top = 26 if title else 0
    height += top
    sketch = theme == "sketch"
    ink = "var(--wf-ink, #4a4363)"
    node_fill = "url(#wf-wash)" if sketch else "var(--surface, #ffffff)"
    node_stroke = ink if sketch else "var(--accent, #0d7d88)"
    edge_stroke = ink if sketch else "var(--accent, #0d7d88)"
    rx = 13 if sketch else 8
    marker = f"arrow-{theme}"

    defs = [f'<marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" '
            f'fill="{edge_stroke}"/></marker>']
    group_attr = ""
    if sketch:
        defs.append('<linearGradient id="wf-wash" x1="0" y1="0" x2="0" y2="1">'
                    '<stop offset="0" stop-color="#8a7fae" stop-opacity="0.10"/>'
                    '<stop offset="1" stop-color="#5a5078" stop-opacity="0.26"/></linearGradient>')
        defs.append('<filter id="wf-wobble" x="-5%" y="-5%" width="110%" height="110%">'
                    '<feTurbulence type="fractalNoise" baseFrequency="0.014" numOctaves="2" '
                    'seed="7" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" '
                    'scale="2.6"/></filter>')
        group_attr = ' filter="url(#wf-wobble)"'

    parts = [
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" width="100%" class="wf-graph" '
        f'preserveAspectRatio="xMidYMin meet" role="img" '
        f'font-family="\'IBM Plex Sans\', system-ui, sans-serif">',
        f'<defs>{"".join(defs)}</defs>',
    ]
    if title:
        parts.append(f'<text x="{_PAD}" y="16" font-size="13" font-weight="600" '
                     f'fill="currentColor">{escape(title)}</text>')
    parts.append(f'<g transform="translate(0 {top})"{group_attr}>')
    for e in graph.edges:
        parts.append(f'<path class="wf-edge" data-from="{e.src}" data-to="{e.dst}" '
                     f'd="{_edge_path(pos, e)}" fill="none" stroke="{edge_stroke}" '
                     f'stroke-width="{2 if sketch else 1.5}" stroke-opacity="0.8" '
                     f'stroke-linecap="round" marker-end="url(#{marker})"/>')
    for n in graph.nodes:
        x, y = pos[n.id]
        parts.append(
            f'<g class="wf-node" data-node="{n.id}" transform="translate({x:.1f} {y:.1f})">'
            f'<rect width="{_W}" height="{_H}" rx="{rx}" fill="{node_fill}" '
            f'stroke="{node_stroke}" stroke-width="{1.8 if sketch else 1.2}"/>'
            f'<text x="13" y="22" font-size="13" font-weight="600" fill="currentColor">'
            f'{escape(n.title)}</text>'
            f'<text x="13" y="40" font-size="10.5" fill="currentColor" fill-opacity="0.6" '
            f'font-family="\'IBM Plex Mono\', ui-monospace, monospace">{escape(n.sublabel)}</text>'
            f'</g>')
    parts.append("</g></svg>")
    return "".join(parts)


def workflow_canvas_html(graph: WorkflowGraph) -> str:
    """An editable-canvas fragment: HTML nodes (contenteditable) over an SVG edge layer.

    The UX/demo supplies CSS + a drag layer + a clean/sketch theme switch; this only
    emits the structure with ``data-*`` hooks (node ``data-node``/``data-x``/``data-y``,
    edge ``data-from``/``data-to``).
    """
    pos, width, height = _layout(graph)
    edges = "".join(
        f'<path class="wf-edge" data-from="{e.src}" data-to="{e.dst}" fill="none" '
        f'marker-end="url(#wf-arrow)"/>' for e in graph.edges)
    nodes = []
    for n in graph.nodes:
        x, y = pos[n.id]
        nodes.append(
            f'<div class="wf-node" data-node="{n.id}" data-x="{x:.0f}" data-y="{y:.0f}" '
            f'style="left:{x:.0f}px; top:{y:.0f}px">'
            f'<div class="wf-title" contenteditable="true" spellcheck="false">{escape(n.title)}</div>'
            f'<div class="wf-sub" contenteditable="true" spellcheck="false">{escape(n.sublabel)}</div>'
            f'</div>')
    return (f'<div class="wf-canvas" style="width:{width:.0f}px; height:{height:.0f}px">'
            f'<svg class="wf-edges" width="{width:.0f}" height="{height:.0f}">'
            f'<defs><marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z"/></marker>'
            f'</defs>{edges}</svg>{"".join(nodes)}</div>')


_WF_PAGE_CSS = """
:root{ --bg:#f5f7f8; --surface:#ffffff; --ink:#14181d; --muted:#5c6673; --border:#dbe1e7;
  --accent:#0d7d88; --accent-soft:#e4f1f2; --wf-ink:#4a4363;
  --sans:'IBM Plex Sans',system-ui,sans-serif; --mono:'IBM Plex Mono',ui-monospace,monospace; color-scheme:light dark;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){ --bg:#0e1114; --surface:#161a1f; --ink:#e7ebef;
  --muted:#97a2af; --border:#29313a; --accent:#3bbcc9; --accent-soft:#123236; --wf-ink:#b7add6;}}
:root[data-theme="dark"]{ --bg:#0e1114; --surface:#161a1f; --ink:#e7ebef; --muted:#97a2af; --border:#29313a;
  --accent:#3bbcc9; --accent-soft:#123236; --wf-ink:#b7add6;}
body{background:var(--bg); color:var(--ink); font-family:var(--sans); margin:0; padding:2.5rem 1.25rem 4rem;}
.wf-head{max-width:46rem; margin:0 auto 1.25rem;}
.wf-head .eyebrow{font-family:var(--mono); font-size:.72rem; letter-spacing:.14em; text-transform:uppercase;
  color:var(--accent); margin:0 0 .35rem;}
.wf-head h1{font-size:1.9rem; font-weight:600; margin:0 0 .4rem; letter-spacing:-.01em;}
.wf-head .lede{color:var(--muted); margin:0; max-width:40rem;}
.wf-head [contenteditable]{outline:none; border-radius:5px; transition:background .15s;}
.wf-head [contenteditable]:hover{background:color-mix(in srgb,var(--accent) 8%,transparent);}
.wf-head [contenteditable]:focus{background:color-mix(in srgb,var(--accent) 6%,transparent);
  box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 40%,transparent);}
.wf-canvas{position:relative; width:100%; min-height:calc(100vh - 12rem);}
.wf-edges{position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none;}
.wf-edges .wf-edge{fill:none; stroke:var(--accent); stroke-width:1.6; stroke-linecap:round; stroke-opacity:.85;}
.wf-edges marker path{fill:var(--accent);}
.wf-node{position:absolute; width:230px; box-sizing:border-box; background:var(--surface);
  border:1.2px solid var(--accent); border-radius:8px; padding:9px 13px; cursor:grab; user-select:none;
  box-shadow:0 1px 3px rgba(0,0,0,.05);}
.wf-title{font-weight:600; font-size:13px; outline:none;}
.wf-sub{font-family:var(--mono); font-size:10.5px; color:var(--muted); outline:none; margin-top:2px; min-height:1em;}
.wf-title[contenteditable]:focus,.wf-sub[contenteditable]:focus{background:color-mix(in srgb,var(--accent) 8%,transparent); border-radius:3px;}
.wf-canvas.sketch{filter:url(#wf-wobble);}
.sketch .wf-node{border:1.8px solid var(--wf-ink); border-radius:14px;
  background:linear-gradient(180deg, rgba(138,127,174,.12), rgba(90,80,120,.28)); box-shadow:none;}
.sketch .wf-sub{color:var(--muted);}
.sketch .wf-edges .wf-edge{stroke:var(--wf-ink); stroke-width:2;}
.sketch .wf-edges marker path{fill:var(--wf-ink);}
.wf-toast{position:fixed; bottom:1.1rem; left:50%; transform:translateX(-50%); background:var(--ink); color:var(--bg);
  font-family:var(--mono); font-size:.72rem; padding:.5rem .9rem; border-radius:8px; opacity:0; transition:opacity .25s; pointer-events:none;}
.wf-toast.show{opacity:.94;}
.wf-controls{position:fixed; bottom:1rem; right:1rem; display:flex; gap:.4rem; align-items:center;
  opacity:0; transition:opacity .25s; z-index:30;}
body:hover .wf-controls{opacity:.5;} .wf-controls:hover{opacity:1;}
@media (hover:none){ .wf-controls{opacity:.45;} }
.wf-controls .switch{display:inline-flex; gap:.25rem;}
.wf-controls button{border:1px solid var(--border); background:var(--surface); color:var(--muted);
  border-radius:999px; padding:.28rem .7rem; cursor:pointer; font-family:var(--mono); font-size:.66rem;
  letter-spacing:.04em;}
.wf-controls .switch button.on{border-color:var(--accent); color:var(--accent); background:var(--accent-soft);}
""".strip()

_WF_PAGE_JS = r"""
(function(){
  var canvas=document.querySelector('.wf-canvas'); if(!canvas) return;
  var W=230;
  function rect(id){var d=canvas.querySelector('.wf-node[data-node="'+id+'"]');return {x:+d.dataset.x,y:+d.dataset.y,w:d.offsetWidth,h:d.offsetHeight};}
  function edges(){canvas.querySelectorAll('.wf-edge').forEach(function(p){var a=rect(p.dataset.from),b=rect(p.dataset.to);
    var sx=a.x+a.w/2,sy=a.y+a.h,tx=b.x+b.w/2,ty=b.y,d;
    if(Math.abs(sx-tx)<0.5)d='M '+sx+' '+sy+' L '+tx+' '+ty;
    else{var my=(sy+ty)/2;d='M '+sx+' '+sy+' C '+sx+' '+my+' '+tx+' '+my+' '+tx+' '+ty;}
    p.setAttribute('d',d);});}
  edges(); window.addEventListener('resize',edges);
  var drag=null,sx,sy,ox,oy;
  canvas.addEventListener('pointerdown',function(e){if(e.target.closest('.wf-title,.wf-sub'))return;
    var d=e.target.closest('.wf-node');if(!d)return;e.preventDefault();drag=d;sx=e.clientX;sy=e.clientY;
    ox=+d.dataset.x;oy=+d.dataset.y;d.style.cursor='grabbing';d.style.zIndex=10;
    document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up);});
  function mv(e){if(!drag)return;var nx=Math.max(0,ox+(e.clientX-sx)),ny=Math.max(0,oy+(e.clientY-sy));
    drag.dataset.x=nx;drag.dataset.y=ny;drag.style.left=nx+'px';drag.style.top=ny+'px';edges();}
  function up(){document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);
    if(drag){drag.style.cursor='grab';drag.style.zIndex='';}drag=null;}

  var sw=document.querySelector('.switch');
  if(sw)sw.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
    canvas.classList.toggle('sketch',b.dataset.theme==='sketch');
    sw.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===b);});});

  function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function buildSVG(){
    var sketch=canvas.classList.contains('sketch');
    var ns=[],minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9,pos={};
    canvas.querySelectorAll('.wf-node').forEach(function(d){var x=+d.dataset.x,y=+d.dataset.y,h=d.offsetHeight;
      var n={id:d.dataset.node,x:x,y:y,h:h,t:d.querySelector('.wf-title').textContent,s:d.querySelector('.wf-sub').textContent};
      ns.push(n);pos[n.id]=n;minx=Math.min(minx,x);miny=Math.min(miny,y);maxx=Math.max(maxx,x+W);maxy=Math.max(maxy,y+h);});
    var pad=20,ox=pad-minx,oy=pad-miny,w=(maxx-minx)+2*pad,h=(maxy-miny)+2*pad;
    var ink=sketch?'#4a4363':'#0d7d88',fill=sketch?'#ece8f4':'#ffffff';
    var ed='';canvas.querySelectorAll('.wf-edge').forEach(function(p){var a=pos[p.dataset.from],b=pos[p.dataset.to];if(!a||!b)return;
      var sx=a.x+ox+W/2,sy=a.y+oy+a.h,tx=b.x+ox+W/2,ty=b.y+oy,d;
      if(Math.abs(sx-tx)<0.5)d='M '+sx+' '+sy+' L '+tx+' '+ty;else{var my=(sy+ty)/2;d='M '+sx+' '+sy+' C '+sx+' '+my+' '+tx+' '+my+' '+tx+' '+ty;}
      ed+='<path d="'+d+'" fill="none" stroke="'+ink+'" stroke-width="'+(sketch?2:1.5)+'" marker-end="url(#ar)"/>';});
    var nd='';ns.forEach(function(n){var x=n.x+ox,y=n.y+oy;
      nd+='<g transform="translate('+x+' '+y+')"><rect width="'+W+'" height="'+n.h+'" rx="'+(sketch?14:8)+'" fill="'+fill+'" stroke="'+ink+'" stroke-width="'+(sketch?1.8:1.2)+'"/>'
        +'<text x="13" y="22" font-size="13" font-weight="600" fill="#14181d">'+esc(n.t)+'</text>'
        +'<text x="13" y="40" font-size="10.5" fill="#5c6673" font-family="monospace">'+esc(n.s)+'</text></g>';});
    var flt=sketch?'<filter id="wob"><feTurbulence type="fractalNoise" baseFrequency="0.013" numOctaves="2" seed="7" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="2.4"/></filter>':'';
    var ga=sketch?' filter="url(#wob)"':'';
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 '+w+' '+h+'" width="'+w+'" height="'+h+'" font-family="sans-serif">'
      +'<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="'+ink+'"/></marker>'+flt+'</defs><g'+ga+'>'+ed+nd+'</g></svg>';
  }
  function toast(msg){var t=document.querySelector('.wf-toast');t.textContent=msg;t.classList.add('show');setTimeout(function(){t.classList.remove('show');},1900);}
  var ex=document.querySelector('.export');
  if(ex)ex.addEventListener('click',function(){var svg=buildSVG();
    if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(svg).then(function(){toast('Current figure copied as SVG — paste into a .svg file');},function(){toast('Copy blocked here; in the app this saves a file');});}
    else toast('In the app this saves an .svg file');});
})();
""".strip()


def render_workflow_page(graph: WorkflowGraph, *, title: str = "Analysis workflow",
                         eyebrow: str = "AXIOMM",
                         subtitle: str = "The AXIOMM tools applied to this analysis, "
                                         "and how they connect.") -> str:
    """A full self-contained editable-canvas page.

    Opens like a report — a clean masthead (eyebrow, editable title + lede) above the
    workflow figure — with **no toolbar and no instructions**. Every label edits in
    place; nodes drag (edges follow); a clean/sketch switch and an export-to-vector-SVG
    control are discovered in a corner on hover, never announced.
    """
    filt = ('<svg width="0" height="0" aria-hidden="true"><defs>'
            '<filter id="wf-wobble" x="-4%" y="-4%" width="108%" height="108%">'
            '<feTurbulence type="fractalNoise" baseFrequency="0.013" numOctaves="2" seed="7" '
            'result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="2.4"/></filter>'
            '</defs></svg>')
    head = (f'<div class="wf-head"><p class="eyebrow">{escape(eyebrow)}</p>'
            f'<h1 contenteditable="true" spellcheck="false">{escape(title)}</h1>'
            f'<p class="lede" contenteditable="true" spellcheck="false">{escape(subtitle)}</p></div>')
    controls = ('<div class="wf-controls"><div class="switch">'
                '<button class="on" data-theme="clean">clean</button>'
                '<button data-theme="sketch">sketch</button></div>'
                '<button class="export">export</button></div>')
    # full-screen page: let the CSS size the canvas (drop canvas_html's fixed size)
    canvas = re.sub(r'(<div class="wf-canvas") style="[^"]*"', r"\1", workflow_canvas_html(graph))
    return (f"<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title><style>{_WF_PAGE_CSS}</style></head><body>\n"
            f"{filt}{head}{canvas}<div class=\"wf-toast\"></div>{controls}\n"
            f"<script>{_WF_PAGE_JS}</script>\n</body></html>\n")


__all__ = [
    "WorkflowEdge", "WorkflowGraph", "WorkflowNode",
    "render_workflow_page", "workflow_canvas_html", "workflow_from_result", "workflow_svg",
]
