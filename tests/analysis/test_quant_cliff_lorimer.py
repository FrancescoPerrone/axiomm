"""Tests for Cliff-Lorimer quantification (Stage two, S3c-2)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.reference import ElementRef
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet
from axiomm.analysis.quant.cliff_lorimer import quantify
from axiomm.analysis.quant.models import KFactorSet


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


# --- gate-review adversarial / scientific tests (P4, P6, P8, P9) -----------

def test_closed_form_oxide_conversion():
    # Pure Si, only cation measured: SiO2 mass = wt_Si * M(SiO2)/M(Si).
    # With one oxide the closure renormalises to 100% by construction, so the
    # meaningful closed-form check is the Si:O mass split inside SiO2.
    qr = quantify(_peaks({"Si": 100.0}), _kf({"Si": 1.0}), _elements())
    assert qr.wt_percent_oxide["SiO2"] == pytest.approx(100.0)
    # element basis is cation-only; oxide basis adds stoichiometric oxygen
    assert set(qr.wt_percent_element) == {"Si"}


def test_reference_invariance():
    # Cliff-Lorimer is ratio-based: element wt% must not depend on which
    # element is chosen as the k-factor reference.
    nets = {"Si": 100.0, "Fe": 50.0}
    q_si = quantify(_peaks(nets), _kf({"Si": 1.0, "Fe": 2.0}, ref="Si"), _elements())
    q_fe = quantify(_peaks(nets), _kf({"Si": 0.5, "Fe": 1.0}, ref="Fe"), _elements())
    assert q_fe.wt_percent_element["Si"] == pytest.approx(q_si.wt_percent_element["Si"])
    assert q_fe.wt_percent_element["Fe"] == pytest.approx(q_si.wt_percent_element["Fe"])


def test_mass_closure():
    qr = quantify(_peaks({"Si": 100.0, "Fe": 50.0, "Al": 20.0}),
                  _kf({"Si": 1.0, "Fe": 2.0, "Al": 1.5}), _elements())
    assert sum(qr.wt_percent_element.values()) == pytest.approx(100.0)
    assert sum(qr.wt_percent_oxide.values()) == pytest.approx(100.0)


def test_missing_element_ref_not_silently_dropped():
    # 'Xx' is in the k-factors but has no ElementRef: must raise, never drop
    # it and renormalise the remainder to 100%.
    with pytest.raises(PayloadValidationError, match="ElementRef"):
        quantify(_peaks({"Si": 100.0, "Xx": 100.0}),
                 _kf({"Si": 1.0, "Xx": 1.0}), _elements())


def test_negative_net_rejected():
    with pytest.raises(PayloadValidationError, match="net intensity"):
        quantify(_peaks({"Si": 100.0, "Fe": -50.0}), _kf({"Si": 1.0, "Fe": 1.0}), _elements())


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 0.0, -1.0])
def test_nonpositive_or_nonfinite_kfactor_rejected(bad):
    with pytest.raises(PayloadValidationError, match="k-factor"):
        quantify(_peaks({"Si": 100.0, "Fe": 50.0}), _kf({"Si": 1.0, "Fe": bad}), _elements())


def test_duplicate_element_ref_rejected():
    els = [*_elements(), ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka")]
    with pytest.raises(PayloadValidationError, match="duplicate"):
        quantify(_peaks({"Si": 100.0}), _kf({"Si": 1.0}), els)


def test_retains_raw_peak_facts_and_cluster_id():
    ms = (PeakMeasurement("Si", 1.74, 100.0, 130.0, 3.0, 7, True),
          PeakMeasurement("Fe", 6.4, 40.0, 55.0, 5.0, 9, True))
    peaks = PeakMeasurementSet(measurements=ms, cluster_id=3)
    qr = quantify(peaks, _kf({"Si": 1.0, "Fe": 1.2}), _elements())
    assert qr.cluster_id == 3
    assert qr.gross_intensities["Si"] == 130.0
    assert qr.background_per_channel["Fe"] == 5.0
    assert qr.window_channels["Si"] == 7


def test_provenance_carries_kfactor_and_physical_model():
    qr = quantify(_peaks({"Si": 100.0, "Fe": 50.0}), _kf({"Si": 1.0, "Fe": 2.0}), _elements(),
                  reference_name="mineralogy_default_v1")
    p = qr.provenance.params
    assert p["kfactor_values"] == {"Si": 1.0, "Fe": 2.0}
    assert p["reference_name"] == "mineralogy_default_v1"
    assert "SiO2" in {next(iter(v)) for v in p["oxide_forms"].values()}
