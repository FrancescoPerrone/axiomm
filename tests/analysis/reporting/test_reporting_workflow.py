"""Auto-generated workflow graph + SVG (clean / sketch)."""

from __future__ import annotations

import re
from types import SimpleNamespace

from axiomm.analysis.reporting.workflow import (
    WorkflowEdge,
    WorkflowGraph,
    WorkflowNode,
    render_workflow_page,
    workflow_canvas_html,
    workflow_from_result,
    workflow_svg,
)


def _branched():
    # a branch (hierarchical-clustering-like / general DAG): means -> {sub_a, sub_b}
    return WorkflowGraph(
        nodes=[WorkflowNode("means", "Cluster spectra"),
               WorkflowNode("sub_a", "Sub-clustering A"),
               WorkflowNode("sub_b", "Sub-clustering B")],
        edges=[WorkflowEdge("means", "sub_a"), WorkflowEdge("means", "sub_b")])


def _clusters_only():
    return SimpleNamespace(
        config={"reduction": "umap", "components": 6, "clustering": "hdbscan", "groups": 8},
        clusters=[{"cluster_id": 0}, {"cluster_id": 1}, {"cluster_id": 2}],
        minerals=None)


def _full():
    return SimpleNamespace(
        config={"reduction": "pca", "components": 6, "clustering": "gmm", "groups": 2,
                "beam_energy_kev": 15.0, "reference": "minerals_default_v2"},
        clusters=[{"cluster_id": 0}, {"cluster_id": 1}],
        minerals=("m0", "m1"))


def test_graph_from_clusters_only_run():
    g = workflow_from_result(_clusters_only())
    ids = [n.id for n in g.nodes]
    assert ids == ["signal", "reduce", "cluster", "means"]      # no mineral stages
    assert [(e.src, e.dst) for e in g.edges] == [
        ("signal", "reduce"), ("reduce", "cluster"), ("cluster", "means")]
    # backend + params surface in the node sublabels
    reduce = next(n for n in g.nodes if n.id == "reduce")
    assert "umap" in reduce.sublabel and "6" in reduce.sublabel


def test_graph_from_full_run_includes_mineral_stages():
    g = workflow_from_result(_full())
    ids = [n.id for n in g.nodes]
    assert ids == ["signal", "reduce", "cluster", "means",
                   "peaks", "quant", "reliability", "minerals", "phase"]
    quant = next(n for n in g.nodes if n.id == "quant")
    assert "15.0" in quant.sublabel


def test_svg_clean_is_self_contained_and_carries_graph_data():
    g = workflow_from_result(_full())
    svg = workflow_svg(g, theme="clean", title="Workflow")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "http" not in svg
    for n in g.nodes:
        assert f'data-node="{n.id}"' in svg          # draggable-ready hooks
    assert svg.count('class="wf-edge"') == len(g.edges)
    assert 'data-from="reduce" data-to="cluster"' in svg
    assert "Mineral match" in svg and "currentColor" in svg


def test_svg_sketch_theme_applies_the_hand_drawn_wobble():
    svg = workflow_svg(workflow_from_result(_full()), theme="sketch")
    assert "feDisplacementMap" in svg and "wf-wobble" in svg
    assert "http" not in svg


def test_empty_graph_renders():
    svg = workflow_svg(WorkflowGraph(), theme="clean")
    assert svg.startswith("<svg")


def test_layout_handles_branches_side_by_side():
    # the two branch children sit at the same depth (same y) but different x
    html = workflow_canvas_html(_branched())
    xs = {m.group(1): float(m.group(2)) for m in
          re.finditer(r'data-node="(sub_[ab])" data-x="([-\d.]+)" data-y="([-\d.]+)"', html)}
    ys = {m.group(1): float(m.group(3)) for m in
          re.finditer(r'data-node="(sub_[ab])" data-x="([-\d.]+)" data-y="([-\d.]+)"', html)}
    assert xs["sub_a"] != xs["sub_b"]        # branched horizontally
    assert ys["sub_a"] == ys["sub_b"]        # same layer


def test_render_workflow_page_is_full_editable_canvas_with_export():
    html = render_workflow_page(workflow_from_result(_full()), title="My workflow")
    assert html.lstrip().startswith("<!doctype html>")
    assert "My workflow" in html
    # one full-screen editable canvas, no static export strip
    assert html.count('class="wf-canvas"') == 1
    # opens like a report: masthead, no toolbar, no instructions
    assert 'class="wf-head"' in html and 'class="eyebrow"' in html
    assert "wf-bar" not in html                                 # no toolbar
    # controls are discovered in a corner (hover-revealed), not announced
    assert 'class="wf-controls"' in html
    assert 'class="export"' in html and "buildSVG" in html      # export the live state
    assert 'data-theme="sketch"' in html and 'data-theme="clean"' in html  # switch
    assert "contenteditable" in html and "pointerdown" in html  # editable + draggable
    assert "exports" not in html                                # the static strip is gone


def test_canvas_html_has_editable_text_and_edge_hooks():
    html = workflow_canvas_html(workflow_from_result(_full()))
    assert 'class="wf-node"' in html and 'contenteditable="true"' in html
    assert html.count('class="wf-edge"') == 8      # 8 edges in the full run
    assert 'data-from="reduce" data-to="cluster"' in html
    assert "http" not in html                       # self-contained
