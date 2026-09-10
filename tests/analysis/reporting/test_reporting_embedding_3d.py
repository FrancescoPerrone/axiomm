"""On-demand 3-D embedding viewer (structural checks; WebGL verified on-device)."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.reporting.embedding_3d import (
    embedding_3d_from_result,
    render_embedding_3d_page,
)


def test_page_loads_three_and_carries_points_and_controls():
    rng = np.random.default_rng(0)
    pts = np.vstack([rng.normal(0, 0.4, (60, 3)), rng.normal(5, 0.4, (60, 3))])
    labels = np.array([0] * 60 + [1] * 60)
    html = render_embedding_3d_page(pts, labels, title="My embedding", backend="umap")
    assert html.lstrip().startswith("<!doctype html>")
    assert "My embedding" in html
    assert "cdnjs.cloudflare.com/ajax/libs/three.js" in html   # the one allowed CDN
    assert '"points"' in html and '"labels"' in html and '"categories"' in html
    # scientific controls present
    for ctl in ('id="reset"', 'id="proj"', 'id="size"', 'id="axes"', 'id="legend"'):
        assert ctl in html, ctl
    # no auto-spin: static initial render, no autoRotate
    assert "autoRotate" not in html
    assert "static initial view" in html


def test_page_rejects_non_3d_points():
    with pytest.raises(PayloadValidationError):
        render_embedding_3d_page(np.zeros((10, 2)), np.zeros(10))


def test_from_result_needs_three_components():
    bad = SimpleNamespace(
        decomposition=SimpleNamespace(loadings=np.zeros((20, 2))),
        clustering=SimpleNamespace(labels=np.zeros(20)))
    with pytest.raises(PayloadValidationError, match="n_components"):
        embedding_3d_from_result(bad)


def test_from_result_extracts_first_three_components_and_subsamples():
    res = SimpleNamespace(
        decomposition=SimpleNamespace(loadings=np.random.default_rng(0).normal(size=(5000, 6))),
        clustering=SimpleNamespace(labels=np.zeros(5000, int)))
    pts, labels = embedding_3d_from_result(res, max_points=1000)
    assert pts.shape == (1000, 3) and labels.shape == (1000,)


def test_from_result_end_to_end():
    pytest.importorskip("sklearn")
    from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
    from axiomm.pipeline import Pipeline
    rng = np.random.default_rng(0)
    ne = 200
    e = np.arange(ne) * 0.02
    cube = np.full((12, 14, ne), 2.0)
    cube[:6] += 300 * np.exp(-((e - 1.25) ** 2) / (2 * 0.05**2))
    cube[6:] += 300 * np.exp(-((e - 3.69) ** 2) / (2 * 0.05**2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", 12, index_in_array=0),
        AxisSpec("x", "navigation", 14, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    r = Pipeline(groups=2, components=3).run(
        AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d"))
    pts, labels = embedding_3d_from_result(r)
    assert pts.shape[1] == 3 and pts.shape[0] == labels.shape[0]
    html = render_embedding_3d_page(pts, labels, title="Run embedding")
    assert "three.js" in html
