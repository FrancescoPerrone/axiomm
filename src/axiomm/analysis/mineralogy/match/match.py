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

import math

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.match.basis import included_elements, to_molar_proportions
from axiomm.analysis.mineralogy.match.config import MatchConfig
from axiomm.analysis.mineralogy.match.metrics import get_metric
from axiomm.analysis.mineralogy.match.models import MineralCandidate, MineralMatchResult
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

_CENSORED = {"below_count_floor", "invalid"}


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
    _validate_cluster(qr)
    metric = get_metric(config.metric)
    diagnostics: list[Diagnostic] = []

    input_reliability, gated, element_status = _resolve_reliability(
        qr, reliability, allow_ungated, diagnostics)

    if config.missing_data.mode == "zero":
        diagnostics.append(Diagnostic(
            "warning", "zero_missing_data_mode",
            "missing-data policy 'zero' treats censored elements as confirmed "
            "absence — a sensitivity-analysis mode, not the default."))

    included = set(included_elements(reference, config.exclude))
    excluded = sorted(set(reference.element_order()) - included)
    provenance = _build_provenance(qr, reference, config, excluded, sorted(included),
                                   input_reliability, reference_name)

    # exploratory clusters are only ranked on an explicit opt-in
    if input_reliability == "exploratory_only":
        diagnostics.append(Diagnostic(
            "warning", "exploratory_cluster",
            "cluster is exploratory_only; " + ("ranking on explicit opt-in."
            if rank_exploratory else "not ranked (pass rank_exploratory=True to rank).")))
        if not rank_exploratory:
            return MineralMatchResult(
                cluster_id=qr.cluster_id, candidates=(), input_reliability=input_reliability,
                reliability_gated=gated, library_name=reference.name,
                library_version=reference.version, provenance=provenance,
                diagnostics=diagnostics)

    # cluster elements, split into usable (reportable) vs censored
    measured = {s: float(w) for s, w in qr.wt_percent_element.items()
                if s in included and float(w) > 0}
    censored_cluster = {s for s in measured if element_status.get(s) in _CENSORED}
    usable = {s: w for s, w in measured.items() if s not in censored_cluster}
    if censored_cluster:
        diagnostics.append(Diagnostic(
            "info", "censored_elements",
            f"below-floor elements treated as censored (not zero): {sorted(censored_cluster)}"))

    cluster_molar = to_molar_proportions(usable, "element_mass_fraction", reference,
                                         allowed=included)

    scored: list[MineralCandidate] = []
    insufficient: list[MineralCandidate] = []
    for m in reference.minerals:
        cand = _score_candidate(m, cluster_molar, censored_cluster, measured,
                                included, reference, config, metric)
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
            f"{len(insufficient)} candidate(s) had too few shared dimensions to rank."))

    return MineralMatchResult(
        cluster_id=qr.cluster_id, candidates=tuple(scored),
        insufficient=tuple(insufficient), input_reliability=input_reliability,
        reliability_gated=gated, library_name=reference.name,
        library_version=reference.version, provenance=provenance, diagnostics=diagnostics)


def _score_candidate(m, cluster_molar, censored_cluster, measured, included,
                     reference, config, metric) -> MineralCandidate | None:
    cand_molar = to_molar_proportions(m.composition, m.basis, reference, allowed=included)
    cand_included = set(cand_molar)
    if not cand_included:
        return None
    reportable = set(cluster_molar)                              # reportable measured
    shared = sorted(reportable & cand_included)                 # observed shared dims
    censored_here = sorted(cand_included & censored_cluster)
    unavailable_here = sorted(s for s in cand_included if s not in measured)
    n_info = len(shared)
    dim_cov = n_info / len(cand_included)
    comp_cov = sum(cand_molar[s] for s in shared)

    # Score over the cluster's REPORTABLE elements: a candidate that lacks a
    # reportable element is zero-filled there and thereby penalised for failing
    # to explain it. Censored elements are excluded by default (they neither
    # help nor hurt); the 'zero' policy adds them back as confirmed-absent
    # (value 0), penalising candidates that contain them. Elements the cluster
    # never measured (unavailable) are always excluded — absence can't be
    # inferred from an unmeasured line.
    score_dims = set(reportable)
    if config.missing_data.mode == "zero":
        score_dims |= set(censored_here)
    score_dims = sorted(score_dims)
    a = [cluster_molar.get(s, 0.0) for s in score_dims]
    b = [cand_molar.get(s, 0.0) for s in score_dims]
    raw = metric.raw(a, b) if score_dims else 0.0
    score = metric.rank_score(raw)

    outcome = ("insufficient_evidence"
               if (n_info < config.min_informative_dims or dim_cov < config.min_coverage)
               else "scored")
    return MineralCandidate(
        name=m.name, family=m.family, score=float(score), outcome=outcome,
        elements_used=tuple(shared), elements_censored=tuple(censored_here),
        elements_unavailable=tuple(unavailable_here), n_informative_dims=n_info,
        dimension_coverage=float(dim_cov), composition_coverage=float(comp_cov),
        basis="molar_proportions")


def _build_provenance(qr, reference, config, excluded, included, input_reliability,
                      reference_name) -> AnalysisProvenance:
    upstream = dict(qr.provenance.params) if qr.provenance is not None else {}
    return AnalysisProvenance(
        tool="mineralogy", backend="match",
        params={
            "cluster_id": qr.cluster_id,
            "library_name": reference_name or reference.name,
            "library_version": reference.version,
            "metric": config.metric,
            "normalization": config.normalization,
            "excluded_elements": excluded,
            "included_elements": included,
            "min_score": config.min_score,
            "top_k": config.top_k,
            "min_informative_dims": config.min_informative_dims,
            "min_coverage": config.min_coverage,
            "missing_data": config.missing_data.mode,
            "cluster_basis": "element_mass_fraction",
            "input_reliability": input_reliability,
            "upstream_quant": upstream,
        },
    )


def match_clusters(quant_results, reference, *, reliabilities=None,
                   config: MatchConfig | None = None, allow_ungated: bool = False,
                   rank_exploratory: bool = False) -> tuple[MineralMatchResult, ...]:
    """Match several clusters, aligning reliabilities one-to-one by ``cluster_id``.

    Results are returned in ascending ``cluster_id`` order regardless of input
    order; a missing, duplicate, or mismatched id is an error.
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
            report_by_id[int(r.cluster_id)] = r
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


__all__ = ["match_cluster", "match_clusters"]
