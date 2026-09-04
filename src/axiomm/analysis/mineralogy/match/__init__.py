"""Exploratory mineral matching (stage two, S3d).

Ranks a quantified cluster against a basis-audited mineralogy reference and
returns candidate matches with scores and evidence support — **candidate
rankings only, never a validated mineral identification.** The upstream weight
percents are an uncorrected theoretical sensitivity-ratio estimate (S3c);
**standards validation remains mandatory** before any quantitative-accuracy or
validated mineral-identification claim.
"""

from __future__ import annotations

from axiomm.analysis.mineralogy.match.config import MatchConfig, MissingDataPolicy
from axiomm.analysis.mineralogy.match.io import read_match, write_match
from axiomm.analysis.mineralogy.match.match import match_cluster, match_clusters
from axiomm.analysis.mineralogy.match.metrics import Metric, get_metric, register_metric
from axiomm.analysis.mineralogy.match.models import (
    CANDIDATE_OUTCOMES,
    MineralCandidate,
    MineralMatchResult,
)

__all__ = [
    "CANDIDATE_OUTCOMES",
    "MatchConfig",
    "Metric",
    "MineralCandidate",
    "MineralMatchResult",
    "MissingDataPolicy",
    "get_metric",
    "match_cluster",
    "match_clusters",
    "read_match",
    "register_metric",
    "write_match",
]
