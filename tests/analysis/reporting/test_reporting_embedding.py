"""Embedding scatter report section (UMAP/HDBSCAN offer)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.reporting import render_report
from axiomm.analysis.reporting.section_renderers.embedding import EmbeddingSection
from axiomm.analysis.reporting.svg import scatter_svg
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def _payload(seed=0, ny=16, nx=20, ne=200):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)
    cube[: ny // 2] += 300 * np.exp(-((e - 1.254) ** 2) / (2 * 0.05**2))
    cube[ny // 2:] += 300 * np.exp(-((e - 3.690) ** 2) / (2 * 0.05**2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


# --- the scatter renderer -----------------------------------------------------

def test_scatter_svg_is_theme_aware_and_self_contained():
    rng = np.random.default_rng(0)
    x = rng.normal(size=50)
    y = rng.normal(size=50)
    labels = np.array([0] * 25 + [1] * 24 + [-1])
    svg = scatter_svg(x, y, labels, categories=[-1, 0, 1],
                      labels_text={-1: "noise", 0: "cluster 0", 1: "cluster 1"})
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "currentColor" in svg          # axes/text adapt to the page theme
    assert "noise" in svg and "cluster 0" in svg
    assert "http" not in svg


def test_scatter_svg_subsamples_large_clouds():
    n = 10000
    rng = np.random.default_rng(0)
    svg = scatter_svg(rng.normal(size=n), rng.normal(size=n), np.zeros(n, int),
                      categories=[0], max_points=500)
    assert svg.count("<circle") == 500   # capped


# --- the section in a run -----------------------------------------------------

def test_embedding_section_present_in_a_clusters_only_run():
    pytest.importorskip("sklearn")
    r = Pipeline(groups=2, components=4).run(_payload())   # no beam energy needed
    html = render_report(r).content
    assert "Embedding" in html and "<svg" in html
    assert "exploratory" in html.lower()      # the scientific gate is stated


def test_embedding_section_applies_only_with_decomposition_and_clustering():
    sec = EmbeddingSection()

    class _Empty:
        pass
    assert not sec.applies(_Empty())

    pytest.importorskip("sklearn")
    from axiomm.analysis.reporting import ReportConfig
    r = Pipeline(groups=2, components=4).run(_payload())
    assert sec.applies(r)
    section = sec.render(r, ReportConfig())
    assert section.id == "embedding" and section.blocks
