"""Tests for k-factor file adapters (Stage two, S3c-1)."""

from __future__ import annotations

import json

import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.io import SCHEMA_VERSION, read_kfactors, write_kfactors
from axiomm.analysis.quant.models import KFactorSet


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
    from axiomm.analysis.quant.io import read_quant, write_quant
    from axiomm.analysis.quant.models import QuantResult
    qr = QuantResult(
        net_intensities={"Si": 100.0, "Fe": 50.0},
        wt_percent_element={"Si": 50.0, "Fe": 50.0},
        wt_percent_oxide={"SiO2": 60.0, "FeO": 40.0},
        reference_element="Si",
        gross_intensities={"Si": 130.0, "Fe": 55.0},
        background_per_channel={"Si": 3.0, "Fe": 5.0},
        window_channels={"Si": 7, "Fe": 9},
        cluster_id=4,
        provenance=AnalysisProvenance(tool="quant", backend="cliff_lorimer",
                                      params={"reference": "Si"}),
        diagnostics=[Diagnostic("info", "element_not_measured", "x")],
    )
    write_quant(qr, tmp_path, "sample")
    back = read_quant(tmp_path, "sample")
    assert back.wt_percent_oxide == {"SiO2": 60.0, "FeO": 40.0}
    assert back.reference_element == "Si"
    assert back.gross_intensities == {"Si": 130.0, "Fe": 55.0}    # P4 retained
    assert back.window_channels == {"Si": 7, "Fe": 9}
    assert back.cluster_id == 4                                    # P8 identity
    assert back.provenance.backend == "cliff_lorimer"
    assert back.diagnostics[0].code == "element_not_measured"


def test_reliability_roundtrip(tmp_path):
    from axiomm.analysis.quant.io import read_reliability, write_reliability
    from axiomm.analysis.quant.reliability import ReliabilityReport
    r = ReliabilityReport(
        cluster_status="exploratory_only",
        element_status={"Si": "reportable", "K": "below_count_floor"},
        reasons=("heterogeneity 0.34 > 0.15",),
        cluster_id=2,
        provenance=AnalysisProvenance(tool="quant", backend="reliability", params={"count_floor": 50.0}),
        diagnostics=[Diagnostic("warning", "exploratory_cluster", "x")],
    )
    write_reliability(r, tmp_path, "sample")
    back = read_reliability(tmp_path, "sample")
    assert back.cluster_status == "exploratory_only"
    assert back.element_status["K"] == "below_count_floor"
    assert tuple(back.reasons) == ("heterogeneity 0.34 > 0.15",)
    assert back.cluster_id == 2
    assert back.diagnostics[0].code == "exploratory_cluster"


# --- P10: strict serialization (schema, kind, finiteness, corruption) ------

def test_write_rejects_nonfinite():
    import tempfile

    from axiomm.analysis.quant.io import write_quant
    from axiomm.analysis.quant.models import QuantResult
    d = tempfile.mkdtemp()
    qr = QuantResult(net_intensities={"Si": float("nan")}, wt_percent_element={},
                     wt_percent_oxide={}, reference_element="Si")
    with pytest.raises(ValueError):   # json allow_nan=False
        write_quant(qr, d, "bad")


def test_read_rejects_unsupported_schema(tmp_path):
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.quant.io import read_quant
    (tmp_path / "v_quant.json").write_text(json.dumps({
        "schema_version": 999, "kind": "quant", "net_intensities": {},
        "wt_percent_element": {}, "wt_percent_oxide": {}, "reference_element": "Si",
        "provenance": None, "diagnostics": []}))
    with pytest.raises(PayloadValidationError, match="schema_version"):
        read_quant(tmp_path, "v")


def test_read_rejects_wrong_kind(tmp_path):
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.quant.io import read_quant
    (tmp_path / "k_quant.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "kind": "reliability", "net_intensities": {},
        "wt_percent_element": {}, "wt_percent_oxide": {}, "reference_element": "Si",
        "provenance": None, "diagnostics": []}))
    with pytest.raises(PayloadValidationError, match="kind"):
        read_quant(tmp_path, "k")


def test_read_rejects_nonfinite_tokens(tmp_path):
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.quant.io import read_quant
    (tmp_path / "n_quant.json").write_text(
        '{"schema_version": 1, "kind": "quant", "net_intensities": {"Si": NaN}, '
        '"wt_percent_element": {}, "wt_percent_oxide": {}, "reference_element": "Si", '
        '"provenance": null, "diagnostics": []}')
    with pytest.raises(PayloadValidationError, match="non-finite"):
        read_quant(tmp_path, "n")


def test_read_rejects_malformed_json(tmp_path):
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.quant.io import read_quant
    (tmp_path / "m_quant.json").write_text("{not json")
    with pytest.raises(PayloadValidationError, match="malformed"):
        read_quant(tmp_path, "m")
