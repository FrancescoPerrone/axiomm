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


def test_kfactors_with_xraylib():
    pytest.importorskip("xraylib")
    ks = compute_k_factors([_si(), _fe()], excitation_kev=18.0, reference="Si")
    assert ks.k_factors["Si"] == pytest.approx(1.0)
    assert ks.sensitivities["Si"] > 0
    assert ks.sensitivities["Fe"] > 0
    assert ks.provenance.params["excitation_kev"] == 18.0
    assert ks.provenance.params["reference"] == "Si"
    assert "xraylib_version" in ks.provenance.params
