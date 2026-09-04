"""Executable acceptance tests for S3d exploratory mineral matching.

A controlled reference (atom-count + mass-fraction endmembers of the same
phase) makes ranking, basis-conversion and censoring assertions exact.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadSerializationError, PayloadValidationError
from axiomm.analysis.mineralogy.match import (
    MatchConfig,
    MineralCandidate,
    MineralMatchResult,
    MissingDataPolicy,
    match_cluster,
    match_clusters,
    read_match,
    write_match,
)
from axiomm.analysis.mineralogy.match.basis import to_molar_proportions
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.quant.models import QuantResult
from axiomm.analysis.quant.reliability import ReliabilityReport


def _controlled_reference():
    elements = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Al": ElementRef("Al", 1.486, 26.982, 13, ("Al2O3", 2, 3), "Ka"),
        "K": ElementRef("K", 3.314, 39.098, 19, ("K2O", 2, 1), "Ka"),
        "F": ElementRef("F", 0.677, 18.998, 9, None, "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
        "P": ElementRef("P", 2.013, 30.974, 15, ("P2O5", 2, 5), "Ka"),
    }
    a_mg, a_si = elements["Mg"].atomic_weight, elements["Si"].atomic_weight
    m_mg, m_si = 2 * a_mg, 1 * a_si          # mass fractions of Mg2SiO4 cations
    tot = m_mg + m_si
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1}, None,
                         "ideal", basis="atom_counts"),
        MineralEndmember("Forsterite_glass", "olivine",
                         {"Mg": 100 * m_mg / tot, "Si": 100 * m_si / tot}, None,
                         "standard", basis="element_mass_fraction"),
        MineralEndmember("Orthoclase", "feldspar", {"K": 1, "Al": 1, "Si": 3}, None,
                         "ideal", basis="atom_counts"),
        MineralEndmember("Quartz", "silica", {"Si": 1}, None, "ideal", basis="atom_counts"),
        # F/Cl-bearing phase: F retention must be able to discriminate it
        MineralEndmember("Fluorapatite", "apatite", {"Ca": 5, "P": 3, "F": 1}, None,
                         "ideal", basis="atom_counts"),
    )
    return MineralogyReference(
        name="controlled_test_v1", version="1", elements=elements, minerals=minerals,
        structural_exclude=frozenset({"O"}),
        family_display={"olivine": "Olivine", "feldspar": "Feldspar",
                        "silica": "Silica", "apatite": "Apatite"},
    )


def _quant(cluster_id=0, **wt):
    return QuantResult(net_intensities={k: 1.0 for k in wt}, wt_percent_element=wt,
                       wt_percent_oxide={}, reference_element=next(iter(wt)),
                       cluster_id=cluster_id)


def _report(status, elstatus, cid=0):
    return ReliabilityReport(cluster_status=status, element_status=elstatus,
                             reasons=(), cluster_id=cid)


def _find(result, name):
    for c in list(result.candidates) + list(result.insufficient):
        if c.name == name:
            return c
    return None


# --- Criterion 1: basis conversion is the only path to the metric ----------

def test_two_bases_of_same_phase_converge_and_rank_each_other():
    ref = _controlled_reference()
    a_mg, a_si = ref.elements["Mg"].atomic_weight, ref.elements["Si"].atomic_weight
    m_mg, m_si = 2 * a_mg, 1 * a_si
    tot = m_mg + m_si
    qr = _quant(Mg=100 * m_mg / tot, Si=100 * m_si / tot)
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    scores = {c.name: c.score for c in result.candidates}
    assert result.candidates[0].name in ("Forsterite", "Forsterite_glass")
    assert abs(scores["Forsterite"] - scores["Forsterite_glass"]) < 1e-9


def test_oxide_mass_fraction_conversion_matches_hand_calc():
    ref = _controlled_reference()
    # pure SiO2 (oxide wt% 100) -> cation moles = 1*100/60.083 -> Si proportion 1.0
    v = to_molar_proportions({"Si": 100.0}, "oxide_mass_fraction", ref,
                             allowed=set(ref.element_order()) - {"O"})
    assert v == pytest.approx({"Si": 1.0})
    # MgO 40.3 wt% + SiO2 60.08 wt% -> 1 mol Mg-cation + 1 mol Si-cation -> 0.5/0.5
    v2 = to_molar_proportions({"Mg": 40.304, "Si": 60.083}, "oxide_mass_fraction", ref,
                              allowed={"Mg", "Si"})
    assert v2["Mg"] == pytest.approx(0.5, abs=1e-3)


def test_metric_receives_the_converted_vector():
    # the metric must receive MOLAR proportions, not the raw mass fractions
    import axiomm.analysis.mineralogy.match.match as M
    ref = _controlled_reference()
    calls = []
    real = M.get_metric

    def spy(name):
        metric = real(name)

        def raw(a, b):
            calls.append((list(a), list(b)))
            return metric.raw(a, b)
        return metric.__class__(metric.name, metric.kind, metric.raw_bounds, raw,
                                metric.rank_score)
    M.get_metric = spy
    try:
        qr = _quant(Mg=60.0, Si=40.0)   # MASS %
        match_cluster(qr, ref, reliability=_report(
            "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    finally:
        M.get_metric = real
    # molar Si proportion of {Mg:60, Si:40} mass% (0.366) — NOT the mass fraction 0.40
    d = 60.0 / 24.305 + 40.0 / 28.085
    molar_si = (40.0 / 28.085) / d
    seen_si = {round(v, 6) for a, _ in calls for v in a}
    assert round(molar_si, 6) in seen_si
    assert round(0.40, 6) not in seen_si          # mass fraction never reaches the metric


# --- Criterion 2: F/S/Cl retained + O excluded, recorded -------------------

def test_oxygen_excluded_and_recorded():
    ref = _controlled_reference()
    result = match_cluster(_quant(Mg=48.0, Si=35.0), ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    assert "O" in result.provenance.params["excluded_elements"]
    assert "Si" not in result.provenance.params["excluded_elements"]
    assert "F" in result.provenance.params["included_elements"]   # F retained


def test_fluorine_is_discriminating():
    ref = _controlled_reference()
    # a Ca-P-F cluster should surface Fluorapatite, using F as a real dimension
    qr = _quant(Ca=54.0, P=32.0, F=9.0)
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Ca": "reportable", "P": "reportable", "F": "reportable"}))
    top = result.best()
    assert top is not None and top.name == "Fluorapatite"
    assert "F" in top.elements_used


# --- Criterion 3: evidence support -----------------------------------------

def test_single_element_overlap_is_insufficient_evidence():
    ref = _controlled_reference()
    qr = _quant(Si=100.0)          # one element only
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Si": "reportable"}))
    assert result.best() is None                     # nothing rank-eligible
    quartz = _find(result, "Quartz")
    assert quartz.outcome == "insufficient_evidence" and quartz.n_informative_dims == 1


def test_candidate_reports_dimension_and_composition_coverage():
    ref = _controlled_reference()
    result = match_cluster(_quant(Mg=48.0, Si=35.0), ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    fo = _find(result, "Forsterite")
    assert set(fo.elements_used) == {"Mg", "Si"}
    assert 0.0 <= fo.dimension_coverage <= 1.0
    assert fo.composition_coverage == pytest.approx(1.0)      # Mg+Si is all of forsterite
    assert fo.n_informative_dims == len(fo.elements_used)


# --- Criterion 4: censoring vs zeroing (diluted-K Lisheen failure mode) -----

def test_below_floor_k_is_censored_not_zeroed():
    ref = _controlled_reference()
    qr = _quant(Si=70.0, Al=12.0, K=0.2)
    report = _report("reportable_estimate",
                     {"Si": "reportable", "Al": "reportable", "K": "below_count_floor"})
    result = match_cluster(qr, ref, reliability=report,
                           config=MatchConfig(missing_data=MissingDataPolicy("exclude")))
    ortho = _find(result, "Orthoclase")
    assert ortho is not None and ortho.outcome == "scored"    # not excluded by censored K
    assert "K" in ortho.elements_censored


def test_zero_policy_warns_and_penalizes():
    ref = _controlled_reference()
    qr = _quant(Si=70.0, Al=12.0, K=0.2)
    report = _report("reportable_estimate",
                     {"Si": "reportable", "Al": "reportable", "K": "below_count_floor"})
    zeroed = match_cluster(qr, ref, reliability=report,
                           config=MatchConfig(missing_data=MissingDataPolicy("zero")))
    exclude = match_cluster(qr, ref, reliability=report,
                            config=MatchConfig(missing_data=MissingDataPolicy("exclude")))
    assert any(d.code == "zero_missing_data_mode" for d in zeroed.diagnostics)
    # zeroing K (a candidate element) penalizes Orthoclase's score
    assert _find(zeroed, "Orthoclase").score < _find(exclude, "Orthoclase").score


def test_unavailable_distinct_from_censored():
    ref = _controlled_reference()
    qr = _quant(Si=70.0, Al=12.0)     # K never measured at all
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Si": "reportable", "Al": "reportable"}))
    ortho = _find(result, "Orthoclase")
    assert "K" in ortho.elements_unavailable
    assert "K" not in ortho.elements_censored


# --- Criterion 5: reliability gating ---------------------------------------

def test_missing_report_requires_explicit_ungated_opt_in():
    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    with pytest.raises(PayloadValidationError):
        match_cluster(qr, ref)
    ungated = match_cluster(qr, ref, allow_ungated=True)
    assert ungated.reliability_gated is False
    assert ungated.input_reliability == "ungated"
    assert any(d.code == "ungated_match" and d.severity == "warning"
               for d in ungated.diagnostics)


def test_invalid_status_raises():
    ref = _controlled_reference()
    with pytest.raises(PayloadValidationError):
        match_cluster(_quant(Si=100.0), ref, reliability=_report("invalid", {"Si": "invalid"}))


def test_exploratory_only_needs_opt_in():
    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    report = _report("exploratory_only", {"Mg": "reportable", "Si": "reportable"})
    guarded = match_cluster(qr, ref, reliability=report)
    assert guarded.candidates == ()
    assert any(d.severity == "warning" for d in guarded.diagnostics)
    opted = match_cluster(qr, ref, reliability=report, rank_exploratory=True)
    assert opted.candidates
    assert any(d.severity == "warning" for d in opted.diagnostics)


def test_unaudited_reference_is_rejected():
    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1
    with pytest.raises(PayloadValidationError, match="basis-audited"):
        match_cluster(_quant(Si=100.0), MINERALOGY_DEFAULT_V1,
                      reliability=_report("reportable_estimate", {"Si": "reportable"}))


# --- Criterion 6: metric contract ------------------------------------------

def test_min_score_out_of_unit_interval_rejected():
    with pytest.raises(PayloadValidationError):
        MatchConfig(min_score=2.0)
    with pytest.raises(PayloadValidationError):
        MatchConfig(min_score=-0.1)


def test_ranking_by_score_and_threshold():
    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    report = _report("reportable_estimate", {"Mg": "reportable", "Si": "reportable"})
    result = match_cluster(qr, ref, reliability=report)
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)
    empty = match_cluster(qr, ref, reliability=report, config=MatchConfig(min_score=0.999999))
    assert empty.candidates == () and empty.best() is None


# --- Criterion 7: identity + provenance ------------------------------------

def test_result_propagates_identity_and_provenance():
    ref = _controlled_reference()
    qr = QuantResult(net_intensities={"Mg": 1.0, "Si": 1.0},
                     wt_percent_element={"Mg": 48.0, "Si": 35.0}, wt_percent_oxide={},
                     reference_element="Si", cluster_id=7,
                     provenance=AnalysisProvenance("quant", "cliff_lorimer",
                                                   params={"kfactor_values": {"Si": 1.0}}))
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}, cid=7))
    assert result.cluster_id == 7
    assert result.input_reliability == "reportable_estimate"
    assert result.library_name == "controlled_test_v1" and result.library_version == "1"
    assert "kfactor_values" in str(result.provenance.params)


def test_report_cluster_id_mismatch_raises():
    ref = _controlled_reference()
    with pytest.raises(PayloadValidationError, match="cluster_id"):
        match_cluster(_quant(cluster_id=10, Si=100.0), ref,
                      reliability=_report("reportable_estimate", {"Si": "reportable"}, cid=11))


def test_batch_aligns_by_cluster_id_one_to_one():
    ref = _controlled_reference()
    a = _quant(cluster_id=0, Si=100.0)
    b = _quant(cluster_id=1, Mg=48.0, Si=35.0)
    ra = _report("reportable_estimate", {"Si": "reportable"}, cid=0)
    rb = _report("reportable_estimate", {"Mg": "reportable", "Si": "reportable"}, cid=1)
    results = match_clusters([b, a], ref, reliabilities=[rb, ra])   # reordered
    assert [r.cluster_id for r in results] == [0, 1]


def test_batch_rejects_non_bijective_reliabilities():
    ref = _controlled_reference()
    a = _quant(cluster_id=0, Si=100.0)
    b = _quant(cluster_id=1, Si=100.0)
    ra = _report("reportable_estimate", {"Si": "reportable"}, cid=0)
    with pytest.raises(PayloadValidationError):
        match_clusters([a, b], ref, reliabilities=[ra])   # missing cid=1


# --- Criterion 9: config validation ----------------------------------------

def test_match_config_rejects_bad_values():
    for bad in (dict(min_score=float("nan")), dict(top_k=0), dict(top_k=1.5),
                dict(min_informative_dims=0), dict(min_informative_dims=2.5),
                dict(min_coverage=1.5)):
        with pytest.raises(PayloadValidationError):
            MatchConfig(**bad)


def test_penalize_missing_data_is_deferred():
    with pytest.raises(PayloadValidationError, match="deferred"):
        MissingDataPolicy("penalize")


# --- Criterion 10: strict match I/O ----------------------------------------

def test_match_io_roundtrip_and_strict_read(tmp_path):
    ref = _controlled_reference()
    result = match_cluster(_quant(Mg=48.0, Si=35.0), ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    write_match(result, tmp_path, "sample")
    back = read_match(tmp_path, "sample")
    assert back.cluster_id == result.cluster_id
    assert [c.name for c in back.candidates] == [c.name for c in result.candidates]
    import json
    (tmp_path / "v_match.json").write_text(json.dumps({"schema_version": 999, "kind": "match"}))
    with pytest.raises(PayloadSerializationError):
        read_match(tmp_path, "v")
    (tmp_path / "k_match.json").write_text(json.dumps({"schema_version": 1, "kind": "quant"}))
    with pytest.raises(PayloadSerializationError):
        read_match(tmp_path, "k")


def test_match_write_validates_before_writing(tmp_path):
    bad = MineralMatchResult(
        cluster_id=0,
        candidates=(MineralCandidate(name="X", family="f", score=1.5, outcome="scored",
                                     elements_used=("Si",), elements_censored=(),
                                     elements_unavailable=(), n_informative_dims=1,
                                     dimension_coverage=1.0, composition_coverage=1.0,
                                     basis="molar_proportions"),),
        input_reliability="reportable_estimate", reliability_gated=True,
        library_name="controlled_test_v1", library_version="1")
    with pytest.raises(PayloadSerializationError):
        write_match(bad, tmp_path, "bad")
    assert not (tmp_path / "bad_match.json").exists()


def test_read_match_rejects_bad_outcome(tmp_path):
    import json
    doc = {"schema_version": 1, "kind": "match", "cluster_id": 0,
           "input_reliability": "reportable_estimate", "reliability_gated": True,
           "library_name": "x", "library_version": "1",
           "candidates": [{"name": "Q", "family": "f", "score": 0.9, "outcome": "bogus",
                           "elements_used": ["Si"], "elements_censored": [],
                           "elements_unavailable": [], "n_informative_dims": 1,
                           "dimension_coverage": 1.0, "composition_coverage": 1.0,
                           "basis": "molar_proportions"}],
           "insufficient": [], "provenance": None, "diagnostics": []}
    (tmp_path / "b_match.json").write_text(json.dumps(doc))
    with pytest.raises(PayloadSerializationError, match="outcome"):
        read_match(tmp_path, "b")


# --- Exploratory-only, never an identification -----------------------------

def test_result_is_ranking_never_identification():
    ref = _controlled_reference()
    result = match_cluster(_quant(Mg=48.0, Si=35.0), ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    # there is no single-label field; best() is just the top candidate or None
    assert not hasattr(result, "identification")
    assert result.best() is None or isinstance(result.best(), MineralCandidate)
    # numpy import kept meaningful (silences unused import if trimmed later)
    assert np.isfinite(result.candidates[0].score)
