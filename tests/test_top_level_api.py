"""Ergonomic API — the curated top-level `axiomm` surface and the `cluster()` verb."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

import axiomm
from axiomm import _EXPORTS


def _payload(seed=0, ny=12, nx=16, ne=200):
    from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
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


# --- one import surface, still import-light -----------------------------------

def test_bare_import_stays_light():
    code = ("import axiomm, sys; "
            "print(all(m not in sys.modules for m in "
            "['sklearn','xraylib','hyperspy','matplotlib']))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "True", out.stdout + out.stderr


def test_every_curated_name_resolves():
    for name in _EXPORTS:
        assert getattr(axiomm, name) is not None, name


def test_dir_lists_the_surface_and_unknown_raises():
    d = dir(axiomm)
    for name in ("Pipeline", "convert_file", "decompose", "cluster", "quantify",
                 "match_minerals", "render_report"):
        assert name in d
    missing = "definitely_not_a_real_export"
    with pytest.raises(AttributeError):
        getattr(axiomm, missing)


def test_names_point_at_the_real_callables():
    from axiomm.analysis.clustering import cluster as _cluster
    from axiomm.analysis.decomposition import decompose as _decompose
    assert axiomm.cluster is _cluster
    assert axiomm.decompose is _decompose


# --- the new cluster() verb mirrors decompose() -------------------------------

def test_cluster_verb_runs_via_top_level():
    pytest.importorskip("sklearn")
    p = _payload()
    decomp = axiomm.decompose(p, backend="pca", n_components=4)
    result = axiomm.cluster(decomp, backend="gmm", n_clusters=2)
    assert result.n_clusters == 2
    assert tuple(result.label_map.shape) == (12, 16)


def test_cluster_gmm_requires_n_clusters():
    pytest.importorskip("sklearn")
    from axiomm.analysis.errors import PayloadValidationError
    decomp = axiomm.decompose(_payload(), backend="pca", n_components=4)
    with pytest.raises(PayloadValidationError, match="n_clusters"):
        axiomm.cluster(decomp, backend="gmm")


def test_cluster_hdbscan_needs_no_n_clusters():
    pytest.importorskip("sklearn")
    decomp = axiomm.decompose(_payload(), backend="pca", n_components=4)
    result = axiomm.cluster(decomp, backend="hdbscan")   # discovers the count
    assert result.n_clusters >= 1
