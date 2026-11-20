"""S7.1 — classification policies over matching evidence."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from axiomm.analysis.errors import BackendNotFoundError, PayloadValidationError
from axiomm.analysis.mineralogy.classify import (
    ClassificationPolicy,
    PermissivePolicy,
    ThresholdPolicy,
    classifiers,
    classify_clusters,
)
from axiomm.analysis.mineralogy.classify.models import UNRESOLVED_NAME
from axiomm.analysis.mineralogy.match.io import _cand_to_dict, _validate_candidate
from axiomm.analysis.mineralogy.match.models import MineralCandidate, MineralMatchResult

REF = SimpleNamespace(family_display={
    "phlogopite_mica": "Mica (phlogopite family)",
    "clinopyroxene_pyroxene": "Pyroxene / mafic silicate",
    "rutile_ti_oxide": "Ti oxide (rutile family)",
    "amphibole": "Amphibole",
})


def _cand(name, family, score, obs=0.9, ndim=2):
    return MineralCandidate(
        name=name, family=family, score=score, raw_score=score, outcome="scored",
        elements_used=tuple(f"e{i}" for i in range(ndim)), elements_censored=(),
        elements_unavailable=(), n_informative_dims=ndim, dimension_coverage=1.0,
        composition_coverage=1.0, observation_coverage=obs, basis="molar_proportions")


def _result(cid, cands):
    return MineralMatchResult(
        cluster_id=cid, candidates=tuple(cands), input_reliability="reportable_estimate",
        reliability_gated=True, library_name="t", library_version="1")


# -- ThresholdPolicy decision branches ---------------------------------------

def test_species_when_clear_strong_leader():
    lab = ThresholdPolicy().classify(
        _result(0, [_cand("Rutile (measured)", "rutile_ti_oxide", 0.95),
                    _cand("Ilmenite", "fe_ti_oxide", 0.70)]), REF)
    assert lab.level == "species" and lab.name == "Rutile (measured)"
    assert lab.family == "rutile_ti_oxide"


def test_family_when_within_family_tie():
    """Two micas within the margin -> family label (the A21_066 mica case)."""
    lab = ThresholdPolicy().classify(
        _result(1, [_cand("Std UGY(mica)", "phlogopite_mica", 0.60),
                    _cand("Phlogopite (measured)", "phlogopite_mica", 0.57)]), REF)
    assert lab.level == "family" and lab.name == "Mica (phlogopite family)"
    assert lab.family == "phlogopite_mica"
    assert set(lab.contenders) == {"Std UGY(mica)", "Phlogopite (measured)"}


def test_family_when_clear_leader_below_species_floor():
    """Clear leader but modest score -> family, not species (the cpx case)."""
    lab = ThresholdPolicy().classify(
        _result(2, [_cand("Hedenbergite", "clinopyroxene_pyroxene", 0.696),
                    _cand("Amphibole", "amphibole", 0.60)]), REF)
    assert lab.level == "family" and lab.name == "Pyroxene / mafic silicate"


def test_unresolved_when_best_below_family_floor():
    lab = ThresholdPolicy().classify(_result(3, [_cand("x", "phlogopite_mica", 0.40)]), REF)
    assert lab.level == "unresolved" and lab.name == UNRESOLVED_NAME


def test_unresolved_when_near_ties_span_families():
    lab = ThresholdPolicy().classify(
        _result(4, [_cand("A", "phlogopite_mica", 0.70),
                    _cand("B", "clinopyroxene_pyroxene", 0.68)]), REF)
    assert lab.level == "unresolved"
    assert "span families" in lab.rationale


def test_unresolved_when_no_candidates():
    lab = ThresholdPolicy().classify(_result(5, []), REF)
    assert lab.level == "unresolved" and lab.score is None


# -- conservative (species-only) mode ----------------------------------------

def test_conservative_species_for_strong_leader():
    pol = ThresholdPolicy(species_floor=0.85, family_floor=0.85, allow_family=False)
    lab = pol.classify(_result(0, [_cand("Rutile", "rutile_ti_oxide", 0.95)]), REF)
    assert lab.level == "species"


def test_conservative_unresolved_for_ambiguous_above_floor():
    """allow_family=False: an above-floor but ambiguous cluster abstains."""
    pol = ThresholdPolicy(species_floor=0.85, family_floor=0.85, allow_family=False)
    lab = pol.classify(_result(0, [_cand("A", "phlogopite_mica", 0.90),
                                    _cand("B", "phlogopite_mica", 0.88)]), REF)
    assert lab.level == "unresolved"


# -- PermissivePolicy (pre-S7 behaviour) -------------------------------------

def test_permissive_always_names_best_species():
    lab = PermissivePolicy().classify(
        _result(0, [_cand("Weak", "phlogopite_mica", 0.40)]), REF)
    assert lab.level == "species" and lab.name == "Weak"


def test_permissive_unresolved_only_without_candidates():
    lab = PermissivePolicy().classify(_result(0, []), REF)
    assert lab.level == "unresolved"


# -- registry + presets ------------------------------------------------------

def test_registry_resolves_policies_and_presets():
    assert isinstance(classifiers.get("threshold"), ThresholdPolicy)
    assert isinstance(classifiers.get("permissive"), PermissivePolicy)
    fam = classifiers.get("family_aware")
    assert isinstance(fam, ThresholdPolicy) and fam.species_floor == 0.80 and fam.allow_family
    cons = classifiers.get("conservative")
    assert cons.allow_family is False


def test_registry_unknown_name_raises():
    with pytest.raises(BackendNotFoundError):
        classifiers.get("no_such_policy")


def test_registry_socket_accepts_a_new_policy():
    """Extensibility: a new strategy plugs in by name (the S6-style socket)."""
    class DummyPolicy(ClassificationPolicy):
        name = "dummy"

        def classify(self, match_result, reference):
            return PermissivePolicy().classify(match_result, reference)

    classifiers.register("dummy", lambda: DummyPolicy())
    try:
        assert isinstance(classifiers.get("dummy"), DummyPolicy)
    finally:
        classifiers.unregister("dummy")


# -- provenance params + config validation -----------------------------------

def test_params_recorded():
    p = ThresholdPolicy().params()
    assert p["policy"] == "threshold" and p["species_floor"] == 0.80
    assert PermissivePolicy().params() == {"policy": "permissive"}


@pytest.mark.parametrize("kw", [
    {"species_floor": 1.5}, {"family_floor": -0.1}, {"family_margin": 2.0},
    {"species_floor": 0.4, "family_floor": 0.6},   # family_floor > species_floor
    {"allow_family": "yes"},
])
def test_config_validation_rejects_bad_settings(kw):
    with pytest.raises(PayloadValidationError):
        ThresholdPolicy(**kw)


# -- classify_clusters is ordered and pure -----------------------------------

def test_classify_clusters_preserves_order_and_evidence():
    results = [_result(0, [_cand("Rutile", "rutile_ti_oxide", 0.95)]),
               _result(1, [_cand("x", "phlogopite_mica", 0.40)])]
    labels = classify_clusters(results, REF, ThresholdPolicy())
    assert [lab.cluster_id for lab in labels] == [0, 1]
    assert [lab.level for lab in labels] == ["species", "unresolved"]
    # evidence untouched: re-labelling under another policy sees the same inputs
    labels2 = classify_clusters(results, REF, PermissivePolicy())
    assert labels2[1].level == "species"
    assert results[0].candidates[0].score == 0.95


def test_classify_clusters_rejects_non_policy():
    with pytest.raises(PayloadValidationError):
        classify_clusters([], REF, object())


# -- observation_coverage field (new in S7) ----------------------------------

def test_candidate_carries_observation_coverage():
    names = {f.name for f in dataclasses.fields(MineralCandidate)}
    assert "observation_coverage" in names


def test_io_roundtrip_preserves_observation_coverage():
    c = _cand("X", "phlogopite_mica", 0.7, obs=0.63)
    back = _validate_candidate(_cand_to_dict(c), "c")
    assert back.observation_coverage == pytest.approx(0.63)


def test_io_tolerates_legacy_doc_without_observation_coverage():
    d = _cand_to_dict(_cand("X", "phlogopite_mica", 0.7, obs=0.63))
    d.pop("observation_coverage")          # a pre-S7 (schema v1) document
    back = _validate_candidate(d, "c")
    assert back.observation_coverage == 0.0
