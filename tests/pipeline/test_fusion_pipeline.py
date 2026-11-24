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
    """Two spatial domains: upper = Mg+Si+Ca, lower = Mg+Si.

    NB this fixture puts the SAME lines in both energies (a Ca line even at 2.9 keV, which
    physically cannot excite Ca's 4.04 keV edge), so it only exercises that fusion *engages*
    and routes by edge — not that each element is pulled from the map that truly excites it.
    Edge-faithful routing is tested end-to-end by test_fusion_excitation_aware_routing_end_to_end
    (and at the policy level in tests/analysis/test_fusion_selection.py)."""
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
    # the fused composition carries a light element (Si, measured at 2.9 keV) AND a
    # mid-Z element (Ca, measured at 13.55 keV) — neither single energy sees both.
    nets = set().union(*[set(q.net_intensities) for q in r.quantification])
    assert "Si" in nets and "Ca" in nets


def test_fusion_provenance_carries_cross_energy_and_round_trips(tmp_path):
    """#2: the bridge scale AND the per-energy status reach the quant provenance (not dropped
    at quantification) and survive save/load. JSON coerces float energy keys to strings, so
    compare by stringified keys."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 fusion_cross_cal="bridge").run(group)
    q = r.quantification[0].provenance.params
    assert "cross_energy_scale" in q and "cross_energy_status" in q
    assert set(q["cross_energy_status"].values()) <= {
        "reference", "no_bridge_elements", "no_usable_link",
        "refused_low_confidence", "applied_low_confidence", "applied"}

    def by_str(d):
        return {str(k): v for k, v in d.items()}

    from axiomm.pipeline import load_result
    r.save(tmp_path / "out")
    q2 = load_result(tmp_path / "out").quantification[0].provenance.params
    assert by_str(q2["cross_energy_scale"]) == by_str(q["cross_energy_scale"])
    assert by_str(q2["cross_energy_status"]) == by_str(q["cross_energy_status"])


def test_single_energy_quant_provenance_has_no_cross_energy_keys():
    """The single-energy path has no cross-energy correction, so those keys are absent
    (not carried as nulls)."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 beam_energy_kev=13.55).run(_map(0))
    params = r.quantification[0].provenance.params
    assert "cross_energy_scale" not in params and "cross_energy_status" not in params


def test_fusion_reliability_uses_source_raw_counting_basis():
    """#4: fused reliability grades each element's net-count floor on the RAW source counts,
    not the monitor-normalized fused quant; provenance records the source-raw basis."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 fusion_cross_cal="bridge").run(group)
    assert r.reliability is not None
    assert all(rel.provenance.params["counting_basis"] == "source_raw_counts"
               for rel in r.reliability)


def test_fusion_default_is_primary_clustering_no_bridge():
    """#5: the conservative default for an explicit multi-energy group is primary-map
    clustering with no bridge cross-calibration — NOT fused clustering / bridge. The
    single-energy path keeps its own (unrelated) defaults."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    pipe = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si")
    assert pipe._config_dict()["fusion_clustering"] == "primary"
    assert pipe._config_dict()["fusion_cross_cal"] == "none"
    r = pipe.run(group)
    codes = {d.code for d in r.diagnostics}
    assert "fusion_clustering_fused" not in codes          # not clustering on fused features
    assert "bridge_cross_calibration" not in codes          # no automatic bridge
    assert "fusion_experimental" not in codes               # conservative default is not experimental
    assert r.provenance["fusion_experimental"] is False


def test_beam_energy_does_not_broadcast_across_group():
    # a facade beam_energy must NOT override the per-map energies of a multi-energy group
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(beam_energy="99 keV", groups=2, components=4, seed=0,
                 reference=_ref(), reference_element="Si").run(group)
    msg = next(d.message for d in r.diagnostics if d.code == "fusion_engaged")
    assert "2.9" in msg and "13.55" in msg and "99" not in msg


def test_fusion_experimental_marker_when_opted_in(tmp_path):
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    # opting back into fused+bridge is experimental: diagnostic + provenance flag + report banner
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 fusion_clustering="fused", fusion_cross_cal="bridge").run(group)
    assert any(d.code == "fusion_experimental" for d in r.diagnostics)
    assert r.provenance["fusion_experimental"] is True
    assert "EXPERIMENTAL" in r.report_html().content
    # and it survives export (save/load carries the flag AND the banner with the result)
    from axiomm.pipeline import load_result
    r.save(tmp_path / "out")
    loaded = load_result(tmp_path / "out")
    assert loaded.provenance.get("fusion_experimental") is True
    assert "EXPERIMENTAL" in loaded.report_html().content   # banner renders from the loaded result too


def test_fusion_primary_none_is_not_experimental():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si",
                 fusion_clustering="primary", fusion_cross_cal="none").run(group)
    assert not any(d.code == "fusion_experimental" for d in r.diagnostics)
    assert r.provenance["fusion_experimental"] is False


def test_fusion_clustering_and_bridge_flagged_independently():
    """#5: clustering-mode and bridge-mode are orthogonal switches — each one alone
    engages its own feature and is flagged experimental on its own; the conservative
    default (primary + none) is the only combination that is not experimental."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0)), (13.55, _map(1))])

    # any of these means the bridge code path ran; none of them means bridge is off
    BRIDGE_CODES = {"bridge_none", "bridge_unresolved_energy",
                    "bridge_low_confidence", "bridge_cross_calibration"}

    def run(clustering, cross_cal):
        return Pipeline(groups=2, components=4, seed=0, reference=_ref(),
                        reference_element="Si", fusion_clustering=clustering,
                        fusion_cross_cal=cross_cal).run(group)

    # fused clustering alone (bridge off): fused-features diagnostic, NO bridge, experimental
    r_fused = run("fused", "none")
    codes = {d.code for d in r_fused.diagnostics}
    assert "fusion_clustering_fused" in codes and not (codes & BRIDGE_CODES)
    assert r_fused.provenance["fusion_experimental"] is True

    # bridge alone (primary clustering): bridge path ran, NO fused features, experimental
    r_bridge = run("primary", "bridge")
    codes = {d.code for d in r_bridge.diagnostics}
    assert "fusion_clustering_fused" not in codes and (codes & BRIDGE_CODES)
    assert r_bridge.provenance["fusion_experimental"] is True


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
    d1, _, ok1 = pipe._normalize_cross_map(_payload_exposure(1.0), [])
    d5, _, ok5 = pipe._normalize_cross_map(_payload_exposure(5.0), [])
    assert ok1 and ok5
    assert np.allclose(np.asarray(d1.data), np.asarray(d5.data))   # (counts*e)/(I0*e) == counts/I0


def test_cross_map_normalization_withholds_and_keeps_cube_finite():
    pipe = Pipeline()
    # no intensity_norm -> cannot establish comparability
    bare = AxiommSignalPayload(
        data=np.ones((3, 3, 10)),
        axes=(AxisSpec("y", "navigation", 3, index_in_array=0),
              AxisSpec("x", "navigation", 3, index_in_array=1),
              AxisSpec("E", "signal", 10, units="keV", scale=0.02, offset=0.0, index_in_array=2)),
        signal_kind="signal1d")
    out, mask, ok = pipe._normalize_cross_map(bare, [])
    assert out is None and mask is None and ok is False
    # an invalid-divisor pixel stays FINITE in the cube (reshape-safe) but False in the mask
    norm = np.full((3, 3), 100.0)
    norm[0, 0] = 0.0
    p = AxiommSignalPayload(data=np.ones((3, 3, 10)), axes=bare.axes, signal_kind="signal1d",
                            intensity_norm=norm)
    out2, mask2, ok2 = pipe._normalize_cross_map(p, [])
    assert ok2 and np.all(np.isfinite(np.asarray(out2.data)))
    assert mask2[0, 0] == np.False_ and int(np.asarray(mask2).sum()) == 8


def test_fusion_invalid_divisor_pixel_does_not_fail_run():
    """An invalid-divisor pixel must be excluded, not reject the whole cube at reshape."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    import dataclasses
    lo = _map(0)
    norm = np.array(lo.intensity_norm, dtype=float)
    norm[0, 0] = 0.0                              # one invalid-divisor pixel
    lo = dataclasses.replace(lo, intensity_norm=norm)
    group = MultiEnergyMapGroup.from_pairs([(2.9, lo), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si").run(group)
    assert r.phase_map is not None and r.quantification is not None    # whole run succeeds
    assert all(np.all(np.isfinite(list(q.net_intensities.values()))) for q in r.quantification)


def test_fusion_empty_cluster_arm_withholds_not_aborts():
    """#3 robustness: a whole cluster with no valid-divisor pixels in one arm has a NaN mean
    there; the run must WITHHOLD composition (clusters retained), not abort on the peak
    measurer's non-finite rejection. The one-invalid-pixel test covers a different case."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    import dataclasses
    lo = _map(0)
    norm = np.array(lo.intensity_norm, dtype=float)
    norm[lo.data.shape[0] // 2:, :] = 0.0        # an entire spatial half (≥1 whole cluster) invalid in the low arm
    lo = dataclasses.replace(lo, intensity_norm=norm)
    group = MultiEnergyMapGroup.from_pairs([(2.9, lo), (13.55, _map(1))])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref(), reference_element="Si").run(group)
    assert any(d.code == "fusion_cluster_support_missing" for d in r.diagnostics)
    assert r.quantification is None and r.minerals is None     # composition withheld, run did NOT abort
    assert len(r.clusters) == 2                                # clusters/evidence retained


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


def _ref_exc():
    """Edge-faithful reference: P/Si are excitable at 2.9 keV (edges 2.14 / 1.84 keV);
    Ca/Fe edges (4.04 / 7.11 keV) are above 2.9, so they can only be measured at 13.55 keV."""
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "P": ElementRef("P", 2.013, 30.974, 15, ("P2O5", 2, 5), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
        "Fe": ElementRef("Fe", 6.400, 55.845, 26, ("FeO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Apatite", "phosphate", {"Ca": 5, "P": 3, "O": 12}, None, "i",
                         basis="atom_counts"),
        MineralEndmember("Ferrosilite", "pyroxene", {"Fe": 1, "Si": 1, "O": 3}, None, "i",
                         basis="atom_counts"),
    )
    return MineralogyReference(
        name="exc", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}), family_display={"phosphate": "Ap", "pyroxene": "Px"})


def test_fusion_excitation_aware_routing_end_to_end():
    """#7: each energy's map carries ONLY the elements that energy can excite — P,Si at
    2.9 keV; Ca,Fe at 13.55 keV (Ca/Fe edges are above 2.9). Edge-aware routing must therefore
    assemble the fused composition from BOTH maps: Ca/Fe come from the high map (they are ABSENT
    from the low map) and P/Si from the low map, so no single acquisition can yield this element
    set. Unlike _map (same lines at both energies), a broken routing here would measure Ca where
    there is no Ca line and the test would fail."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    lo = _map_axis(0, scale=0.02, offset=0.0, ne=700,
                   upper=[(2.013, 300), (1.740, 300)], lower=[(1.740, 200)])   # P, Si only
    hi = _map_axis(1, scale=0.02, offset=0.0, ne=700,
                   upper=[(3.690, 300), (6.400, 300)], lower=[(3.690, 200)])   # Ca, Fe only
    group = MultiEnergyMapGroup.from_pairs([(2.9, lo), (13.55, hi)])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref_exc(),
                 reference_element="Si").run(group)
    nets = set().union(*[set(q.net_intensities) for q in r.quantification])
    assert {"P", "Si", "Ca", "Fe"} <= nets
    # one domain carries P (low-map only) together with Ca+Fe (high-map only) — impossible from
    # either single acquisition, so routing pulled each element from the map that excites it.
    assert any(q.net_intensities.get("P", 0.0) > 0.0 and q.net_intensities.get("Ca", 0.0) > 0.0
               and q.net_intensities.get("Fe", 0.0) > 0.0 for q in r.quantification)


def _ref_cov():
    """Reference for coverage statuses: S is excited at 2.9 keV (edge 2.47); Rb's K-edge
    (~15.2 keV) is above both energies, so Rb can never fluoresce in this group."""
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "S": ElementRef("S", 2.308, 32.06, 16, ("SO3", 1, 3), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
        "Rb": ElementRef("Rb", 13.395, 85.468, 37, None, "Ka"),
    }
    minerals = (
        MineralEndmember("Diopside", "pyroxene", {"Ca": 1, "Si": 2, "O": 6}, None, "i",
                         basis="atom_counts"),
        MineralEndmember("Anhydrite", "sulfate", {"Ca": 1, "S": 1, "O": 4}, None, "i",
                         basis="atom_counts"),
    )
    return MineralogyReference(
        name="cov", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}), family_display={"pyroxene": "Px", "sulfate": "Sulf"})


def test_fusion_records_coverage_eligibility_statuses(tmp_path):
    """B1: distinguish WHY a reference cation has no composition — `not_excited` (edge above
    every supplied energy: Rb) vs `out_of_coverage` (excited, but its line lies outside the
    spectral window of the map that would measure it: S is routed to 2.9 keV, whose map has a
    short axis that does not reach S's 2.31 keV line). Both survive save/load."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    lo = _map_axis(0, scale=0.01, offset=0.0, ne=200,            # short axis, ~0–2.0 keV
                   upper=[(1.740, 300)], lower=[(1.740, 200)])
    hi = _map_axis(1, scale=0.02, offset=0.0, ne=700,            # ~0–14 keV
                   upper=[(1.740, 200), (3.690, 300)], lower=[(3.690, 200)])
    group = MultiEnergyMapGroup.from_pairs([(2.9, lo), (13.55, hi)])
    r = Pipeline(groups=2, components=4, seed=0, reference=_ref_cov(),
                 reference_element="Si").run(group)
    obs = r.quantification[0].observation_status
    assert obs.get("Rb") == "not_excited"          # edge above both energies (physical)
    assert obs.get("S") == "out_of_coverage"       # excited, line outside its source map window
    assert "Rb" not in r.quantification[0].net_intensities   # never measured, still carries a reason
    from axiomm.pipeline import load_result
    r.save(tmp_path / "out")
    obs2 = load_result(tmp_path / "out").quantification[0].observation_status
    assert obs2.get("Rb") == "not_excited" and obs2.get("S") == "out_of_coverage"


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
