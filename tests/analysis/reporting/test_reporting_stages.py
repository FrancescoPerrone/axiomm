"""S4c — decomposition + clustering sections, and the per-section options seam."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.reporting import ReportConfig, render_report
from axiomm.analysis.reporting.sections.clustering import ClusteringSection
from axiomm.analysis.reporting.sections.decomposition import DecompositionSection
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def _payload(seed=0, ny=12, nx=16, ne=200):
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


def _clusters_only():
    pytest.importorskip("sklearn")
    return Pipeline(groups=3, components=6).run(_payload())  # no beam energy -> no minerals


# --- sections appear in a clusters-only run -----------------------------------

def test_decomposition_and_clustering_sections_present():
    r = _clusters_only()
    html = render_report(r).content
    assert "Decomposition" in html and "Clustering" in html
    assert "explained variance" in html.lower()
    assert "cluster" in html.lower() and "pixels" in html.lower()


def test_stage_figures_embedded():
    pytest.importorskip("matplotlib")
    html = render_report(_clusters_only()).content
    # scree + label map both embedded, none linked
    assert html.count("data:image/png;base64,") >= 2
    assert "http://" not in html and "https://" not in html


# --- applies() and standalone use ---------------------------------------------

def test_sections_applies_and_run_standalone():
    r = _clusters_only()
    dec, clu = DecompositionSection(), ClusteringSection()
    assert dec.applies(r) and clu.applies(r)

    class _Empty:
        pass
    assert not dec.applies(_Empty()) and not clu.applies(_Empty())

    # a decomposition-only duck object renders on its own
    class _DecOnly:
        decomposition = r.decomposition
    sec = dec.render(_DecOnly(), ReportConfig())
    assert sec.id == "decomposition" and sec.blocks


# --- per-section options seam -------------------------------------------------

def test_decomposition_respects_max_components_option():
    r = _clusters_only()  # components=6
    cfg = ReportConfig(options={"decomposition": {"max_components": 3}})
    sec = DecompositionSection().render(r, cfg)
    tables = [b for b in sec.blocks if hasattr(b, "rows")]
    assert tables and len(tables[0].rows) == 3  # EV table capped to 3 rows
