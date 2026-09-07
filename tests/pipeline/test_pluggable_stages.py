"""Pluggable reduction + clustering stages for `axiomm.pipeline` (S5-refinement).

A stage backend may be given as a name, a constructed instance, or a
``{"name": ..., **options}`` dict; ``None`` keeps today's seeded PCA / GMM
defaults. Selecting a non-default *registered* name is the socket S6 backends
(UMAP, HDBSCAN, ...) plug into, so a dummy registered backend is exercised here.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import BackendNotFoundError, PayloadValidationError
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline, PipelineConfig


def _payload(seed=0, ny=12, nx=16, ne=200):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)
    cube[: ny // 2] += 300 * np.exp(-((e - 1.254) ** 2) / (2 * 0.05**2))
    cube[ny // 2 :] += 300 * np.exp(-((e - 3.690) ** 2) / (2 * 0.05**2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


# --- defaults are untouched ---------------------------------------------------

def test_none_and_named_builtins_agree():
    pytest.importorskip("sklearn")
    p = _payload()
    default = Pipeline(groups=2, components=4, seed=1).run(p)
    named = Pipeline(groups=2, components=4, seed=1,
                     reduction="pca", clustering="gmm").run(p)
    assert np.array_equal(default.label_map, named.label_map)


def test_dict_form_selects_builtin_with_options():
    pytest.importorskip("sklearn")
    r = Pipeline(components=4, seed=0,
                 reduction={"name": "pca"},
                 clustering={"name": "gmm", "n_clusters": 3}).run(_payload())
    assert len(r.clusters) == 3


# --- instances are used as-is, with an honest diagnostic ----------------------

def test_clustering_instance_used_as_is():
    pytest.importorskip("sklearn")
    from axiomm.analysis.clustering import GMMClusterer, GMMConfig
    clus = GMMClusterer(n_clusters=3, config=GMMConfig(random_state=0))
    r = Pipeline(groups=8, components=4, clustering=clus).run(_payload())
    # the instance's n_clusters wins over the pipeline's groups=8
    assert len(r.clusters) == 3
    assert any(d.code == "stage_instance_supplied" for d in r.diagnostics)


def test_reduction_instance_used_as_is():
    pytest.importorskip("sklearn")
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer
    r = Pipeline(groups=2, components=4,
                 reduction=SklearnPCADecomposer(random_state=1)).run(_payload())
    assert len(r.clusters) == 2
    assert any(d.code == "stage_instance_supplied" for d in r.diagnostics)


# --- forward-compat: a non-default *registered* name resolves and runs --------

def test_registered_backend_names_resolve():
    """Proves the socket S6 (UMAP/HDBSCAN) plugs into: register under a new
    name, select it, and the pipeline resolves + runs it."""
    pytest.importorskip("sklearn")
    from axiomm.analysis.clustering import GMMClusterer, clusterers
    from axiomm.analysis.decomposition import decomposers
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer

    class MyReducer(SklearnPCADecomposer):
        pass

    class MyClusterer(GMMClusterer):
        pass

    decomposers.register("myreducer", lambda: MyReducer())
    clusterers.register("myclusterer", lambda: MyClusterer)
    try:
        r = Pipeline(groups=2, components=4, seed=0,
                     reduction="myreducer", clustering="myclusterer").run(_payload())
        assert len(r.clusters) == 2
        assert r.provenance["config"]["reduction"] == "myreducer"
        assert r.provenance["config"]["clustering"] == "myclusterer"
    finally:
        decomposers.unregister("myreducer")
        clusterers.unregister("myclusterer")


# --- provenance records the chosen backends -----------------------------------

def test_provenance_records_backend_names():
    pytest.importorskip("sklearn")
    r = Pipeline(groups=2, components=4).run(_payload())
    assert r.provenance["config"]["reduction"] == "pca"
    assert r.provenance["config"]["clustering"] == "gmm"


# --- validation ---------------------------------------------------------------

def test_unknown_backend_name_raises():
    pytest.importorskip("sklearn")
    with pytest.raises(BackendNotFoundError):
        Pipeline(groups=2, components=4, reduction="does_not_exist").run(_payload())


@pytest.mark.parametrize("kwargs", [
    dict(reduction=123),
    dict(clustering=object()),
    dict(reduction={"nope": "pca"}),      # dict without a name
    dict(clustering={"name": ""}),        # empty name
])
def test_bad_stage_spec_rejected_at_config(kwargs):
    with pytest.raises(PayloadValidationError):
        PipelineConfig(**kwargs)
