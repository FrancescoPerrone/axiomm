"""Tests for theoretical k-factors (Stage two, S3c-1)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import AnalysisDependencyError, PayloadValidationError
from axiomm.analysis.mineralogy.reference import ElementRef
from axiomm.analysis.quant import kfactors
from axiomm.analysis.quant.kfactors import compute_k_factors


def _si():
    return ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka")


def _fe():
    return ElementRef("Fe", 6.404, 55.845, 26, ("FeO", 1, 1), "Ka")


def test_non_positive_excitation_raises_without_xraylib():
    with pytest.raises(PayloadValidationError, match="excitation_kev"):
        compute_k_factors([_si(), _fe()], excitation_kev=0.0)


def test_reference_not_in_elements_raises_without_xraylib():
    with pytest.raises(PayloadValidationError, match="reference"):
        compute_k_factors([_si(), _fe()], excitation_kev=18.0, reference="Ca")


def test_missing_xraylib_raises_dependency_error(monkeypatch):
    def _boom():
        raise ImportError("no xraylib")

    monkeypatch.setattr(kfactors, "_import_xraylib", _boom)
    with pytest.raises(AnalysisDependencyError, match="xraylib"):
        compute_k_factors([_si(), _fe()], excitation_kev=18.0)


def test_duplicate_symbol_raises_without_xraylib():
    with pytest.raises(PayloadValidationError, match="duplicate"):
        compute_k_factors([_si(), _si()], excitation_kev=18.0)


def test_kfactors_with_xraylib():
    pytest.importorskip("xraylib")
    ks = compute_k_factors([_si(), _fe()], excitation_kev=18.0, reference="Si")
    assert ks.k_factors["Si"] == pytest.approx(1.0)
    assert ks.sensitivities["Si"] > 0
    assert ks.sensitivities["Fe"] > 0
    assert ks.provenance.params["excitation_kev"] == 18.0
    assert ks.provenance.params["reference"] == "Si"
    assert "xraylib_version" in ks.provenance.params
    # P5: the physical model / omitted effects are recorded, not implied
    assert "detector efficiency" in ks.provenance.params["physical_model"]
    # P7: the per-element cross-section method is recorded
    assert set(ks.provenance.params["line_method"]) == {"Si", "Fe"}


class _FakeXraylib:
    """Minimal xraylib stub: Kissel raises for a chosen Z, forcing fallback."""

    __version__ = "fake-0"
    KA_LINE = 0
    LA_LINE = 1

    def __init__(self, kissel_fails_for):
        self._fails = kissel_fails_for

    def XRayInit(self):
        pass

    def CS_FluorLine_Kissel(self, z, line, kev):
        if z in self._fails:
            raise ValueError("no Kissel partial cross-section")
        return 100.0

    def CS_FluorLine(self, z, line, kev):
        return 50.0


def test_kissel_fallback_recorded_in_provenance(monkeypatch):
    # Fe (Z=26) has no Kissel cross-section -> must fall back to CS_FluorLine,
    # record CS_FluorLine as the method for Fe, emit a diagnostic, and NOT
    # claim an all-Kissel method (P7).
    fake = _FakeXraylib(kissel_fails_for={26})
    monkeypatch.setattr(kfactors, "_import_xraylib", lambda: fake)
    ks = compute_k_factors([_si(), _fe()], excitation_kev=18.0, reference="Si")
    assert ks.provenance.params["line_method"]["Si"] == "CS_FluorLine_Kissel"
    assert ks.provenance.params["line_method"]["Fe"] == "CS_FluorLine"
    assert "mixed" in ks.provenance.params["method"]
    assert any(d.code == "kfactor_fallback" for d in ks.diagnostics)


def test_all_kissel_method_when_no_fallback(monkeypatch):
    fake = _FakeXraylib(kissel_fails_for=set())
    monkeypatch.setattr(kfactors, "_import_xraylib", lambda: fake)
    ks = compute_k_factors([_si(), _fe()], excitation_kev=18.0, reference="Si")
    assert "Kissel" in ks.provenance.params["method"]
    assert "mixed" not in ks.provenance.params["method"]
    assert not any(d.code == "kfactor_fallback" for d in ks.diagnostics)


class _ZeroSensitivityXraylib(_FakeXraylib):
    """xraylib stub returning a non-positive sensitivity for one element."""

    def __init__(self, zero_for):
        super().__init__(kissel_fails_for=set())
        self._zero_for = zero_for

    def CS_FluorLine_Kissel(self, z, line, kev):
        return 0.0 if z in self._zero_for else 100.0


def test_nonpositive_sensitivity_raises_not_nan(monkeypatch):
    # finding 8: a non-positive sensitivity must raise here, not return a
    # NaN-containing KFactorSet that downstream code immediately rejects.
    fake = _ZeroSensitivityXraylib(zero_for={26})   # Fe
    monkeypatch.setattr(kfactors, "_import_xraylib", lambda: fake)
    with pytest.raises(PayloadValidationError, match="non-positive or non-finite"):
        compute_k_factors([_si(), _fe()], excitation_kev=18.0, reference="Si")
