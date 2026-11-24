"""S8.4 — the multi-energy fusion path through the Pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError, RegistrationError
from axiomm.analysis.fusion import MultiEnergyMapGroup
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def test_config_dict_records_fusion_settings():
    # effective fusion/normalize settings must be in provenance to reproduce a run
    cfg = Pipeline(fusion_clustering="primary", fusion_cross_cal="none",
                   normalize=False, exclude_elements={"Ba"})._config_dict()
    assert cfg["fusion_clustering"] == "primary"
    assert cfg["fusion_cross_cal"] == "none"
    assert cfg["normalize"] is False
    assert cfg["exclude_elements"] == ["Ba"]
    assert "line_resolution_kev" in cfg
    assert "bridge_dispersion_limit" in cfg and "bridge_low_confidence" in cfg


def test_bridge_low_confidence_config_validation():
    with pytest.raises(PayloadValidationError):
        Pipeline(bridge_low_confidence="sometimes")
    with pytest.raises(PayloadValidationError):
        Pipeline(bridge_dispersion_limit=0.5)


def _map(seed=0, ny=8, nx=10, ne=400):
    """Two spatial domains: upper = Mg+Si+Ca, lower = Mg+Si."""
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)

    def add(sl, lines):
        for cen, amp in lines:
            cube[sl] += amp * np.exp(-((e - cen) ** 2) / (2 * 0.05 ** 2))

    add((slice(None, ny // 2),), [(1.254, 300), (1.740, 300), (3.690, 300)])   # Mg, Si, Ca
    add((slice(ny // 2, None),), [(1.254, 300), (1.740, 180)])                 # Mg, Si
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, units="µm", scale=1.0, offset=0.0, index_in_array=0),
        AxisSpec("x", "navigation", nx, units="µm", scale=1.0, offset=0.0, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d",
                               intensity_norm=np.full((ny, nx), 100.0))


def _ref():
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
        name="t", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}), family_display={"olivine": "Ol", "pyroxene": "Px"})


def test_fusion_path_runs_and_uses_both_energies():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si").run(group)
    assert r.phase_map is not None and r.minerals is not None
    codes = {d.code for d in r.diagnostics}
    assert "fusion_engaged" in codes and "navigation_grid_verified" in codes
    assert "fusion_clustering_fused" in codes      # default clusters on both energies
    assert "bridge_cross_calibration" in codes or "bridge_none" in codes
    # the fused composition carries a light element (Si, measured at 2.9 keV) AND a
    # mid-Z element (Ca, measured at 13.55 keV) — neither single energy sees both.
    nets = set().union(*[set(q.net_intensities) for q in r.quantification])
    assert "Si" in nets and "Ca" in nets


def test_beam_energy_does_not_broadcast_across_group():
    # a facade beam_energy must NOT override the per-map energies of a multi-energy group
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(beam_energy="99 keV", groups=2, components=4, seed=0,
                 reference=_ref(), reference_element="Si").run(group)
    msg = next(d.message for d in r.diagnostics if d.code == "fusion_engaged")
    assert "2.9" in msg and "13.55" in msg and "99" not in msg


def test_fusion_experimental_marker_on_defaults_and_report(tmp_path):
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si").run(group)
    # default fused+bridge is experimental: diagnostic + provenance flag + report banner
    assert any(d.code == "fusion_experimental" for d in r.diagnostics)
    assert r.provenance["fusion_experimental"] is True
    assert "EXPERIMENTAL" in r.report_html().content
    # and it survives export (save/load carries the flag with the result)
    from axiomm.pipeline import load_result
    r.save(tmp_path / "out")
    assert load_result(tmp_path / "out").provenance.get("fusion_experimental") is True


def test_fusion_primary_none_is_not_experimental():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 fusion_clustering="primary", fusion_cross_cal="none").run(group)
    assert not any(d.code == "fusion_experimental" for d in r.diagnostics)
    assert r.provenance["fusion_experimental"] is False


def _payload_exposure(exposure):
    cube = (np.arange(4 * 4 * 20).reshape(4, 4, 20).astype(float) + 1.0) * exposure
    axes = (
        AxisSpec("y", "navigation", 4, units="µm", scale=1.0, offset=0.0, index_in_array=0),
        AxisSpec("x", "navigation", 4, units="µm", scale=1.0, offset=0.0, index_in_array=1),
        AxisSpec("Energy", "signal", 20, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d",
                               intensity_norm=np.full((4, 4), 100.0 * exposure))


def test_cross_map_normalization_cancels_exposure():
    """#3 core guarantee: dividing counts by the raw I0 (no per-map median) removes an
    exposure/monitor scaling, so two acquisitions of the same composition land on one scale."""
    pipe = Pipeline()
    d1, ok1 = pipe._normalize_cross_map(_payload_exposure(1.0), [])
    d5, ok5 = pipe._normalize_cross_map(_payload_exposure(5.0), [])
    assert ok1 and ok5
    assert np.allclose(np.asarray(d1.data), np.asarray(d5.data))   # (counts*e)/(I0*e) == counts/I0


def test_cross_map_normalization_withholds_and_masks():
    pipe = Pipeline()
    # no intensity_norm -> cannot establish comparability
    bare = AxiommSignalPayload(
        data=np.ones((3, 3, 10)),
        axes=(AxisSpec("y", "navigation", 3, index_in_array=0),
              AxisSpec("x", "navigation", 3, index_in_array=1),
              AxisSpec("E", "signal", 10, units="keV", scale=0.02, offset=0.0, index_in_array=2)),
        signal_kind="signal1d")
    out, ok = pipe._normalize_cross_map(bare, [])
    assert out is None and ok is False
    # an invalid-divisor pixel is masked to NaN (excluded), not left as raw counts
    norm = np.full((3, 3), 100.0)
    norm[0, 0] = 0.0
    p = AxiommSignalPayload(data=np.ones((3, 3, 10)), axes=bare.axes, signal_kind="signal1d",
                            intensity_norm=norm)
    out2, ok2 = pipe._normalize_cross_map(p, [])
    assert ok2 and np.isnan(np.asarray(out2.data)[0, 0]).all()


def test_fusion_withholds_composition_without_comparable_normalization():
    """#3: a map lacking a usable intensity_norm -> comparability can't be established ->
    fused composition is withheld; clusters and evidence are retained."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    import dataclasses
    lo = dataclasses.replace(_map(0), intensity_norm=None)       # no I0
    group = MultiEnergyMapGroup.from_pairs([(2.9, lo), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si").run(group)
    assert any(d.code == "fusion_composition_withheld" for d in r.diagnostics)
    assert r.quantification is None and r.minerals is None and r.phase_map is None
    assert len(r.clusters) == 2                                  # clusters/evidence kept


def test_fusion_navigation_grid_mismatch_raises():
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0, nx=10)), (13.55, _map(1, nx=12))])
    with pytest.raises(RegistrationError):
        Pipeline(groups=2, components=4, reference=_ref(), reference_element="Si").run(group)


# -- #6 N-energy generality: per-map spectral axis + union eligibility --------

def _map_axis(seed, *, scale, offset, ne, upper, lower, ny=8, nx=10):
    """A map on an arbitrary signal axis (scale/offset/size), same nav grid as _map."""
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * scale + offset
    cube = np.full((ny, nx, ne), 2.0)

    def add(sl, lines):
        for cen, amp in lines:
            cube[sl] += amp * np.exp(-((e - cen) ** 2) / (2 * 0.05 ** 2))

    add((slice(None, ny // 2),), upper)
    add((slice(ny // 2, None),), lower)
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, units="µm", scale=1.0, offset=0.0, index_in_array=0),
        AxisSpec("x", "navigation", nx, units="µm", scale=1.0, offset=0.0, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=scale, offset=offset, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d",
                               intensity_norm=np.full((ny, nx), 100.0))


def _ref_wide():
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Al": ElementRef("Al", 1.486, 26.982, 13, ("Al2O3", 2, 3), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
        "Fe": ElementRef("Fe", 6.400, 55.845, 26, ("FeO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Anorthite", "feldspar", {"Al": 2, "Si": 2, "Ca": 1, "O": 8}, None, "i",
                         basis="atom_counts"),
        MineralEndmember("Fayalite", "olivine", {"Fe": 2, "Si": 1, "O": 4}, None, "i",
                         basis="atom_counts"),
    )
    return MineralogyReference(
        name="w", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}), family_display={"feldspar": "Fsp", "olivine": "Ol"})


def test_fusion_union_eligibility_and_per_map_axis():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    # lo spans 0-4.99 keV (Al, Si); hi spans 2.0-13.98 keV (Ca, Fe) -- NON-nested ranges,
    # different signal axes, same nav grid. Al (1.486 keV) is ONLY in lo's range.
    lo = _map_axis(0, scale=0.01, offset=0.0, ne=500,
                   upper=[(1.486, 300), (1.740, 300)], lower=[(1.740, 200)])
    hi = _map_axis(1, scale=0.02, offset=2.0, ne=600,
                   upper=[(3.690, 300), (6.400, 300)], lower=[(3.690, 200)])
    group = MultiEnergyMapGroup.from_pairs([(2.9, lo), (13.55, hi)])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref_wide(),
                 reference_element="Si").run(group)
    nets = set().union(*[set(q.net_intensities) for q in r.quantification])
    # union eligibility: Al is below hi's 2.0 keV floor, so a primary(hi)-only range would miss
    # it; the union of ranges keeps it, measured on lo's own axis without error.
    assert "Al" in nets
    assert "Si" in nets and "Ca" in nets      # both maps' ranges are represented


def test_energy_selection_config_recorded_and_validated():
    cfg = Pipeline(energy_selection="best_excited")._config_dict()
    assert cfg["energy_selection"] == "best_excited"
    with pytest.raises(PayloadValidationError):
        Pipeline(energy_selection=123)        # not a name or a policy


def test_single_map_group_runs():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(13.55, _map(0))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si").run(group)
    assert r.phase_map is not None


def test_fusion_clustering_primary_mode():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 fusion_clustering="primary").run(group)
    assert r.phase_map is not None
    assert "fusion_clustering_fused" not in {d.code for d in r.diagnostics}


def test_config_rejects_bad_fusion_options():
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.pipeline import PipelineConfig
    with pytest.raises(PayloadValidationError):
        PipelineConfig(fusion_clustering="nope")
    with pytest.raises(PayloadValidationError):
        PipelineConfig(fusion_cross_cal="nope")
