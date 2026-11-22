"""S8.3 — cross-energy fusion: net-intensity selection + per-element-energy k-factors."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import CrossCalibrationError, PayloadValidationError
from axiomm.analysis.fusion import (
    bridge_cross_calibration,
    fuse_net_intensities,
    fused_k_factors,
)
from axiomm.analysis.mineralogy.reference import ElementRef
from axiomm.analysis.quant.models import KFactorSet


def _ref(sym, z):
    return ElementRef(sym, 1.0, 20.0, z, None, "Ka")


# -- fuse_net_intensities ----------------------------------------------------

def test_fuse_net_picks_each_element_from_its_energy():
    per_energy = {
        2.9: {0: {"Si": 10.0, "P": 5.0}, 1: {"Si": 8.0, "P": 3.0}},
        13.55: {0: {"Fe": 20.0, "Ca": 7.0}, 1: {"Fe": 15.0, "Ca": 4.0}},
    }
    source = {"Si": 2.9, "P": 2.9, "Fe": 13.55, "Ca": 13.55}
    fused, diags = fuse_net_intensities(per_energy, source)
    assert fused[0] == {"Si": 10.0, "P": 5.0, "Fe": 20.0, "Ca": 7.0}
    assert fused[1] == {"Si": 8.0, "P": 3.0, "Fe": 15.0, "Ca": 4.0}
    assert not [d for d in diags if d.code == "fusion_not_excited"]


def test_fuse_net_omits_not_excited_with_diagnostic():
    per_energy = {2.9: {0: {"Si": 10.0}}, 13.55: {0: {"Fe": 20.0}}}
    fused, diags = fuse_net_intensities(per_energy, {"Si": 2.9, "Fe": 13.55, "Zr": None})
    assert "Zr" not in fused[0] and fused[0] == {"Si": 10.0, "Fe": 20.0}
    assert any(d.code == "fusion_not_excited" for d in diags)


# -- fused_k_factors (injectable sensitivity source) -------------------------

def _fake_compute(S):
    def fake(els, *, excitation_kev, reference):
        sens = {el.symbol: S[(el.symbol, excitation_kev)] for el in els}
        return KFactorSet(k_factors={e.symbol: 1.0 for e in els}, sensitivities=sens,
                          reference_element=reference, excitation_kev=excitation_kev)
    return fake


def test_fused_k_uses_per_element_measurement_energy():
    s = {("Si", 2.9): 4.0, ("P", 2.9): 2.0, ("Fe", 13.55): 1.0, ("Ca", 13.55): 0.5}
    refs = [_ref("Si", 14), _ref("P", 15), _ref("Fe", 26), _ref("Ca", 20)]
    source = {"Si": 2.9, "P": 2.9, "Fe": 13.55, "Ca": 13.55}
    ks = fused_k_factors(refs, source, reference="Si", _compute=_fake_compute(s))
    # k_i = S_ref(E_ref) / S_i(E_i), with S_ref = S_Si(2.9) = 4.0
    assert ks.k_factors["Si"] == 1.0
    assert ks.k_factors["P"] == 4.0 / 2.0
    assert ks.k_factors["Fe"] == 4.0 / 1.0
    assert ks.k_factors["Ca"] == 4.0 / 0.5
    assert ks.reference_element == "Si" and ks.excitation_kev == 2.9
    assert ks.provenance.params["source_energy_kev"] == source


def test_fused_k_reference_not_excited_raises():
    with pytest.raises(PayloadValidationError):
        fused_k_factors([_ref("Si", 14)], {"Si": None}, reference="Si")


def test_fused_k_applies_cross_energy_scale():
    s = {("Si", 2.9): 4.0, ("Fe", 13.55): 1.0}
    refs = [_ref("Si", 14), _ref("Fe", 26)]
    source = {"Si": 2.9, "Fe": 13.55}
    scale = {2.9: 0.5, 13.55: 1.0}
    ks = fused_k_factors(refs, source, reference="Si", scale=scale, _compute=_fake_compute(s))
    # Si (at 2.9) gets scaled by 0.5: k_Si = (4/4) * 0.5 = 0.5; Fe unscaled: 4/1 * 1 = 4
    assert ks.k_factors["Si"] == pytest.approx(0.5)
    assert ks.k_factors["Fe"] == pytest.approx(4.0)


# -- bridge-element cross-calibration (S8.6) ---------------------------------

def test_bridge_cross_calibration_derives_scale():
    # Si (edge 1.84) is excited at both energies -> a bridge element.
    per_energy_net = {2.9: {0: {"Si": 10.0}}, 13.55: {0: {"Si": 2.0}}}
    s = {("Si", 2.9): 2.0, ("Si", 13.55): 1.0}
    scale, diags = bridge_cross_calibration(
        per_energy_net, [_ref("Si", 14)], [2.9, 13.55], reference_energy=13.55,
        edge_fn=lambda r: 1.84, _compute=_fake_compute(s))
    # conc(Si,13.55)=2/1=2 ; conc(Si,2.9)=10/2=5 ; scale[2.9]=2/5=0.4
    assert scale[13.55] == 1.0
    assert scale[2.9] == pytest.approx(0.4)
    assert any(d.code == "bridge_cross_calibration" for d in diags)


def test_bridge_uses_true_median_for_even_count():
    # two bridge elements -> two ratios (2.0 and 4.0); the median is their mean (3.0),
    # not the upper-middle value (4.0) a naive ratios[len//2] would return.
    per_energy_net = {2.9: {0: {"Si": 1.0, "Mg": 1.0}}, 13.55: {0: {"Si": 2.0, "Mg": 4.0}}}
    s = {("Si", 2.9): 1.0, ("Si", 13.55): 1.0, ("Mg", 2.9): 1.0, ("Mg", 13.55): 1.0}
    scale, _ = bridge_cross_calibration(
        per_energy_net, [_ref("Si", 14), _ref("Mg", 12)], [2.9, 13.55],
        reference_energy=13.55, edge_fn=lambda r: 1.0, _compute=_fake_compute(s))
    assert scale[2.9] == pytest.approx(3.0)


def test_bridge_unresolved_energy_warns_and_leaves_scale_one():
    # Si is a bridge element (excited at both) but has no positive net at 2.9:
    # no usable pair -> scale stays 1.0 with an explicit per-energy warning.
    per_energy_net = {2.9: {0: {"Si": 0.0}}, 13.55: {0: {"Si": 2.0}}}
    s = {("Si", 2.9): 1.0, ("Si", 13.55): 1.0}
    scale, diags = bridge_cross_calibration(
        per_energy_net, [_ref("Si", 14)], [2.9, 13.55], reference_energy=13.55,
        edge_fn=lambda r: 1.0, _compute=_fake_compute(s))
    assert scale[2.9] == 1.0
    assert any(d.code == "bridge_unresolved_energy" and d.severity == "warning" for d in diags)


def test_bridge_weights_by_pixel_count():
    # one bridge element, two clusters (ratios 2 and 4); the 10x-heavier cluster dominates
    per = {2.9: {0: {"Si": 1.0}, 1: {"Si": 1.0}}, 13.55: {0: {"Si": 2.0}, 1: {"Si": 4.0}}}
    s = {("Si", 2.9): 1.0, ("Si", 13.55): 1.0}
    scale, _ = bridge_cross_calibration(
        per, [_ref("Si", 14)], [2.9, 13.55], reference_energy=13.55, edge_fn=lambda r: 1.0,
        cluster_weights={0: 10, 1: 1}, _compute=_fake_compute(s))
    assert scale[2.9] == pytest.approx(2.0)   # weighted-median pulled to the heavy cluster


def _two_cluster_high_dispersion():
    # ratios 1 and 5 -> dispersion 5x; weighted median (equal weight) = 3.0
    per = {2.9: {0: {"Si": 1.0}, 1: {"Si": 1.0}}, 13.55: {0: {"Si": 1.0}, 1: {"Si": 5.0}}}
    return per, {("Si", 2.9): 1.0, ("Si", 13.55): 1.0}


def test_bridge_low_confidence_flag_applies_with_warning():
    per, s = _two_cluster_high_dispersion()
    scale, diags = bridge_cross_calibration(
        per, [_ref("Si", 14)], [2.9, 13.55], reference_energy=13.55, edge_fn=lambda r: 1.0,
        dispersion_limit=2.0, on_low_confidence="flag", _compute=_fake_compute(s))
    assert scale[2.9] == pytest.approx(3.0)   # applied despite dispersion
    assert any(d.code == "bridge_low_confidence" and d.severity == "warning" for d in diags)


def test_bridge_low_confidence_refuse_leaves_scale_one():
    per, s = _two_cluster_high_dispersion()
    scale, diags = bridge_cross_calibration(
        per, [_ref("Si", 14)], [2.9, 13.55], reference_energy=13.55, edge_fn=lambda r: 1.0,
        dispersion_limit=2.0, on_low_confidence="refuse", _compute=_fake_compute(s))
    assert scale[2.9] == 1.0
    assert any(d.code == "bridge_low_confidence" for d in diags)


def test_bridge_low_confidence_raise():
    per, s = _two_cluster_high_dispersion()
    with pytest.raises(CrossCalibrationError):
        bridge_cross_calibration(
            per, [_ref("Si", 14)], [2.9, 13.55], reference_energy=13.55, edge_fn=lambda r: 1.0,
            dispersion_limit=2.0, on_low_confidence="raise", _compute=_fake_compute(s))


def test_bridge_cross_calibration_none_when_no_bridge():
    # Ca and Ti are each excited only at 13.55 keV (edges 4.04 / 4.97) -> no bridge.
    per_energy_net = {2.9: {0: {}}, 13.55: {0: {"Ca": 5.0, "Ti": 3.0}}}
    edges = {"Ca": 4.04, "Ti": 4.97}
    scale, diags = bridge_cross_calibration(
        per_energy_net, [_ref("Ca", 20), _ref("Ti", 22)], [2.9, 13.55], reference_energy=13.55,
        edge_fn=lambda r: edges[r.symbol], _compute=_fake_compute({}))
    assert scale == {2.9: 1.0, 13.55: 1.0}
    assert any(d.code == "bridge_none" for d in diags)


def test_real_xraylib_fused_k_factors():
    pytest.importorskip("xraylib")
    refs = [_ref("Si", 14), _ref("P", 15), _ref("Ca", 20), _ref("Fe", 26)]
    source = {"Si": 2.9, "P": 2.9, "Ca": 13.55, "Fe": 13.55}
    ks = fused_k_factors(refs, source, reference="Si")
    assert ks.k_factors["Si"] == 1.0
    assert all(v > 0 and v == v for v in ks.k_factors.values())
    assert set(ks.sensitivities) == {"Si", "P", "Ca", "Fe"}
    # P measured at 2.9 keV (its best energy) has a real, finite sensitivity
    assert ks.sensitivities["P"] > 0
