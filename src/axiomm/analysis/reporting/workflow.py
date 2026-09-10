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


__all__ = [
    "WorkflowEdge", "WorkflowGraph", "WorkflowNode",
    "workflow_canvas_html", "workflow_from_result", "workflow_svg",
]
