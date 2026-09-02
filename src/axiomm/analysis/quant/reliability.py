"""Quantification reliability gate.

A GMM cluster mean is a statistical average over possibly mixed pixels, so
it is not automatically a valid quantitative phase spectrum. This tool
flags per-element results below a reliable count and per-cluster
summaries that are exploratory-only. It is an overlay: the raw
``QuantResult`` is never modified, and no physical cause is asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Mapping

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

ElementStatus = Literal["valid", "below_quantification_limit"]
ClusterStatus = Literal["quantitative", "exploratory_only"]


@dataclass(frozen=True)
class ReliabilityConfig:
    """Reliability thresholds (documented example defaults; caller-set)."""

    min_pixel_count: int = 20
    max_heterogeneity: float = 0.15
    min_total_counts: float = 1.0e4
    min_net_counts: float = 50.0


@dataclass
class ReliabilityReport:
    """Per-cluster reliability verdict, overlaying a QuantResult."""

    cluster_status: str
    element_status: Mapping[str, str]
    reasons: tuple[str, ...]
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


def assess_reliability(quant, *, pixel_count, heterogeneity, total_counts,
                       config: ReliabilityConfig = ReliabilityConfig()) -> ReliabilityReport:
    """Assess one cluster's quantification against the reliability thresholds."""
    element_status = {
        sym: ("below_quantification_limit" if net < config.min_net_counts else "valid")
        for sym, net in quant.net_intensities.items()
    }

    reasons: list[str] = []
    if pixel_count < config.min_pixel_count:
        reasons.append(f"pixel_count {pixel_count} < {config.min_pixel_count}")
    if heterogeneity is None or (isinstance(heterogeneity, float) and math.isnan(heterogeneity)):
        reasons.append("heterogeneity undefined (empty cluster)")
    elif heterogeneity > config.max_heterogeneity:
        reasons.append(f"heterogeneity {heterogeneity:.3f} > {config.max_heterogeneity}")
    if total_counts < config.min_total_counts:
        reasons.append(f"total_counts {total_counts:.0f} < {config.min_total_counts:.0f}")
    cluster_status = "exploratory_only" if reasons else "quantitative"

    diagnostics: list[Diagnostic] = []
    flagged = [s for s, v in element_status.items() if v == "below_quantification_limit"]
    if flagged:
        diagnostics.append(
            Diagnostic("warning", "below_quantification_limit",
                       f"elements below the quantification limit: {flagged}")
        )
    if cluster_status == "exploratory_only":
        diagnostics.append(
            Diagnostic("warning", "exploratory_cluster",
                       "cluster mean not accepted as quantitative: " + "; ".join(reasons))
        )

    provenance = AnalysisProvenance(
        tool="quant", backend="reliability",
        params={
            "min_pixel_count": config.min_pixel_count,
            "max_heterogeneity": config.max_heterogeneity,
            "min_total_counts": config.min_total_counts,
            "min_net_counts": config.min_net_counts,
        },
    )
    return ReliabilityReport(
        cluster_status=cluster_status, element_status=element_status,
        reasons=tuple(reasons), provenance=provenance, diagnostics=diagnostics,
    )


def assess_cluster_reliability(quant_results, cluster_means,
                               config: ReliabilityConfig = ReliabilityConfig()) -> tuple[ReliabilityReport, ...]:
    """Assess each cluster's quantification against its cluster-quality."""
    if cluster_means.heterogeneity is None or cluster_means.total_counts is None:
        raise PayloadValidationError(
            "cluster_means is not enriched with heterogeneity/total_counts; "
            "recompute with compute_cluster_means."
        )
    n = len(quant_results)
    if not (len(cluster_means.pixel_counts) == n
            and len(cluster_means.heterogeneity) == n
            and len(cluster_means.total_counts) == n):
        raise PayloadValidationError(
            "quant_results length does not match cluster_means arrays."
        )
    return tuple(
        assess_reliability(
            quant_results[i],
            pixel_count=int(cluster_means.pixel_counts[i]),
            heterogeneity=float(cluster_means.heterogeneity[i]),
            total_counts=float(cluster_means.total_counts[i]),
            config=config,
        )
        for i in range(n)
    )


__all__ = ["ClusterStatus", "ElementStatus", "ReliabilityConfig",
           "ReliabilityReport", "assess_cluster_reliability", "assess_reliability"]
