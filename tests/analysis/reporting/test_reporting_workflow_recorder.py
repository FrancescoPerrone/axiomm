"""Provenance recorder for free-composed tool use + result.workflow_html()."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from axiomm.analysis.reporting.workflow import WorkflowRecorder
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _prov_result(tool, backend):
    return SimpleNamespace(provenance=SimpleNamespace(tool=tool, backend=backend))


def test_recorder_infers_edges_from_object_flow():
    rec = WorkflowRecorder()
    payload = object()
    rec.source(payload, title="Signal")

    def decompose(x):
        return _prov_result("decomposition", "pca")

    def cluster(x):
        return _prov_result("clustering", "gmm")

    comps = rec.step(decompose, payload)      # edge: Signal -> Decomposition
    rec.step(cluster, comps)                   # edge: Decomposition -> Clustering

    g = rec.graph()
    assert [n.title for n in g.nodes] == ["Signal", "Decomposition", "Clustering"]
    ids = {n.title: n.id for n in g.nodes}
    edges = {(e.src, e.dst) for e in g.edges}
    assert edges == {(ids["Signal"], ids["Decomposition"]),
                     (ids["Decomposition"], ids["Clustering"])}
    # backend read from provenance shows up as the sublabel
    assert next(n for n in g.nodes if n.title == "Decomposition").sublabel == "pca"


def test_recorder_supports_branches_for_hierarchical_use():
    rec = WorkflowRecorder()
    root = _prov_result("clustering", "gmm")
    rec.record(root, tool="clustering", backend="gmm")
    a = rec.record(_prov_result("clustering", "hdbscan"), tool="clustering",
                   backend="hdbscan", inputs=[root])
    b = rec.record(_prov_result("clustering", "hdbscan"), tool="clustering",
                   backend="hdbscan", inputs=[root])
    g = rec.graph()
    assert len(g.nodes) == 3 and len(g.edges) == 2      # root -> a, root -> b
    assert a is not b


def test_recorder_workflow_html_is_a_full_page():
    rec = WorkflowRecorder()
    p = object()
    rec.source(p)
    rec.step(lambda x: _prov_result("decomposition", "umap"), p)
    html = rec.workflow_html(title="My recorded run")
    assert html.lstrip().startswith("<!doctype html>")
    assert "My recorded run" in html and 'class="wf-canvas"' in html


def _payload():
    rng = np.random.default_rng(0)
    ne = 200
    e = np.arange(ne) * 0.02
    cube = np.full((10, 12, ne), 2.0)
    cube[:5] += 300 * np.exp(-((e - 1.25) ** 2) / (2 * 0.05**2))
    cube[5:] += 300 * np.exp(-((e - 3.69) ** 2) / (2 * 0.05**2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", 10, index_in_array=0),
        AxisSpec("x", "navigation", 12, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


def test_pipeline_result_workflow_html(tmp_path):
    pytest.importorskip("sklearn")
    from axiomm.analysis.errors import OutputExistsError
    from axiomm.pipeline import Pipeline
    r = Pipeline(groups=2, components=4).run(_payload())
    html = r.workflow_html()
    assert "Analysis workflow" in html and 'class="wf-canvas"' in html
    assert "Decomposition" in html and "Clustering" in html

    out = tmp_path / "wf.html"
    r.workflow_html(out)
    assert out.exists()
    with pytest.raises(OutputExistsError):
        r.workflow_html(out)
    r.workflow_html(out, overwrite=True)
