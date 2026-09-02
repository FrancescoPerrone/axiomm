"""Tests for Cliff-Lorimer quantification (Stage two, S3c-2)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.mineralogy.reference import ElementRef
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet
from axiomm.analysis.quant.models import KFactorSet
from axiomm.analysis.quant.cliff_lorimer import quantify


def _elements():
    return [
        ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        ElementRef("Fe", 6.404, 55.845, 26, ("FeO", 1, 1), "Ka"),
        ElementRef("Al", 1.486, 26.982, 13, ("Al2O3", 2, 3), "Ka"),
        ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
    ]


def _peaks(nets):
    ms = tuple(PeakMeasurement(s, 0.0, n, n, 0.0, 1, True) for s, n in nets.items())
    return PeakMeasurementSet(measurements=ms)


def _kf(kf, ref="Si"):
    return KFactorSet(
        k_factors=kf, sensitivities={}, reference_element=ref, excitation_kev=18.0,
        provenance=AnalysisProvenance(tool="quant", backend="kfactors_theoretical",
                                      params={"excitation_kev": 18.0, "method": "theoretical"}),
    )


def test_wt_element_ratio():
    qr = quantify(_peaks({"Si": 100.0, "Fe": 50.0}), _kf({"Si": 1.0, "Fe": 2.0}), _elements())
    assert qr.wt_percent_element["Si"] == pytest.approx(50.0)
    assert qr.wt_percent_element["Fe"] == pytest.approx(50.0)
    assert qr.provenance.params["reference"] == "Si"


def test_pure_si_gives_sio2_100():
    qr = quantify(_peaks({"Si": 100.0, "Fe": 0.0}), _kf({"Si": 1.0, "Fe": 2.0}), _elements())
    assert qr.wt_percent_oxide["SiO2"] == pytest.approx(100.0)


def test_two_oxides_sum_to_100():
    qr = quantify(_peaks({"Si": 100.0, "Al": 100.0}), _kf({"Si": 1.0, "Al": 1.0}), _elements())
    assert sum(qr.wt_percent_oxide.values()) == pytest.approx(100.0)
    assert "SiO2" in qr.wt_percent_oxide and "Al2O3" in qr.wt_percent_oxide


def test_net_ref_zero_falls_back_with_diagnostic():
    qr = quantify(_peaks({"Si": 0.0, "Fe": 50.0}), _kf({"Si": 1.0, "Fe": 2.0}), _elements())
    assert qr.wt_percent_element["Fe"] == pytest.approx(100.0)
    assert any(d.code == "no_reference_intensity" for d in qr.diagnostics)


def test_kfactor_element_not_measured_diagnostic():
    qr = quantify(_peaks({"Si": 100.0}), _kf({"Si": 1.0, "Ca": 1.0}), _elements())
    assert qr.net_intensities["Ca"] == 0.0
    assert any(d.code == "element_not_measured" for d in qr.diagnostics)


def test_no_signal_diagnostic():
    qr = quantify(_peaks({"Si": 0.0, "Fe": 0.0}), _kf({"Si": 1.0, "Fe": 1.0}), _elements())
    assert all(v == 0.0 for v in qr.wt_percent_element.values())
    assert any(d.code == "no_signal" for d in qr.diagnostics)


def test_reference_not_in_kfactors_raises():
    with pytest.raises(PayloadValidationError, match="reference"):
        quantify(_peaks({"Fe": 50.0}), _kf({"Fe": 2.0}, ref="Si"), _elements())


def test_missing_oxygen_raises():
    els = [e for e in _elements() if e.symbol != "O"]
    with pytest.raises(PayloadValidationError, match="O"):
        quantify(_peaks({"Si": 100.0}), _kf({"Si": 1.0}), els)


def test_batch_quantify_cluster_means():
    from axiomm.analysis.quant import quantify_cluster_means
    sets = [_peaks({"Si": 100.0, "Fe": 50.0}), _peaks({"Si": 100.0, "Fe": 0.0})]
    out = quantify_cluster_means(sets, _kf({"Si": 1.0, "Fe": 2.0}), _elements())
    assert len(out) == 2
    assert out[1].wt_percent_element["Fe"] == pytest.approx(0.0)
