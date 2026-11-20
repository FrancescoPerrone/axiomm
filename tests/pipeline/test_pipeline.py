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


# --- Intensity normalization (I0 + dead-time) ---------------------------------

def _norm_payload(nav_norm, ny=3, nx=4, ne=16):
    """Flat cube (all pixels identical) carrying a per-pixel intensity_norm."""
    cube = np.ones((ny, nx, ne)) * 10.0
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(
        data=cube, axes=axes, signal_kind="signal1d",
        intensity_norm=np.asarray(nav_norm, dtype=float))


def test_normalize_divides_by_median_scaled_divisor():
    """A pixel with twice the median flux is divided down to half magnitude;
    overall magnitude is preserved (median-scaled divisor)."""
    norm = np.full((3, 4), 100.0)
    norm[0, 0] = 200.0                      # one high-flux pixel
    payload = _norm_payload(norm)
    out = []
    p = Pipeline()._normalize_payload(payload, out)
    # magnitude preserved: median pixel keeps its 10.0
    assert p.data[1, 1, 0] == pytest.approx(10.0)
    # high-flux pixel scaled down by 2x
    assert p.data[0, 0, 0] == pytest.approx(5.0)
    assert p.intensity_norm is None         # cleared, cannot double-apply
    assert any(d.code == "normalization_applied" for d in out)


def test_normalize_leaves_bad_pixels_raw():
    """A NaN divisor pixel keeps its raw counts rather than becoming NaN."""
    norm = np.full((3, 4), 100.0)
    norm[2, 3] = np.nan
    payload = _norm_payload(norm)
    p = Pipeline()._normalize_payload(payload, [])
    assert p.data[2, 3, 0] == pytest.approx(10.0)
    assert np.all(np.isfinite(p.data))


def test_normalize_skips_on_shape_mismatch():
    """A divisor that doesn't match the nav grid is ignored with a diagnostic."""
    payload = _norm_payload(np.full((2, 2), 100.0))   # wrong shape for (3,4)
    out = []
    p = Pipeline()._normalize_payload(payload, out)
    assert p is payload                                # untouched
    assert any(d.code == "normalization_skipped" for d in out)


def test_normalize_noop_without_intensity_norm():
    payload = _norm_payload(np.full((3, 4), 100.0))
    payload.intensity_norm = None
    out = []
    assert Pipeline()._normalize_payload(payload, out) is payload
    assert out == []


def test_normalize_off_leaves_payload_untouched():
    """normalize=False keeps raw counts even when a divisor is present."""
    pytest.importorskip("sklearn")
    norm = np.full((12, 16), 100.0)
    base = _payload()
    base.intensity_norm = norm
    r = Pipeline(groups=2, components=4, normalize=False).run(base)
    assert not any(d.code == "normalization_applied" for d in r.diagnostics)
    assert r.payload.intensity_norm is norm       # still present, unapplied


# --- S7 classification wiring -------------------------------------------------

def test_default_classification_is_family_aware():
    assert PipelineConfig().classification == "family_aware"


def test_classification_rejects_bad_spec():
    with pytest.raises(PayloadValidationError):
        PipelineConfig(classification=123)


def test_clean_data_gets_species_under_default_policy():
    """Guard against over-abstention: clean, well-measured phases stay species."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    r = Pipeline(groups=2, components=4, reference=_controlled_reference(),
                 beam_energy_kev=15.0, seed=0).run(_payload(counts=400.0))
    levels = {row["level"] for row in r.clusters}
    assert levels <= {"species", "family"}          # nothing over-abstains on clean data
    assert any(row["level"] == "species" for row in r.clusters)
    assert r.labels is not None and len(r.labels) == len(r.clusters)
    assert r.provenance["classification"]["policy"] == "threshold"


def test_permissive_reproduces_pre_s7_labels():
    """permissive == the old always-name-best behaviour (the reversible default)."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    r = Pipeline(groups=2, components=4, reference=_controlled_reference(),
                 beam_energy_kev=15.0, seed=0, classification="permissive").run(
                     _payload(counts=400.0))
    for row in r.clusters:
        assert row["level"] == "species"
        assert row["label"] == row["best_match"]
    assert "unresolved" not in set(np.asarray(r.phase_map).ravel().tolist())


def test_classification_accepts_name_dict_instance():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    from axiomm.analysis.mineralogy.classify import ThresholdPolicy
    ref = _controlled_reference()
    strict_dict = {"name": "threshold", "species_floor": 0.999, "family_floor": 0.999}
    strict_inst = ThresholdPolicy(species_floor=0.999, family_floor=0.999, allow_family=False)
    r_dict = Pipeline(groups=2, components=4, reference=ref, beam_energy_kev=15.0, seed=0,
                      classification=strict_dict).run(_payload(counts=400.0))
    r_inst = Pipeline(groups=2, components=4, reference=ref, beam_energy_kev=15.0, seed=0,
                      classification=strict_inst).run(_payload(counts=400.0))
    # a near-impossible floor drives every cluster to unresolved (knob works)
    assert all(row["level"] == "unresolved" for row in r_dict.clusters)
    assert all(row["level"] == "unresolved" for row in r_inst.clusters)


def test_save_load_preserves_labels(tmp_path):
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    r = Pipeline(groups=2, components=4, reference=_controlled_reference(),
                 beam_energy_kev=15.0, seed=0).run(_payload(counts=400.0))
    r.save(tmp_path)
    back = load_result(tmp_path)
    assert back.labels is not None
    assert [lb.level for lb in back.labels] == [lb.level for lb in r.labels]
    assert [lb.name for lb in back.labels] == [lb.name for lb in r.labels]


def test_workflow_graph_carries_classification_node():
    from types import SimpleNamespace

    from axiomm.analysis.reporting.workflow import workflow_from_result
    res = SimpleNamespace(config={"classification": "family_aware"},
                          clusters=[{"cluster_id": 0}], minerals=(object(),))
    g = workflow_from_result(res)
    assert "classify" in [n.id for n in g.nodes]
    assert any(e.src == "minerals" and e.dst == "classify" for e in g.edges)
    assert any(e.src == "classify" and e.dst == "phase" for e in g.edges)
