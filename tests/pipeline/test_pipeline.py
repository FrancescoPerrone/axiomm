"""Tests for the S5 `axiomm.pipeline` front door."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline, PipelineConfig, load_result


def _payload(seed=0, counts=1.0, ny=12, nx=16, ne=400):
    """Two-domain (y,x,E) map: Mg+Si upper half, Ca+Mg+Si lower half."""
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)

    def add(sl, lines):
        for cen, amp in lines:
            cube[sl] += amp * counts * np.exp(-((e - cen) ** 2) / (2 * 0.05 ** 2))

    add((slice(None, ny // 2),), [(1.254, 300), (1.740, 150)])          # Mg, Si
    add((slice(ny // 2, None),), [(3.690, 250), (1.254, 150), (1.740, 300)])  # Ca, Mg, Si
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


def _controlled_reference():
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "i", basis="atom_counts"),
        MineralEndmember("Diopside", "pyroxene", {"Ca": 1, "Mg": 1, "Si": 2, "O": 6}, None, "i", basis="atom_counts"),
    )
    return MineralogyReference(
        name="pipe_test_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}),
        family_display={"olivine": "Ol", "pyroxene": "Px"})


# --- Acceptance 1: import is light --------------------------------------------

def test_import_is_light():
    code = ("import axiomm, sys; "
            "print(all(m not in sys.modules for m in ['sklearn','xraylib','hyperspy']))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "True", out.stdout + out.stderr


# --- Acceptance 2/8: clusters-only path, plain result -------------------------

def test_clusters_only_when_no_beam_energy():
    pytest.importorskip("sklearn")
    r = Pipeline(groups=2, components=4).run(_payload())
    assert r.minerals is None and r.phase_map is None
    assert len(r.clusters) == 2
    assert all(row["best_match"] == "unresolved" for row in r.clusters)
    assert any(d.code == "minerals_skipped" for d in r.diagnostics)
    assert "clusters only" in repr(r)


# --- Acceptance 5: deterministic under a fixed seed ---------------------------

def test_deterministic_under_seed():
    pytest.importorskip("sklearn")
    p = _payload()
    a = Pipeline(groups=2, components=4, seed=3).run(p)
    b = Pipeline(groups=2, components=4, seed=3).run(p)
    assert np.array_equal(a.label_map, b.label_map)


# --- Acceptance 7: config validation ------------------------------------------

@pytest.mark.parametrize("kwargs", [
    dict(groups=0), dict(components=0), dict(groups=1.5),
    dict(beam_energy_kev=-1), dict(beam_energy_kev=float("nan")),
    dict(seed="x"), dict(reference_element=""),
])
def test_config_rejects_bad_settings(kwargs):
    with pytest.raises(PayloadValidationError):
        PipelineConfig(**kwargs)


# --- Acceptance 3/4: full chain + phase map -----------------------------------

def test_full_chain_produces_phase_map():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    ref = _controlled_reference()
    r = Pipeline(groups=2, components=4, reference=ref, beam_energy_kev=15.0,
                 reference_element="Si", seed=0).run(_payload(counts=400.0))
    assert r.minerals is not None
    assert r.phase_map is not None and r.phase_map.shape == r.label_map.shape
    # at least one cluster resolves to a real olivine/pyroxene (not all unresolved)
    names = set(np.unique(r.phase_map))
    assert names & {"Forsterite", "Diopside"}


def test_reference_element_out_of_range_raises():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    ref = _controlled_reference()
    with pytest.raises(PayloadValidationError, match="energy range"):
        Pipeline(reference=ref, beam_energy_kev=15.0, reference_element="Fe",
                 groups=2, components=4).run(_payload())


# --- Acceptance 6: save / load round-trip -------------------------------------

def test_save_load_clusters_only(tmp_path):
    pytest.importorskip("sklearn")
    r = Pipeline(groups=2, components=4).run(_payload())
    r.save(tmp_path)
    back = load_result(tmp_path)
    assert [c["cluster_id"] for c in back.clusters] == [c["cluster_id"] for c in r.clusters]
    assert back.minerals is None


def test_save_load_full_chain(tmp_path):
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    ref = _controlled_reference()
    r = Pipeline(groups=2, components=4, reference=ref, beam_energy_kev=15.0, seed=0).run(
        _payload(counts=400.0))
    r.save(tmp_path)
    back = load_result(tmp_path)
    assert back.minerals is not None
    assert np.array_equal(np.asarray(back.phase_map), np.asarray(r.phase_map))
    assert [c["best_match"] for c in back.clusters] == [c["best_match"] for c in r.clusters]
