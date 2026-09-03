"""Executable semantics for S3d exploratory mineral matching.

These tests encode the acceptance criteria of
``docs/specs/stage_two_S3d_mineral_matching_design.md`` **before** the matcher
is implemented. They are skipped as a whole (the ``mineralogy.match`` module
does not exist yet) so the suite stays green; they are the contract to review,
and the red/green target once implementation is approved. Imports live inside
each test so collection never fails on the missing module.

Remove the module-level skip when implementation begins, one test at a time.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="S3d matcher not yet implemented; design under review (see "
    "docs/specs/stage_two_S3d_mineral_matching_design.md)."
)


# Criterion 1 + 2 --- mass -> molar conversion is the only path to the metric
def test_pure_endmember_ranks_itself_first_via_molar_conversion():
    """A cluster whose mass fractions come from one endmember ranks it first.

    The cluster's cation *mass* fractions must be converted to molar/cation
    proportions (÷ atomic weight, renormalise) before scoring; comparing mass
    fractions directly to the stoichiometric-count vectors would misrank.
    """
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult

    # forsterite-like Mg2SiO4: cation counts Mg:2, Si:1 -> convert to the
    # equivalent MASS fractions, feed those, and expect forsterite ranked #1.
    a_mg, a_si = REF.elements["Mg"].atomic_weight, REF.elements["Si"].atomic_weight
    mass_mg = 2 * a_mg
    mass_si = 1 * a_si
    tot = mass_mg + mass_si
    qr = QuantResult(
        net_intensities={"Mg": 1.0, "Si": 1.0},
        wt_percent_element={"Mg": 100 * mass_mg / tot, "Si": 100 * mass_si / tot},
        wt_percent_oxide={}, reference_element="Si", cluster_id=0,
    )
    result = match_cluster(qr, REF)
    assert result.candidates, "expected at least one candidate"
    assert "forsterite" in result.candidates[0].name.lower()


def test_metric_never_sees_raw_mass_fractions():
    """The public API converts to molar proportions; the metric receives those.

    Two clusters that share the same molar/cation proportions but differ only by
    a (mass-space) rescaling must produce identical rankings.
    """
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult

    base = QuantResult(net_intensities={"Mg": 1.0, "Si": 1.0},
                       wt_percent_element={"Mg": 60.0, "Si": 40.0},
                       wt_percent_oxide={}, reference_element="Si", cluster_id=1)
    scaled = QuantResult(net_intensities={"Mg": 1.0, "Si": 1.0},
                         wt_percent_element={"Mg": 30.0, "Si": 20.0},  # same ratio
                         wt_percent_oxide={}, reference_element="Si", cluster_id=1)
    r1 = match_cluster(base, REF)
    r2 = match_cluster(scaled, REF)
    assert [c.name for c in r1.candidates] == [c.name for c in r2.candidates]


# Criterion 3 --- censored (below-floor / unmeasured) elements are not zeros
def test_below_floor_element_is_censored_not_zeroed():
    """Diluted K (Lisheen failure mode) must not be treated as confirmed zero.

    With the default ``exclude`` policy, a below-floor K neither confirms nor
    refutes K-bearing candidates, which therefore remain in the ranking.
    """
    from axiomm.analysis.mineralogy.match import MatchConfig, MissingDataPolicy, match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult
    from axiomm.analysis.quant.reliability import ReliabilityReport

    qr = QuantResult(net_intensities={"Si": 2000.0, "Al": 500.0, "K": 6.0},
                     wt_percent_element={"Si": 70.0, "Al": 12.0, "K": 0.2},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=2)
    report = ReliabilityReport(
        cluster_status="reportable_estimate",
        element_status={"Si": "reportable", "Al": "reportable", "K": "below_count_floor"},
        reasons=(), cluster_id=2,
    )
    cfg = MatchConfig(missing_data=MissingDataPolicy("exclude"))
    result = match_cluster(qr, REF, reliability=report, config=cfg)
    assert "K" in result.candidates[0].elements_censored
    # a K-bearing feldspar remains a candidate rather than being excluded
    assert any("feldspar" in c.family.lower() or "K" in c.name for c in result.candidates)


def test_zero_policy_differs_from_exclude_policy():
    from axiomm.analysis.mineralogy.match import MatchConfig, MissingDataPolicy, match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult
    from axiomm.analysis.quant.reliability import ReliabilityReport

    qr = QuantResult(net_intensities={"Si": 2000.0, "Al": 500.0, "K": 6.0},
                     wt_percent_element={"Si": 70.0, "Al": 12.0, "K": 0.2},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=3)
    report = ReliabilityReport(cluster_status="reportable_estimate",
                               element_status={"Si": "reportable", "Al": "reportable",
                                               "K": "below_count_floor"},
                               reasons=(), cluster_id=3)
    exclude = match_cluster(qr, REF, reliability=report,
                            config=MatchConfig(missing_data=MissingDataPolicy("exclude")))
    zeroed = match_cluster(qr, REF, reliability=report,
                           config=MatchConfig(missing_data=MissingDataPolicy("zero")))
    assert [c.name for c in exclude.candidates] != [c.name for c in zeroed.candidates]


# Criterion 4 --- reliability gating
def test_invalid_cluster_status_raises():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult
    from axiomm.analysis.quant.reliability import ReliabilityReport

    qr = QuantResult(net_intensities={"Si": 1.0}, wt_percent_element={"Si": 100.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=4)
    report = ReliabilityReport(cluster_status="invalid", element_status={"Si": "invalid"},
                               reasons=("bad",), cluster_id=4)
    with pytest.raises(PayloadValidationError):
        match_cluster(qr, REF, reliability=report)


def test_exploratory_only_needs_explicit_opt_in():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult
    from axiomm.analysis.quant.reliability import ReliabilityReport

    qr = QuantResult(net_intensities={"Si": 100.0, "Mg": 60.0},
                     wt_percent_element={"Si": 40.0, "Mg": 60.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=5)
    report = ReliabilityReport(cluster_status="exploratory_only",
                               element_status={"Si": "reportable", "Mg": "reportable"},
                               reasons=("heterogeneity high",), cluster_id=5)
    # default: no candidates, but an explicit warning diagnostic
    guarded = match_cluster(qr, REF, reliability=report)
    assert guarded.candidates == ()
    assert any(d.severity == "warning" for d in guarded.diagnostics)
    # opt in: candidates returned, still carrying the warning
    opted = match_cluster(qr, REF, reliability=report, rank_exploratory=True)
    assert opted.candidates
    assert any(d.severity == "warning" for d in opted.diagnostics)


# Criterion 5 --- identity + provenance propagation
def test_result_propagates_identity_and_provenance():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.models import AnalysisProvenance
    from axiomm.analysis.quant.models import QuantResult

    qr = QuantResult(net_intensities={"Si": 100.0, "Mg": 60.0},
                     wt_percent_element={"Si": 40.0, "Mg": 60.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=7,
                     provenance=AnalysisProvenance("quant", "cliff_lorimer",
                                                   params={"kfactor_values": {"Si": 1.0}}))
    result = match_cluster(qr, REF)
    assert result.cluster_id == 7
    assert result.library_name == REF.name
    assert result.library_version == REF.version
    assert "kfactor_values" in result.provenance.params.get("upstream_quant", {}) \
        or "kfactor_values" in str(result.provenance.params)


# Criterion 6 --- configurable, provenance-recorded metric/normalization/thresholds
def test_config_is_honoured_and_recorded():
    from axiomm.analysis.mineralogy.match import MatchConfig, match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult

    qr = QuantResult(net_intensities={"Si": 100.0, "Mg": 60.0},
                     wt_percent_element={"Si": 40.0, "Mg": 60.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=8)
    cfg = MatchConfig(top_k=3, min_score=0.5)
    result = match_cluster(qr, REF, config=cfg)
    assert len(result.candidates) <= 3
    assert all(c.score >= 0.5 for c in result.candidates)
    assert result.provenance.params["top_k"] == 3
    assert result.provenance.params["min_score"] == 0.5


# Criterion 7 --- ranked list, no unconditional single label
def test_returns_ranked_list_and_best_may_be_none():
    from axiomm.analysis.mineralogy.match import MatchConfig, match_cluster

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult

    qr = QuantResult(net_intensities={"Si": 100.0, "Mg": 60.0},
                     wt_percent_element={"Si": 40.0, "Mg": 60.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=9)
    # scores descending
    result = match_cluster(qr, REF)
    scores = [c.score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)
    # an impossible threshold yields no candidates and best() is None
    empty = match_cluster(qr, REF, config=MatchConfig(min_score=2.0))
    assert empty.candidates == ()
    assert empty.best() is None


# Criterion 8 --- batch identity, one-to-one by cluster_id
def test_reliability_cluster_id_mismatch_raises():
    from axiomm.analysis.mineralogy.match import match_cluster

    from axiomm.analysis.errors import PayloadValidationError
    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult
    from axiomm.analysis.quant.reliability import ReliabilityReport

    qr = QuantResult(net_intensities={"Si": 100.0}, wt_percent_element={"Si": 100.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=10)
    report = ReliabilityReport(cluster_status="reportable_estimate",
                               element_status={"Si": "reportable"}, reasons=(),
                               cluster_id=11)  # mismatched id
    with pytest.raises(PayloadValidationError, match="cluster_id"):
        match_cluster(qr, REF, reliability=report)


def test_batch_aligns_by_cluster_id_one_to_one():
    from axiomm.analysis.mineralogy.match import match_clusters

    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult

    a = QuantResult(net_intensities={"Si": 100.0}, wt_percent_element={"Si": 100.0},
                    wt_percent_oxide={}, reference_element="Si", cluster_id=0)
    b = QuantResult(net_intensities={"Mg": 60.0, "Si": 40.0},
                    wt_percent_element={"Mg": 60.0, "Si": 40.0},
                    wt_percent_oxide={}, reference_element="Si", cluster_id=1)
    results = match_clusters([b, a], REF)   # reordered
    assert [r.cluster_id for r in results] == [0, 1]


# Criterion 9 --- match I/O is strict and deeply validated
def test_match_io_roundtrip_and_strict_read(tmp_path):
    from axiomm.analysis.mineralogy.match import match_cluster, read_match, write_match

    from axiomm.analysis.errors import PayloadSerializationError
    from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
    from axiomm.analysis.quant.models import QuantResult

    qr = QuantResult(net_intensities={"Si": 100.0, "Mg": 60.0},
                     wt_percent_element={"Si": 40.0, "Mg": 60.0},
                     wt_percent_oxide={}, reference_element="Si", cluster_id=0)
    result = match_cluster(qr, REF)
    write_match(result, tmp_path, "sample")
    back = read_match(tmp_path, "sample")
    assert back.cluster_id == result.cluster_id
    (tmp_path / "bad_match.json").write_text('{"schema_version": 999, "kind": "match"}')
    with pytest.raises(PayloadSerializationError):
        read_match(tmp_path, "bad")


# Criterion 10 --- config dataclasses reject bad values
def test_match_config_rejects_bad_values():
    from axiomm.analysis.mineralogy.match import MatchConfig

    from axiomm.analysis.errors import PayloadValidationError

    for bad in (dict(min_score=float("nan")), dict(top_k=0), dict(top_k=1.5),
                dict(min_score=-1.0)):
        with pytest.raises(PayloadValidationError):
            MatchConfig(**bad)
