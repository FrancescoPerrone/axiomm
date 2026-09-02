"""Tests for quant payloads + dependency error (Stage two, S3c-1)."""

from __future__ import annotations

from axiomm.analysis.errors import AnalysisDependencyError, AxiommAnalysisError
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.quant.models import KFactorSet


def test_dependency_error_is_an_analysis_error():
    assert issubclass(AnalysisDependencyError, AxiommAnalysisError)


def test_kfactor_set_holds_fields():
    ks = KFactorSet(
        k_factors={"Si": 1.0, "Fe": 2.3},
        sensitivities={"Si": 100.0, "Fe": 43.0},
        reference_element="Si",
        excitation_kev=18.0,
        provenance=AnalysisProvenance(tool="quant", backend="kfactors_theoretical"),
    )
    assert ks.k_factors["Si"] == 1.0
    assert ks.reference_element == "Si"
    assert ks.excitation_kev == 18.0
    assert ks.diagnostics == []
