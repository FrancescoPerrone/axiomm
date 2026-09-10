"""Auto-generated workflow graph from a run's provenance (stage two).

Turns what a run actually did into a node-and-edge **workflow figure**: which
AXIOMM tools were used, in what order, with which backends/parameters. Rendered as
one self-contained, theme-aware **SVG** — a publication-ready vector figure that is
also the export. Two looks: ``clean`` (crisp, UML-like) and ``sketch`` (hand-drawn
ink-and-wash, via an SVG turbulence-displacement wobble). Nodes carry
``data-node``/``data-x``/``data-y`` and edges ``data-from``/``data-to`` so a thin
canvas layer can make them draggable (edges follow); no such layer is required to
render the figure.
"""

from __future__ import annotations

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


_W, _H, _VGAP, _PAD = 230, 54, 34, 20


def _positions(graph: WorkflowGraph) -> dict[str, tuple[float, float]]:
    return {n.id: (_PAD, _PAD + i * (_H + _VGAP)) for i, n in enumerate(graph.nodes)}


def _edge_path(pos, e: WorkflowEdge) -> str:
    _, y0 = pos[e.src]
    _, y1 = pos[e.dst]
    cx = _PAD + _W / 2
    return f"M {cx:.1f} {y0 + _H:.1f} L {cx:.1f} {y1:.1f}"


def workflow_svg(graph: WorkflowGraph, *, theme: str = "clean", title: str | None = None) -> str:
    """Render the workflow as one self-contained SVG (``clean`` or ``sketch``)."""
    pos = _positions(graph)
    width = _W + 2 * _PAD
    height = _PAD + len(graph.nodes) * (_H + _VGAP)
    if title:
        height += 26
    top = 26 if title else 0

    sketch = theme == "sketch"
    node_fill = "rgba(122,110,150,0.16)" if sketch else "var(--surface, #ffffff)"
    node_stroke = "var(--wf-ink, #4a4363)" if sketch else "var(--accent, #0d7d88)"
    edge_stroke = "var(--wf-ink, #4a4363)" if sketch else "var(--accent, #0d7d88)"
    rx = 11 if sketch else 8
    marker = f"arrow-{theme}"

    defs = [f'<marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0 0 L10 5 L0 10 z" fill="{edge_stroke}"/></marker>']
    group_attr = ""
    if sketch:
        defs.append('<filter id="wf-wobble"><feTurbulence type="fractalNoise" '
                    'baseFrequency="0.018" numOctaves="2" seed="7" result="n"/>'
                    '<feDisplacementMap in="SourceGraphic" in2="n" scale="2.4"/></filter>')
        group_attr = ' filter="url(#wf-wobble)"'

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" class="wf-graph" '
        f'preserveAspectRatio="xMidYMin meet" role="img" '
        f'font-family="\'IBM Plex Sans\', system-ui, sans-serif">',
        f'<defs>{"".join(defs)}</defs>',
    ]
    if title:
        parts.append(f'<text x="{_PAD}" y="16" font-size="13" font-weight="600" '
                     f'fill="currentColor">{escape(title)}</text>')
    parts.append(f'<g transform="translate(0 {top})"{group_attr}>')

    # edges first (behind nodes)
    for e in graph.edges:
        parts.append(f'<path class="wf-edge" data-from="{e.src}" data-to="{e.dst}" '
                     f'd="{_edge_path(pos, e)}" fill="none" stroke="{edge_stroke}" '
                     f'stroke-width="{2 if sketch else 1.5}" stroke-opacity="0.75" '
                     f'marker-end="url(#{marker})"/>')
    # nodes
    for n in graph.nodes:
        x, y = pos[n.id]
        parts.append(
            f'<g class="wf-node" data-node="{n.id}" data-x="{x:.1f}" data-y="{y:.1f}" '
            f'transform="translate({x:.1f} {y:.1f})" style="cursor:grab">'
            f'<rect width="{_W}" height="{_H}" rx="{rx}" fill="{node_fill}" '
            f'stroke="{node_stroke}" stroke-width="{1.6 if sketch else 1.2}"/>'
            f'<text x="12" y="22" font-size="13" font-weight="600" fill="currentColor">'
            f'{escape(n.title)}</text>'
            f'<text x="12" y="40" font-size="10.5" fill="currentColor" fill-opacity="0.6" '
            f'font-family="\'IBM Plex Mono\', ui-monospace, monospace">{escape(n.sublabel)}</text>'
            f'</g>')
    parts.append("</g></svg>")
    return "".join(parts)


__all__ = ["WorkflowEdge", "WorkflowGraph", "WorkflowNode", "workflow_from_result", "workflow_svg"]
