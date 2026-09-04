"""Executable semantics for S3d exploratory mineral matching (rev. 2).

These tests encode the acceptance criteria of
``docs/specs/stage_two_S3d_mineral_matching_design.md`` **before** the matcher
is implemented. The whole module is skipped (the ``mineralogy.match`` module
does not exist yet) so the suite stays green; they are the contract to review,
and the red/green target once implementation is approved. Imports and the
controlled-reference fixture live inside each test, so collection never fails on
the not-yet-existing module or the not-yet-added ``MineralEndmember.basis``.

Remove the module-level skip when implementation begins, one test at a time.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="S3d matcher not yet implemented; design under review (see "
    "docs/specs/stage_two_S3d_mineral_matching_design.md)."
)


# --------------------------------------------------------------------------
# a small CONTROLLED reference, so ranking/censoring assertions are exact
# --------------------------------------------------------------------------

def _controlled_reference():
    """A tiny mineralogy reference with known endmembers and both bases.

    Includes Forsterite twice — once as atom counts, once as the equivalent
    mass fractions — so the basis conversion can be checked to converge.
    """
    from axiomm.analysis.mineralogy.reference import (
        ElementRef,
        MineralEndmember,
        MineralogyReference,
    )

    elements = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Al": ElementRef("Al", 1.486, 26.982, 13, ("Al2O3", 2, 3), "Ka"),
        "K": ElementRef("K", 3.314, 39.098, 19, ("K2O", 2, 1), "Ka"),
    }
    a_mg, a_si = elements["Mg"].atomic_weight, elements["Si"].atomic_weight
    # mass fractions equivalent to Mg2SiO4 cations (Mg:2, Si:1)
    m_mg, m_si = 2 * a_mg, 1 * a_si
    tot = m_mg + m_si
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1}, None,
                         "ideal", basis="atom_counts"),
        MineralEndmember("Forsterite_glass", "olivine",
                         {"Mg": 100 * m_mg / tot, "Si": 100 * m_si / tot}, None,
                         "standard", basis="mass_fraction"),
        MineralEndmember("Orthoclase", "feldspar", {"K": 1, "Al": 1, "Si": 3}, None,
                         "ideal", basis="atom_counts"),
        MineralEndmember("Quartz", "silica", {"Si": 1}, None, "ideal",
                         basis="atom_counts"),
    )
    return MineralogyReference(
        name="controlled_test_v1", version="1",
        elements=elements, minerals=minerals,
        structural_exclude=frozenset({"O"}),
        family_display={"olivine": "Olivine", "feldspar": "Feldspar",
                        "silica": "Silica"},
    )


def _quant(**wt):
    from axiomm.analysis.quant.models import QuantResult
    cid = wt.pop("cluster_id", 0)
    return QuantResult(net_intensities={k: 1.0 for k in wt}, wt_percent_element=wt,
                       wt_percent_oxide={}, reference_element=next(iter(wt)), cluster_id=cid)


def _report(status, elstatus, cid=0):
    from axiomm.analysis.quant.reliability import ReliabilityReport
    return ReliabilityReport(cluster_status=status, element_status=elstatus,
                             reasons=(), cluster_id=cid)


# Criterion 1 --- basis conversion is the only path to the metric
def test_two_bases_of_same_phase_converge_and_rank_each_other():
    from axiomm.analysis.mineralogy.match import match_cluster

    ref = _controlled_reference()
    a_mg = ref.elements["Mg"].atomic_weight
    a_si = ref.elements["Si"].atomic_weight
    m_mg, m_si = 2 * a_mg, 1 * a_si
    tot = m_mg + m_si
    # a cluster measured as forsterite MASS fractions
    qr = _quant(Mg=100 * m_mg / tot, Si=100 * m_si / tot)
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    top = result.candidates[0].name
    assert top in ("Forsterite", "Forsterite_glass")
    # the two same-phase endmembers score (almost) identically after conversion
    scores = {c.name: c.score for c in result.candidates}
    assert abs(scores["Forsterite"] - scores["Forsterite_glass"]) < 1e-6


def test_atom_count_ideal_ranks_first_for_its_own_mass_cluster():
    from axiomm.analysis.mineralogy.match import match_cluster

    ref = _controlled_reference()
    qr = _quant(K=14.0, Al=9.7, Si=30.2)   # orthoclase-ish mass fractions
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate",
        {"K": "reportable", "Al": "reportable", "Si": "reportable"}))
    assert result.candidates[0].name == "Orthoclase"


# Criterion 2 --- included basis (F/S/Cl retained; O/Br/I excluded) recorded
def test_effective_basis_recorded_and_excludes_oxygen():
    from axiomm.analysis.mineralogy.match import match_cluster

    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    excluded = result.provenance.params["excluded_elements"]
    assert "O" in excluded
    assert "Si" not in excluded and "Mg" not in excluded


# Criterion 3 --- evidence support: sparse overlap is not a perfect match
def test_single_element_overlap_is_insufficient_evidence():
    from axiomm.analysis.mineralogy.match import MatchConfig, match_cluster

    ref = _controlled_reference()
    qr = _quant(Si=100.0)   # only Si -> overlaps Quartz on one dimension
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Si": "reportable"}),
        config=MatchConfig(min_informative_dims=3))
    quartz = [c for c in result.candidates if c.name == "Quartz"]
    # Quartz is either omitted or flagged, never a scored best match
    assert result.best() is None or result.best().name != "Quartz"
    if quartz:
        assert quartz[0].outcome == "insufficient_evidence"
        assert quartz[0].n_informative_dims == 1


def test_candidate_reports_coverage_and_evidence_fields():
    from axiomm.analysis.mineralogy.match import match_cluster

    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    cand = result.candidates[0]
    assert set(cand.elements_used) <= {"Mg", "Si"}
    assert 0.0 <= cand.coverage <= 1.0
    assert cand.n_informative_dims == len(cand.elements_used)


# Criterion 4 --- censoring vs zeroing (diluted-K Lisheen failure mode)
def test_below_floor_k_is_censored_not_zeroed():
    from axiomm.analysis.mineralogy.match import MatchConfig, MissingDataPolicy, match_cluster

    ref = _controlled_reference()
    qr = _quant(Si=70.0, Al=12.0, K=0.2)
    report = _report("reportable_estimate",
                     {"Si": "reportable", "Al": "reportable", "K": "below_count_floor"})
    result = match_cluster(qr, ref, reliability=report,
                           config=MatchConfig(missing_data=MissingDataPolicy("exclude")))
    assert "K" in result.candidates[0].elements_censored
    # Orthoclase (K-bearing) is not excluded merely because K is below floor
    assert any(c.name == "Orthoclase" for c in result.candidates)


def test_zero_policy_warns_and_differs_from_exclude():
    from axiomm.analysis.mineralogy.match import MatchConfig, MissingDataPolicy, match_cluster

    ref = _controlled_reference()
    qr = _quant(Si=70.0, Al=12.0, K=0.2)
    report = _report("reportable_estimate",
                     {"Si": "reportable", "Al": "reportable", "K": "below_count_floor"})
    zeroed = match_cluster(qr, ref, reliability=report,
                           config=MatchConfig(missing_data=MissingDataPolicy("zero")))
    exclude = match_cluster(qr, ref, reliability=report,
                            config=MatchConfig(missing_data=MissingDataPolicy("exclude")))
    assert any(d.severity == "warning" for d in zeroed.diagnostics)   # zero mode warns
    assert [c.name for c in zeroed.candidates] != [c.name for c in exclude.candidates]


# Criterion 5 --- reliability gating (required / explicit ungated / invalid)
def test_missing_report_requires_explicit_ungated_opt_in():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.errors import PayloadValidationError

    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    with pytest.raises(PayloadValidationError):
        match_cluster(qr, ref)   # no report, no opt-in
    ungated = match_cluster(qr, ref, allow_ungated=True)
    assert ungated.reliability_gated is False
    assert ungated.input_reliability == "ungated"
    assert any(d.severity == "warning" and d.code == "ungated_match"
               for d in ungated.diagnostics)


def test_invalid_status_raises():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.errors import PayloadValidationError

    ref = _controlled_reference()
    qr = _quant(Si=100.0)
    with pytest.raises(PayloadValidationError):
        match_cluster(qr, ref, reliability=_report("invalid", {"Si": "invalid"}))


def test_exploratory_only_needs_opt_in():
    from axiomm.analysis.mineralogy.match import match_cluster

    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    report = _report("exploratory_only", {"Mg": "reportable", "Si": "reportable"})
    guarded = match_cluster(qr, ref, reliability=report)
    assert guarded.candidates == ()
    assert any(d.severity == "warning" for d in guarded.diagnostics)
    opted = match_cluster(qr, ref, reliability=report, rank_exploratory=True)
    assert opted.candidates
    assert any(d.severity == "warning" for d in opted.diagnostics)


# Criterion 6 --- metric contract: rank_score in [0,1]; no min_score = 2.0
def test_min_score_out_of_unit_interval_rejected():
    from axiomm.analysis.mineralogy.match import MatchConfig

    from axiomm.analysis.errors import PayloadValidationError

    with pytest.raises(PayloadValidationError):
        MatchConfig(min_score=2.0)   # thresholds live in [0, 1], not a cosine range
    with pytest.raises(PayloadValidationError):
        MatchConfig(min_score=-0.1)


def test_ranking_is_by_rank_score_and_thresholded():
    from axiomm.analysis.mineralogy.match import MatchConfig, match_cluster

    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    report = _report("reportable_estimate", {"Mg": "reportable", "Si": "reportable"})
    result = match_cluster(qr, ref, reliability=report)
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in scores)
    # an achievable-but-unmet threshold yields nothing and best() is None
    empty = match_cluster(qr, ref, reliability=report, config=MatchConfig(min_score=0.999999))
    assert empty.candidates == () or all(c.outcome != "scored" for c in empty.candidates)
    assert empty.best() is None


# Criterion 7 --- identity + provenance propagation
def test_result_propagates_identity_and_provenance():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.models import AnalysisProvenance
    from axiomm.analysis.quant.models import QuantResult

    ref = _controlled_reference()
    qr = QuantResult(net_intensities={"Mg": 1.0, "Si": 1.0},
                     wt_percent_element={"Mg": 48.0, "Si": 35.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=7,
                     provenance=AnalysisProvenance("quant", "cliff_lorimer",
                                                   params={"kfactor_values": {"Si": 1.0}}))
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}, cid=7))
    assert result.cluster_id == 7
    assert result.input_reliability == "reportable_estimate"
    assert result.library_name == "controlled_test_v1"
    assert result.library_version == "1"
    assert "kfactor_values" in str(result.provenance.params)


def test_report_cluster_id_mismatch_raises():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.errors import PayloadValidationError

    ref = _controlled_reference()
    qr = _quant(Si=100.0, cluster_id=10)
    with pytest.raises(PayloadValidationError, match="cluster_id"):
        match_cluster(qr, ref, reliability=_report("reportable_estimate",
                                                   {"Si": "reportable"}, cid=11))


# Criterion 7/8 --- batch aligns one-to-one by cluster_id
def test_batch_aligns_by_cluster_id_one_to_one():
    from axiomm.analysis.mineralogy.match import match_clusters

    ref = _controlled_reference()
    a = _quant(Si=100.0, cluster_id=0)
    b = _quant(Mg=48.0, Si=35.0, cluster_id=1)
    ra = _report("reportable_estimate", {"Si": "reportable"}, cid=0)
    rb = _report("reportable_estimate", {"Mg": "reportable", "Si": "reportable"}, cid=1)
    results = match_clusters([b, a], ref, reliabilities=[rb, ra])   # reordered
    assert [r.cluster_id for r in results] == [0, 1]


# Criterion 9 --- config validation
def test_match_config_rejects_bad_values():
    from axiomm.analysis.mineralogy.match import MatchConfig

    from axiomm.analysis.errors import PayloadValidationError

    for bad in (dict(min_score=float("nan")), dict(top_k=0), dict(top_k=1.5),
                dict(min_informative_dims=0), dict(min_informative_dims=2.5)):
        with pytest.raises(PayloadValidationError):
            MatchConfig(**bad)


# Criterion 10 --- match I/O is strict and deeply validated
def test_match_io_roundtrip_and_strict_read(tmp_path):
    from axiomm.analysis.mineralogy.match import match_cluster, read_match, write_match

    from axiomm.analysis.errors import PayloadSerializationError

    ref = _controlled_reference()
    qr = _quant(Mg=48.0, Si=35.0)
    result = match_cluster(qr, ref, reliability=_report(
        "reportable_estimate", {"Mg": "reportable", "Si": "reportable"}))
    write_match(result, tmp_path, "sample")
    back = read_match(tmp_path, "sample")
    assert back.cluster_id == result.cluster_id
    # unsupported schema version rejected
    (tmp_path / "v_match.json").write_text('{"schema_version": 999, "kind": "match"}')
    with pytest.raises(PayloadSerializationError):
        read_match(tmp_path, "v")
    # wrong kind rejected
    (tmp_path / "k_match.json").write_text('{"schema_version": 1, "kind": "quant"}')
    with pytest.raises(PayloadSerializationError):
        read_match(tmp_path, "k")


def test_match_write_validates_before_writing(tmp_path):
    from axiomm.analysis.mineralogy.match import MineralCandidate, MineralMatchResult, write_match

    from axiomm.analysis.errors import PayloadValidationError

    # a candidate with an out-of-range score must be rejected, writing nothing
    bad = MineralMatchResult(
        cluster_id=0,
        candidates=(MineralCandidate(name="X", family="f", score=1.5, elements_used=("Si",),
                                     coverage=1.0, elements_censored=(), elements_unavailable=(),
                                     n_informative_dims=1, outcome="scored", basis="molar"),),
        input_reliability="reportable_estimate", reliability_gated=True,
        library_name="controlled_test_v1", library_version="1",
    )
    with pytest.raises(PayloadValidationError):
        write_match(bad, tmp_path, "bad")
    assert not (tmp_path / "bad_match.json").exists()
