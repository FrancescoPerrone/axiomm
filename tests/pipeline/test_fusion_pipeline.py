"""S8.4 — the multi-energy fusion path through the Pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import RegistrationError
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
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


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


def test_fusion_navigation_grid_mismatch_raises():
    group = MultiEnergyMapGroup.from_pairs([(2.9, _map(0, nx=10)), (13.55, _map(1, nx=12))])
    with pytest.raises(RegistrationError):
        Pipeline(groups=2, components=4, reference=_ref(), reference_element="Si").run(group)


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
