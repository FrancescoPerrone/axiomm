"""Exploratory mineral matching (S3d).

Ranks a cluster's quantification against a basis-audited mineralogy reference
and returns candidate matches with scores and evidence support. **Candidates
and rankings only — never a validated identification.** The upstream weight
percents are an uncorrected theoretical sensitivity-ratio estimate (S3c), so
even a top-ranked ``reportable_estimate`` candidate is a screening result.
Standards validation remains mandatory before any quantitative-accuracy or
validated mineral-identification claim.
"""

from __future__ import annotations

import hashlib
import json
import math

from axiomm import __version__ as _AXIOMM_VERSION
from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.match.basis import included_elements, to_molar_proportions
from axiomm.analysis.mineralogy.match.config import NORMALIZATIONS, MatchConfig
from axiomm.analysis.mineralogy.match.metrics import evaluate, get_metric
from axiomm.analysis.mineralogy.match.models import MineralCandidate, MineralMatchResult
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.reliability import validate_reliability

MATCH_SCHEMA_VERSION = 1     # kept in sync with match.io.SCHEMA_VERSION
_CENSORED = {"below_count_floor", "invalid"}
_MEASURED = {"measured_positive", "measured_zero"}


def _require_audited(reference) -> None:
    unaudited = [m.name for m in reference.minerals if m.basis is None]
    if unaudited:
        raise PayloadValidationError(
            f"reference {reference.name!r} has basis-unaudited endmembers "
            f"(e.g. {unaudited[:3]}); the S3d matcher requires a basis-audited "
            "reference such as MINERALOGY_DEFAULT_V2. Migrate or use V2."
        )


def _validate_cluster(qr) -> None:
    for sym, wt in qr.wt_percent_element.items():
        if not (isinstance(wt, (int, float)) and not isinstance(wt, bool)
                and math.isfinite(float(wt)) and float(wt) >= 0):
            raise PayloadValidationError(
                f"cluster wt_percent_element[{sym!r}] must be finite and >= 0; got {wt!r}."
            )


def _input_digest(qr) -> str:
    payload = json.dumps(
        {s: round(float(v), 6) for s, v in sorted(qr.wt_percent_element.items())},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _resolve_reliability(qr, reliability, allow_ungated, diagnostics):
    """Return (input_reliability, reliability_gated, element_status) or raise."""
    if reliability is None:
        if not allow_ungated:
            raise PayloadValidationError(
                "a ReliabilityReport is required; pass allow_ungated=True to match "
                "an ungated cluster (recorded as such)."
            )
        diagnostics.append(Diagnostic("warning", "ungated_match",
                                      "matched without a reliability report (ungated)."))
        return "ungated", False, {}
    validate_reliability(reliability)   # strict vocabulary + contradiction checks (finding 2)
    if (reliability.cluster_id is not None and qr.cluster_id is not None
            and int(reliability.cluster_id) != int(qr.cluster_id)):
        raise PayloadValidationError(
            f"reliability cluster_id {reliability.cluster_id} != quant cluster_id "
            f"{qr.cluster_id}."
        )
    if reliability.cluster_status == "invalid":
        raise PayloadValidationError(
            "cluster reliability is 'invalid'; refusing to match an invalid cluster."
        )
    return reliability.cluster_status, True, dict(reliability.element_status)


def match_cluster(qr, reference, *, reliability=None, config: MatchConfig | None = None,
                  allow_ungated: bool = False, rank_exploratory: bool = False,
                  reference_name: str | None = None) -> MineralMatchResult:
    """Rank ``reference`` endmembers against one cluster's quantification."""
    config = config or MatchConfig()
    _require_audited(reference)
    reference.validate(strict=True)         # finding 6: strict reference-library validation
    _validate_cluster(qr)
    metric = get_metric(config.metric)
    normalize = NORMALIZATIONS[config.normalization]
    diagnostics: list[Diagnostic] = []

    input_reliability, gated, element_status = _resolve_reliability(
        qr, reliability, allow_ungated, diagnostics)

    if config.missing_data.mode == "zero":
        diagnostics.append(Diagnostic(
            "warning", "zero_missing_data_mode",
            "missing-data policy 'zero' treats censored elements as confirmed "
            "absence — a sensitivity-analysis mode, not the default."))

    # --- observation classification (finding 5): distinguish measured vs not --
    obs = dict(qr.observation_status)
    observation_known = bool(obs)
    if not observation_known:
        diagnostics.append(Diagnostic(
            "warning", "observation_status_unknown",
            "QuantResult carries no observation_status; observation treated as "
            "unknown (wt%>0 used as a fallback proxy, not an acquisition status)."))

    included = set(included_elements(reference, config.exclude))
    excluded = sorted(set(reference.element_order()) - included)
    lib_name = reference_name or reference.name
    provenance = _build_provenance(qr, reference, config, excluded, sorted(included),
                                   input_reliability, reliability, lib_name, metric)

    # exploratory clusters are only ranked on an explicit opt-in
    if input_reliability == "exploratory_only":
        diagnostics.append(Diagnostic(
            "warning", "exploratory_cluster",
            "cluster is exploratory_only; " + ("ranking on explicit opt-in."
            if rank_exploratory else "not ranked (pass rank_exploratory=True to rank).")))
        if not rank_exploratory:
            return MineralMatchResult(
                cluster_id=qr.cluster_id, candidates=(), input_reliability=input_reliability,
                reliability_gated=gated, library_name=lib_name,
                library_version=reference.version, provenance=provenance,
                diagnostics=diagnostics)

    def status_of(sym: str) -> str:
        if observation_known:
            return obs.get(sym, "not_measured")
        return "measured_positive" if float(qr.wt_percent_element.get(sym, 0.0)) > 0 else "not_measured"

    # elements the cluster actually observed (measured, positive or zero)
    measured_all = {s for s in included if status_of(s) in _MEASURED}
    # reportable = observed with positive signal, not censored by the reliability gate
    reportable = {
        s: float(qr.wt_percent_element.get(s, 0.0))
        for s in included
        if status_of(s) == "measured_positive"
        and float(qr.wt_percent_element.get(s, 0.0)) > 0
        and element_status.get(s) not in _CENSORED
    }
    censored_cluster = {s for s in measured_all if element_status.get(s) in _CENSORED}
    if censored_cluster:
        diagnostics.append(Diagnostic(
            "info", "censored_elements",
            f"below-floor elements treated as censored (not zero): {sorted(censored_cluster)}"))

    cluster_molar = normalize_map(
        to_molar_proportions(reportable, "element_mass_fraction", reference, allowed=included),
        normalize)

    scored: list[MineralCandidate] = []
    insufficient: list[MineralCandidate] = []
    for m in reference.minerals:
        cand = _score_candidate(m, cluster_molar, censored_cluster, measured_all,
                                included, reference, config, metric, normalize)
        if cand is None:
            continue
        if cand.outcome == "insufficient_evidence":
            insufficient.append(cand)
        elif cand.score >= config.min_score:
            scored.append(cand)

    # rank by score, breaking ties toward the better-covered candidate
    scored.sort(key=lambda c: (c.score, c.composition_coverage), reverse=True)
    if config.top_k is not None:
        scored = scored[:config.top_k]
    if insufficient:
        diagnostics.append(Diagnostic(
            "info", "insufficient_evidence",
            f"{len(insufficient)} candidate(s) not rank-eligible (too few informative "
            "dimensions or below the composition-coverage support threshold)."))
    # finding 11: a one-element would-be match is a specific, named limitation
    single = sorted({c.name for c in insufficient if c.n_informative_dims <= 1
                     and c.score >= 0.9})
    if single:
        diagnostics.append(Diagnostic(
            "warning", "single_dimension_evidence",
            f"candidate(s) {single} match on a single informative element; one-element "
            "identification is not supported by ratio matching (a validated "
            "presence-plus-absence model is required)."))

    return MineralMatchResult(
        cluster_id=qr.cluster_id, candidates=tuple(scored),
        insufficient=tuple(insufficient), input_reliability=input_reliability,
        reliability_gated=gated, library_name=lib_name,
        library_version=reference.version, provenance=provenance, diagnostics=diagnostics)


def normalize_map(mapping: dict[str, float], normalize) -> dict[str, float]:
    """Apply the configured normalization to a molar map, preserving keys."""
    if not mapping:
        return {}
    keys = list(mapping)
    values = normalize([mapping[k] for k in keys])
    return dict(zip(keys, values, strict=True))


def _score_candidate(m, cluster_molar, censored_cluster, measured_all, included,
                     reference, config, metric, normalize) -> MineralCandidate | None:
    cand_molar = normalize_map(
        to_molar_proportions(m.composition, m.basis, reference, allowed=included), normalize)
    cand_included = set(cand_molar)
    if not cand_included:
        return None
    reportable = set(cluster_molar)                              # reportable measured
    shared = sorted(reportable & cand_included)                 # observed shared dims
    censored_here = sorted(cand_included & censored_cluster)
    unavailable_here = sorted(s for s in cand_included if s not in measured_all)
    n_info = len(shared)
    dim_cov = n_info / len(cand_included)
    comp_cov = sum(cand_molar[s] for s in shared)

    # Score over the cluster's REPORTABLE elements: a candidate that lacks a
    # reportable element is zero-filled there and thereby penalised for failing
    # to explain it. Censored elements are excluded by default; 'zero' adds them
    # back as confirmed-absent. Never-measured elements are always excluded.
    score_dims = set(reportable)
    if config.missing_data.mode == "zero":
        score_dims |= set(censored_here)
    score_dims = sorted(score_dims)
    if score_dims:
        a = [cluster_molar.get(s, 0.0) for s in score_dims]
        b = [cand_molar.get(s, 0.0) for s in score_dims]
        raw, score = evaluate(metric, a, b)
    else:
        raw, score = 0.0, 0.0

    # finding 1: support-aware eligibility — enough shared dimensions AND enough
    # of the candidate's own composition explained, else not rank-eligible.
    outcome = "scored"
    if (n_info < config.min_informative_dims
            or dim_cov < config.min_coverage
            or comp_cov < config.min_composition_coverage):
        outcome = "insufficient_evidence"
    return MineralCandidate(
        name=m.name, family=m.family, score=float(score), raw_score=float(raw),
        outcome=outcome, elements_used=tuple(shared), elements_censored=tuple(censored_here),
        elements_unavailable=tuple(unavailable_here), n_informative_dims=n_info,
        dimension_coverage=float(dim_cov), composition_coverage=float(comp_cov),
        basis="molar_proportions")


def _build_provenance(qr, reference, config, excluded, included, input_reliability,
                      reliability, lib_name, metric) -> AnalysisProvenance:
    upstream = dict(qr.provenance.params) if qr.provenance is not None else {}
    rel_thresholds = None
    if reliability is not None and reliability.provenance is not None:
        rp = reliability.provenance.params
        rel_thresholds = {k: rp.get(k) for k in
                          ("min_pixel_count", "max_heterogeneity", "min_total_counts",
                           "count_floor", "element_count_floors") if k in rp}
    upstream_diag = [d.code for d in qr.diagnostics]
    if reliability is not None:
        upstream_diag += [d.code for d in reliability.diagnostics]
    return AnalysisProvenance(
        tool="mineralogy", backend="match",
        params={
            "schema_version": MATCH_SCHEMA_VERSION,
            "software_version": _AXIOMM_VERSION,
            "cluster_id": qr.cluster_id,
            "input_measurement_digest": _input_digest(qr),
            "library_name": lib_name,
            "library_version": reference.version,
            "reference_bases": sorted({m.basis for m in reference.minerals if m.basis}),
            "reference_audit": "MINERALOGY_V2_BASIS_AUDIT" if lib_name.startswith("minerals_default")
            else "external",
            "metric": metric.name,
            "metric_version": metric.version,
            "normalization": config.normalization,
            "normalization_applied": config.normalization,   # validated == requested
            "excluded_elements": excluded,
            "included_elements": included,
            "min_score": config.min_score,
            "top_k": config.top_k,
            "min_informative_dims": config.min_informative_dims,
            "min_coverage": config.min_coverage,
            "min_composition_coverage": config.min_composition_coverage,
            "missing_data": config.missing_data.mode,
            "cluster_basis": "element_mass_fraction",
            "input_reliability": input_reliability,
            "reliability_thresholds": rel_thresholds,
            "quant_method": upstream.get("kfactor_method"),
            "calibration_backend": upstream.get("xraylib_backend"),
            "cross_section_version": upstream.get("xraylib_version"),
            "quant_reference_name": upstream.get("reference_name"),
            "upstream_diagnostics": upstream_diag,
            "upstream_quant": upstream,
        },
    )


def match_clusters(quant_results, reference, *, reliabilities=None,
                   config: MatchConfig | None = None, allow_ungated: bool = False,
                   rank_exploratory: bool = False) -> tuple[MineralMatchResult, ...]:
    """Match several clusters, aligning reliabilities one-to-one by ``cluster_id``.

    Results are returned in ascending ``cluster_id`` order regardless of input
    order; a missing, duplicate, or mismatched id is an error, and duplicate
    identifiers are never silently overwritten.
    """
    config = config or MatchConfig()
    by_id: dict[int, object] = {}
    for qr in quant_results:
        if qr.cluster_id is None:
            raise PayloadValidationError("every quant result must carry a cluster_id.")
        cid = int(qr.cluster_id)
        if cid in by_id:
            raise PayloadValidationError(f"duplicate cluster_id {cid} in quant_results.")
        by_id[cid] = qr

    report_by_id: dict[int, object] = {}
    if reliabilities is not None:
        for r in reliabilities:
            if r.cluster_id is None:
                raise PayloadValidationError("every reliability report must carry a cluster_id.")
            rid = int(r.cluster_id)
            if rid in report_by_id:
                raise PayloadValidationError(f"duplicate cluster_id {rid} in reliabilities.")
            report_by_id[rid] = r
        if set(report_by_id) != set(by_id):
            raise PayloadValidationError(
                "reliabilities must correspond one-to-one to quant_results by cluster_id."
            )

    results = []
    for cid in sorted(by_id):
        results.append(match_cluster(
            by_id[cid], reference, reliability=report_by_id.get(cid), config=config,
            allow_ungated=allow_ungated, rank_exploratory=rank_exploratory))
    return tuple(results)


__all__ = ["MATCH_SCHEMA_VERSION", "match_cluster", "match_clusters"]
