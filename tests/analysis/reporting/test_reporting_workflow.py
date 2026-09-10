"""Auto-generated workflow graph + SVG (clean / sketch)."""

from __future__ import annotations

from types import SimpleNamespace

from axiomm.analysis.reporting.workflow import (
    WorkflowGraph,
    workflow_from_result,
    workflow_svg,
)


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
