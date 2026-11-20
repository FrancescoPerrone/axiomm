"""Apply a classification policy across every cluster's match result."""

from __future__ import annotations

from collections.abc import Iterable

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.classify.models import ClusterLabel
from axiomm.analysis.mineralogy.classify.policy import ClassificationPolicy


def classify_clusters(match_results: Iterable, reference,
                      policy: ClassificationPolicy) -> tuple[ClusterLabel, ...]:
    """Label each cluster's ``MineralMatchResult`` under ``policy``.

    Pure over the evidence: the match results are read, never mutated, so the
    same results can be re-labelled under a different policy without re-running
    quantification or matching. Results are returned in input order.
    """
    if not hasattr(policy, "classify"):
        raise PayloadValidationError(
            f"policy must expose a classify() method; got {type(policy).__name__}.")
    return tuple(policy.classify(mr, reference) for mr in match_results)


__all__ = ["classify_clusters"]
