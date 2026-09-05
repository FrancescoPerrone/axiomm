"""Phase-A scientific-software gate regression tests for S3d.

One focused test (or small group) per gate finding, exercising the live
implementation. Findings: 1 reference-support gate, 2 reliability validation,
3 normalization registry, 4 match-result serialization, 5 exact-zero
observations, 6 reference-library validation, 7 metric-registry safety,
8 provenance completeness, 11 single-informative-element phases.
"""

from __future__ import annotations

import json

import pytest

from axiomm.analysis.errors import PayloadSerializationError, PayloadValidationError
from axiomm.analysis.mineralogy.match import (
    MatchConfig,
    Metric,
    get_metric,
    match_cluster,
    read_match,
    register_metric,
    write_match,
)
from axiomm.analysis.mineralogy.match.metrics import evaluate
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.quant.models import QuantResult
from axiomm.analysis.quant.reliability import ReliabilityReport, validate_reliability


def _ref(minerals=None):
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
        "P": ElementRef("P", 2.013, 30.974, 15, ("P2O5", 2, 5), "Ka"),
        "F": ElementRef("F", 0.677, 18.998, 9, None, "Ka"),
        "Fe": ElementRef("Fe", 6.404, 55.845, 26, ("FeO", 1, 1), "Ka"),
    }
    minerals = minerals or (
        MineralEndmember("Quartz", "silica", {"Si": 1, "O": 2}, None, "i", basis="atom_counts"),
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "i", basis="atom_counts"),
        MineralEndmember("Apatite", "apatite", {"Ca": 5, "P": 3, "O": 12, "F": 1}, None, "i", basis="atom_counts"),
        MineralEndmember("Magnetite", "oxide", {"Fe": 3, "O": 4}, None, "i", basis="atom_counts"),
    )
    return MineralogyReference(
        name="gate_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}),
        family_display={"silica": "Q", "olivine": "Ol", "apatite": "Ap", "oxide": "Ox"})


def _quant(cluster_id=0, obs=True, **wt):
    status = ({s: "measured_positive" for s in wt} if obs else {})
    return QuantResult(net_intensities={s: 1.0 for s in wt}, wt_percent_element=wt,
                       wt_percent_oxide={}, reference_element=next(iter(wt)),
                       observation_status=status, cluster_id=cluster_id)


def _rep(status="reportable_estimate", elstatus=None, cid=0):
    return ReliabilityReport(status, elstatus or {}, reasons=(), cluster_id=cid)


# ---- Finding 1: support-aware eligibility, not a tie-breaker ---------------

def test_finding1_low_support_candidate_ineligible():
    ref = _ref()
    qr = _quant(Mg=60.0, Si=40.0)
    r = match_cluster(qr, ref, reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}))
    assert r.best().name == "Forsterite"
    apat = next(c for c in r.insufficient if c.name == "Apatite")
    assert apat.outcome == "insufficient_evidence"
    assert apat.composition_coverage < 0.5


def test_finding1_high_similarity_low_support_gated():
    # A candidate that contains the measured element only as a MINOR component:
    # cosine on the shared dimension is ~1.0, but the element is a tiny fraction
    # of the candidate's composition, so the support gate (not min_informative)
    # must make it ineligible.
    minor = MineralEndmember("MinorMg", "olivine", {"Mg": 1, "Ca": 20, "O": 21}, None, "i",
                             basis="atom_counts")
    ref = _ref(minerals=(minor,))
    qr = _quant(Mg=100.0)
    r = match_cluster(qr, ref, reliability=_rep(elstatus={"Mg": "reportable"}),
                      config=MatchConfig(min_informative_dims=1, min_composition_coverage=0.5))
    cand = next(c for c in list(r.candidates) + list(r.insufficient) if c.name == "MinorMg")
    assert cand.raw_score > 0.99                       # high numerical similarity
    assert cand.composition_coverage < 0.5             # but inadequate support
    assert cand.outcome == "insufficient_evidence"     # -> not rank-eligible
    assert r.best() is None


def test_finding1_threshold_is_configurable_and_in_provenance():
    ref = _ref()
    qr = _quant(Mg=60.0, Si=40.0)
    r = match_cluster(qr, ref, reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}),
                      config=MatchConfig(min_composition_coverage=0.9))
    assert r.provenance.params["min_composition_coverage"] == 0.9


# ---- Finding 2: strict reliability validation -----------------------------

@pytest.mark.parametrize("report", [
    ReliabilityReport("quantitative", {}, reasons=()),                       # unknown cluster status
    ReliabilityReport("reportable_estimate", {"Si": "valid"}, reasons=()),   # unknown element status
    ReliabilityReport("reportable_estimate", {}, reasons=("x",)),            # contradiction
    ReliabilityReport("reportable_estimate", {"Si": "invalid"}, reasons=()), # invalid elem w/ reportable
    ReliabilityReport("exploratory_only", {"Si": "invalid"}, reasons=("x",)),# invalid elem, not invalid cluster
])
def test_finding2_validate_reliability_rejects(report):
    with pytest.raises(PayloadValidationError):
        validate_reliability(report)


def test_finding2_matcher_rejects_invalid_report():
    ref = _ref()
    with pytest.raises(PayloadValidationError):
        match_cluster(_quant(Si=100.0), ref,
                      reliability=ReliabilityReport("bogus", {}, reasons=()))


# ---- Finding 3: normalization registry ------------------------------------

def test_finding3_unsupported_normalization_rejected():
    with pytest.raises(PayloadValidationError, match="normalization"):
        MatchConfig(normalization="minmax")


def test_finding3_applied_normalization_recorded():
    ref = _ref()
    r = match_cluster(_quant(Mg=60.0, Si=40.0), ref,
                      reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}))
    assert r.provenance.params["normalization_applied"] == "sum_to_one"


# ---- Finding 4: match-result serialization hardening ----------------------

def _good_result(ref):
    return match_cluster(_quant(Mg=60.0, Si=40.0), ref,
                         reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}))


def test_finding4_malformed_provenance_raises_serialization(tmp_path):
    ref = _ref()
    write_match(_good_result(ref), tmp_path, "s")
    p = tmp_path / "s_match.json"
    doc = json.loads(p.read_text())
    doc["provenance"] = {"backend": "match"}   # missing 'tool'
    p.write_text(json.dumps(doc))
    with pytest.raises(PayloadSerializationError, match="provenance"):
        read_match(tmp_path, "s")


def test_finding4_candidate_ordering_enforced(tmp_path):
    ref = _ref()
    write_match(_good_result(ref), tmp_path, "s")
    p = tmp_path / "s_match.json"
    doc = json.loads(p.read_text())
    # duplicate a candidate out of order to break descending-score ordering
    if doc["candidates"]:
        c = dict(doc["candidates"][0], score=1.0, name="B")
        doc["candidates"] = [dict(doc["candidates"][0], score=0.1, name="A"), c]
        p.write_text(json.dumps(doc))
        with pytest.raises(PayloadSerializationError, match="ordered"):
            read_match(tmp_path, "s")


def test_finding4_n_info_consistency(tmp_path):
    ref = _ref()
    write_match(_good_result(ref), tmp_path, "s")
    p = tmp_path / "s_match.json"
    doc = json.loads(p.read_text())
    if doc["candidates"]:
        doc["candidates"][0]["n_informative_dims"] = 99
        p.write_text(json.dumps(doc))
        with pytest.raises(PayloadSerializationError, match="n_informative_dims"):
            read_match(tmp_path, "s")


def test_finding4_library_provenance_consistency(tmp_path):
    ref = _ref()
    write_match(_good_result(ref), tmp_path, "s")
    p = tmp_path / "s_match.json"
    doc = json.loads(p.read_text())
    doc["library_name"] = "something_else"
    p.write_text(json.dumps(doc))
    with pytest.raises(PayloadSerializationError, match="library_name"):
        read_match(tmp_path, "s")


def test_finding4_roundtrip_preserves_raw_score(tmp_path):
    ref = _ref()
    result = _good_result(ref)
    write_match(result, tmp_path, "s")
    back = read_match(tmp_path, "s")
    assert back.candidates[0].raw_score == result.candidates[0].raw_score


# ---- Finding 5: exact-zero observations -----------------------------------

def test_finding5_quantify_populates_observation_status():
    from axiomm.analysis.mineralogy.reference import ElementRef as ER
    from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet
    from axiomm.analysis.quant import compute_k_factors, quantify
    els = [ER("O", 0.525, 15.999, 8, None, "Ka"),
           ER("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
           ER("Fe", 6.404, 55.845, 26, ("FeO", 1, 1), "Ka")]
    k = compute_k_factors([els[1], els[2]], excitation_kev=18.0, reference="Si")
    # Si measured with signal, Fe not measured at all
    peaks = PeakMeasurementSet(measurements=(
        PeakMeasurement("Si", 1.74, 100.0, 120.0, 2.0, 5, True),))
    qr = quantify(peaks, k, els)
    assert qr.observation_status["Si"] == "measured_positive"
    assert qr.observation_status["Fe"] == "not_measured"


def test_finding5_manual_quantresult_emits_unknown_diagnostic():
    ref = _ref()
    qr = _quant(Mg=60.0, Si=40.0, obs=False)   # no observation_status
    r = match_cluster(qr, ref, reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}))
    assert any(d.code == "observation_status_unknown" for d in r.diagnostics)


def test_finding5_observation_status_roundtrips(tmp_path):
    from axiomm.analysis.quant.io import read_quant, write_quant
    qr = QuantResult(net_intensities={"Si": 100.0, "Fe": 0.0},
                     wt_percent_element={"Si": 100.0, "Fe": 0.0}, wt_percent_oxide={},
                     reference_element="Si",
                     gross_intensities={"Si": 120.0, "Fe": 5.0},
                     background_per_channel={"Si": 2.0, "Fe": 5.0},
                     window_channels={"Si": 5, "Fe": 5},
                     observation_status={"Si": "measured_positive", "Fe": "measured_zero"})
    write_quant(qr, tmp_path, "s")
    back = read_quant(tmp_path, "s")
    assert back.observation_status == {"Si": "measured_positive", "Fe": "measured_zero"}


# ---- Finding 6: strict reference-library validation before matching -------

def test_finding6_malformed_reference_rejected_by_matcher():
    els = {"O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
           "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka")}
    bad = MineralogyReference(
        name="bad", version="1", elements=els,
        minerals=(MineralEndmember("X", "s", {"Si": 1, "Zz": 1}, None, "i", basis="atom_counts"),),
        structural_exclude=frozenset({"O"}), family_display={"s": "S"})
    with pytest.raises(PayloadValidationError, match="not in the reference element set"):
        match_cluster(_quant(Si=100.0), bad,
                      reliability=_rep(elstatus={"Si": "reportable"}))


# ---- Finding 7: metric-registry safety ------------------------------------

def test_finding7_no_silent_overwrite():
    m = get_metric("cosine")
    with pytest.raises(PayloadValidationError, match="already registered"):
        register_metric(m)
    register_metric(m, replace=True)   # explicit replace is fine


def test_finding7_rejects_noncallable_and_bad_bounds():
    with pytest.raises(PayloadValidationError):
        register_metric(Metric("bad", "1", "similarity", (0.0, 1.0), "not callable", lambda r: r))
    with pytest.raises(PayloadValidationError):
        register_metric(Metric("bad2", "1", "similarity", (1.0, 0.0),
                               lambda a, b: 0.0, lambda r: r))


def test_finding7_evaluate_rejects_out_of_domain():
    bad = Metric("cursed", "1", "similarity", (0.0, 1.0), lambda a, b: 5.0, lambda r: r)
    with pytest.raises(PayloadValidationError, match="outside bounds"):
        evaluate(bad, [1.0], [1.0])


# ---- Finding 8: provenance completeness -----------------------------------

def test_finding8_provenance_is_complete():
    ref = _ref()
    qr = _quant(Mg=60.0, Si=40.0)
    qr.provenance = AnalysisProvenance("quant", "cliff_lorimer",
                                       params={"xraylib_version": "4.3.0",
                                               "xraylib_backend": "xraylib",
                                               "kfactor_method": "Kissel"})
    r = match_cluster(qr, ref, reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}))
    p = r.provenance.params
    for key in ("software_version", "schema_version", "metric", "metric_version",
                "normalization_applied", "min_composition_coverage",
                "input_measurement_digest", "library_name", "calibration_backend",
                "cross_section_version"):
        assert key in p, key
    assert p["library_name"] == r.library_name        # cross-object consistency
    assert p["calibration_backend"] == "xraylib"


# ---- Finding 11: single-informative-element phases ------------------------

def test_finding11_single_element_abstains_with_diagnostic():
    ref = _ref()
    qr = _quant(Si=100.0)   # one informative element only
    r = match_cluster(qr, ref, reliability=_rep(elstatus={"Si": "reportable"}))
    assert r.best() is None                            # abstains
    quartz = next(c for c in r.insufficient if c.name == "Quartz")
    assert quartz.n_informative_dims == 1
    assert any(d.code == "single_dimension_evidence" for d in r.diagnostics)


def test_finding11_multi_element_still_resolves():
    ref = _ref()
    r = match_cluster(_quant(Mg=60.0, Si=40.0), ref,
                      reliability=_rep(elstatus={"Mg": "reportable", "Si": "reportable"}))
    assert r.best() is not None and r.best().name == "Forsterite"
    assert r.best().n_informative_dims >= 2
