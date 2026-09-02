"""Tests for k-factor file adapters (Stage two, S3c-1)."""

from __future__ import annotations

import json

import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.models import KFactorSet
from axiomm.analysis.quant.io import SCHEMA_VERSION, read_kfactors, write_kfactors


def _ks():
    return KFactorSet(
        k_factors={"Si": 1.0, "Fe": 2.3},
        sensitivities={"Si": 100.0, "Fe": 43.0},
        reference_element="Si",
        excitation_kev=18.0,
        provenance=AnalysisProvenance(tool="quant", backend="kfactors_theoretical",
                                      params={"reference": "Si"}),
        diagnostics=[Diagnostic("warning", "zero_sensitivity", "x")],
    )


def test_roundtrip(tmp_path):
    write_kfactors(_ks(), tmp_path, "sample")
    back = read_kfactors(tmp_path, "sample")
    assert back.k_factors == {"Si": 1.0, "Fe": 2.3}
    assert back.sensitivities == {"Si": 100.0, "Fe": 43.0}
    assert back.reference_element == "Si"
    assert back.excitation_kev == 18.0
    assert back.provenance.backend == "kfactors_theoretical"
    assert back.diagnostics[0].code == "zero_sensitivity"


def test_schema_version_recorded(tmp_path):
    write_kfactors(_ks(), tmp_path, "sample")
    doc = json.loads((tmp_path / "sample_kfactors.json").read_text())
    assert doc["schema_version"] == SCHEMA_VERSION


def test_refuses_silent_overwrite(tmp_path):
    write_kfactors(_ks(), tmp_path, "sample")
    with pytest.raises(OutputExistsError):
        write_kfactors(_ks(), tmp_path, "sample")
    write_kfactors(_ks(), tmp_path, "sample", overwrite=True)


def test_quant_roundtrip(tmp_path):
    from axiomm.analysis.quant.models import QuantResult
    from axiomm.analysis.quant.io import read_quant, write_quant
    qr = QuantResult(
        net_intensities={"Si": 100.0, "Fe": 50.0},
        wt_percent_element={"Si": 50.0, "Fe": 50.0},
        wt_percent_oxide={"SiO2": 60.0, "FeO": 40.0},
        reference_element="Si",
        provenance=AnalysisProvenance(tool="quant", backend="cliff_lorimer",
                                      params={"reference": "Si"}),
        diagnostics=[Diagnostic("info", "element_not_measured", "x")],
    )
    write_quant(qr, tmp_path, "sample")
    back = read_quant(tmp_path, "sample")
    assert back.wt_percent_oxide == {"SiO2": 60.0, "FeO": 40.0}
    assert back.reference_element == "Si"
    assert back.provenance.backend == "cliff_lorimer"
    assert back.diagnostics[0].code == "element_not_measured"
