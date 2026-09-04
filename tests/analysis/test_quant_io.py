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

def test_write_rejects_nonfinite(tmp_path):
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.quant.io import write_quant
    from axiomm.analysis.quant.models import QuantResult
    qr = QuantResult(net_intensities={"Si": float("nan")}, wt_percent_element={},
                     wt_percent_oxide={}, reference_element="Si")
    # validate-before-write catches the non-finite value before it is dumped
    with pytest.raises(PayloadValidationError):
        write_quant(qr, tmp_path, "bad")
    assert not (tmp_path / "bad_quant.json").exists()   # nothing was persisted


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


# --- finding 6: explicit schema evolution (v1 -> v2) -----------------------

def test_schema_version_is_two():
    assert SCHEMA_VERSION == 2


def test_read_rejects_legacy_v1_clearly(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    # a legacy v1-shaped quant doc (schema_version 1, no gross/window/kind fields)
    (tmp_path / "old_quant.json").write_text(json.dumps({
        "schema_version": 1, "net_intensities": {}, "wt_percent_element": {},
        "wt_percent_oxide": {}, "reference_element": "Si",
        "provenance": None, "diagnostics": []}))
    with pytest.raises(PayloadSerializationError, match="schema_version"):
        read_quant(tmp_path, "old")


# --- finding 3: deep validation of the deserialized payload ----------------

def _valid_quant_doc():
    return {
        "schema_version": SCHEMA_VERSION, "kind": "quant",
        "net_intensities": {"Si": 100.0}, "wt_percent_element": {"Si": 100.0},
        "wt_percent_oxide": {"SiO2": 100.0}, "reference_element": "Si",
        "gross_intensities": {"Si": 120.0}, "background_per_channel": {"Si": 2.0},
        "window_channels": {"Si": 7}, "cluster_id": 3,
        "provenance": None, "diagnostics": [],
    }


def _write(tmp_path, stem, doc):
    (tmp_path / f"{stem}_quant.json").write_text(json.dumps(doc))


def test_read_rejects_negative_gross(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["gross_intensities"] = {"Si": -1.0}
    _write(tmp_path, "g", doc)
    with pytest.raises(PayloadSerializationError, match="gross_intensities"):
        read_quant(tmp_path, "g")


def test_read_rejects_non_integer_window(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["window_channels"] = {"Si": 2.5}
    _write(tmp_path, "w", doc)
    with pytest.raises(PayloadSerializationError, match="window_channels"):
        read_quant(tmp_path, "w")


def test_read_rejects_inconsistent_element_keys(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["gross_intensities"] = {"Fe": 10.0}  # Fe not in net
    _write(tmp_path, "k", doc)
    with pytest.raises(PayloadSerializationError, match="absent from net_intensities"):
        read_quant(tmp_path, "k")


def test_read_rejects_non_integer_cluster_id(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["cluster_id"] = "3"
    _write(tmp_path, "c", doc)
    with pytest.raises(PayloadSerializationError, match="cluster_id"):
        read_quant(tmp_path, "c")


def test_read_rejects_bad_provenance_structure(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["provenance"] = {"backend": "x"}   # missing tool
    _write(tmp_path, "p", doc)
    with pytest.raises(PayloadSerializationError, match="provenance"):
        read_quant(tmp_path, "p")


def test_read_reliability_rejects_bad_status_vocabulary(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_reliability
    (tmp_path / "s_reliability.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "kind": "reliability",
        "cluster_status": "quantitative",   # retired vocabulary
        "element_status": {"Si": "reportable"}, "reasons": [],
        "cluster_id": None, "provenance": None, "diagnostics": []}))
    with pytest.raises(PayloadSerializationError, match="cluster_status"):
        read_reliability(tmp_path, "s")


def test_read_reliability_rejects_bad_element_status(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_reliability
    (tmp_path / "e_reliability.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "kind": "reliability",
        "cluster_status": "reportable_estimate",
        "element_status": {"Si": "valid"},   # retired vocabulary
        "reasons": [], "cluster_id": None, "provenance": None, "diagnostics": []}))
    with pytest.raises(PayloadSerializationError, match="element_status"):
        read_reliability(tmp_path, "e")


# --- relational validation of quantification fields ------------------------

def test_read_rejects_reference_not_in_net(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["reference_element"] = "Zz"   # not a measured element
    _write(tmp_path, "r", doc)
    with pytest.raises(PayloadSerializationError, match="reference_element"):
        read_quant(tmp_path, "r")


def test_read_rejects_wt_element_key_not_in_net(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["wt_percent_element"] = {"Fe": 100.0}   # Fe not in net_intensities
    _write(tmp_path, "we", doc)
    with pytest.raises(PayloadSerializationError, match="wt_percent_element"):
        read_quant(tmp_path, "we")


# --- validate-before-write: a malformed payload is never persisted ---------

def test_write_quant_validates_before_writing(tmp_path):
    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.quant.io import write_quant
    from axiomm.analysis.quant.models import QuantResult
    # reference element absent from net_intensities -> rejected, nothing written
    qr = QuantResult(net_intensities={"Fe": 10.0}, wt_percent_element={"Fe": 100.0},
                     wt_percent_oxide={}, reference_element="Si")
    with pytest.raises(PayloadValidationError):
        write_quant(qr, tmp_path, "bad")
    assert not (tmp_path / "bad_quant.json").exists()


# --- additional quant persistence invariants (audit-closure point 4) -------

def test_read_rejects_negative_net(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["net_intensities"] = {"Si": -1.0}
    doc["reference_element"] = "Si"
    doc["gross_intensities"] = {}
    doc["background_per_channel"] = {}
    doc["window_channels"] = {}
    doc["wt_percent_element"] = {}
    _write(tmp_path, "nn", doc)
    with pytest.raises(PayloadSerializationError, match="net_intensities"):
        read_quant(tmp_path, "nn")


def test_read_rejects_net_greater_than_gross(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["net_intensities"] = {"Si": 200.0}
    doc["gross_intensities"] = {"Si": 100.0}   # net > gross
    _write(tmp_path, "ng", doc)
    with pytest.raises(PayloadSerializationError, match="exceeds gross"):
        read_quant(tmp_path, "ng")


def test_read_rejects_negative_wt_percent(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_quant
    doc = _valid_quant_doc()
    doc["wt_percent_oxide"] = {"SiO2": -5.0}
    _write(tmp_path, "nw", doc)
    with pytest.raises(PayloadSerializationError, match="wt_percent_oxide"):
        read_quant(tmp_path, "nw")


def test_read_kfactors_rejects_nonpositive_sensitivity(tmp_path):
    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.quant.io import read_kfactors
    (tmp_path / "s_kfactors.json").write_text(json.dumps({
        "schema_version": SCHEMA_VERSION, "kind": "kfactors",
        "k_factors": {"Si": 1.0}, "sensitivities": {"Si": 0.0},   # non-positive
        "reference_element": "Si", "excitation_kev": 18.0,
        "provenance": None, "diagnostics": []}))
    with pytest.raises(PayloadSerializationError, match="sensitivities"):
        read_kfactors(tmp_path, "s")
