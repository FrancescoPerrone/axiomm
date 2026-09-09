"""S6 — second backends: HDBSCAN clustering and UMAP decomposition."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _features(seed=0, per=100, d=4, nav=(10, 20)):
    """Two well-separated blobs of decomposition loadings."""
    rng = np.random.default_rng(seed)
    a = rng.normal(0.0, 0.3, (per, d))
    b = rng.normal(6.0, 0.3, (per, d))

    class _F:
        loadings = np.vstack([a, b])
        nav_shape = nav
        n_components = d
    return _F()


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


# --- HDBSCAN (sklearn-backed, no extra dependency) ----------------------------

def test_hdbscan_backend_finds_the_blobs():
    pytest.importorskip("sklearn")
    from axiomm.analysis.clustering import HDBSCANClusterer
    res = HDBSCANClusterer().cluster(_features())
    real = [int(c) for c in np.asarray(res.cluster_ids) if c >= 0]
    assert len(real) >= 2
    assert tuple(res.label_map.shape) == (10, 20)
    assert any(d.code == "hdbscan_clusters" for d in res.diagnostics)


def test_hdbscan_is_registered_as_a_class():
    from axiomm.analysis.clustering import HDBSCANClusterer, get_clusterer
    assert get_clusterer("hdbscan") is HDBSCANClusterer


def test_pipeline_selects_hdbscan_by_name():
    pytest.importorskip("sklearn")
    from axiomm.pipeline import Pipeline
    r = Pipeline(components=4, clustering="hdbscan").run(_payload())
    assert len(r.clusters) >= 1
    assert r.provenance["config"]["clustering"] == "hdbscan"


def test_pipeline_hdbscan_dict_with_options():
    pytest.importorskip("sklearn")
    from axiomm.pipeline import Pipeline
    r = Pipeline(components=4,
                 clustering={"name": "hdbscan", "config": _hdbscan_cfg(3)}).run(_payload())
    assert len(r.clusters) >= 1


def _hdbscan_cfg(mcs):
    from axiomm.analysis.clustering import HDBSCANConfig
    return HDBSCANConfig(min_cluster_size=mcs)


# --- UMAP (optional dependency) -----------------------------------------------

def test_umap_is_registered():
    from axiomm.analysis.decomposition import decomposers
    assert "umap" in decomposers.names()


def test_umap_missing_raises_clear_dependency_error():
    try:
        import umap  # noqa: F401
        pytest.skip("umap-learn is installed; the missing-dependency path is not exercised")
    except ImportError:
        pass
    from axiomm.analysis.decomposition import get_decomposer
    with pytest.raises(AnalysisDependencyError, match="umap"):
        get_decomposer("umap").decompose(_payload(), n_components=2)


def test_umap_runs_when_available():
    pytest.importorskip("umap")
    pytest.importorskip("sklearn")
    from axiomm.pipeline import Pipeline
    r = Pipeline(reduction="umap", components=2, clustering="hdbscan").run(_payload())
    assert len(r.clusters) >= 1


# --- report decomposition section tolerates a no-variance backend -------------

def test_decomposition_section_handles_no_explained_variance():
    from types import SimpleNamespace

    from axiomm.analysis.reporting import ReportConfig
    from axiomm.analysis.reporting.section_renderers.decomposition import DecompositionSection

    decomp = SimpleNamespace(explained_variance_ratio=np.zeros((0,)), n_components=8,
                             provenance=SimpleNamespace(backend="umap"))
    result = SimpleNamespace(decomposition=decomp)
    sec = DecompositionSection().render(result, ReportConfig())
    assert sec.blocks and "not defined" in str(sec.blocks[0]).lower()
