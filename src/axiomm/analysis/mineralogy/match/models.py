"""Result payloads for exploratory mineral matching (S3d).

Candidate rankings and scores with evidence support — never a validated
mineral identification. Composition, not inheritance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from axiomm.analysis.models import AnalysisProvenance, Diagnostic

#: A candidate's evaluation outcome.
CANDIDATE_OUTCOMES: frozenset[str] = frozenset({"scored", "insufficient_evidence"})


@dataclass(frozen=True)
class MineralCandidate:
    """One endmember scored against a cluster, with its evidence support.

    ``score`` is the metric's ``rank_score`` in ``[0, 1]`` (1 = best). Evidence
    fields distinguish what was actually observed: ``elements_used`` are the
    shared scored dimensions; ``elements_censored`` were measured but below the
    reporting floor; ``elements_unavailable`` were never measured; the two
    coverage fields report the fraction of the candidate's dimensions
    (``dimension_coverage``) and of its molar composition
    (``composition_coverage``) that the observation actually constrains.
    """

    name: str
    family: str
    score: float                     # rank_score in [0, 1] (1 = best)
    raw_score: float                 # the metric's raw value the rank derives from
    outcome: str
    elements_used: tuple[str, ...]
    elements_censored: tuple[str, ...]
    elements_unavailable: tuple[str, ...]
    n_informative_dims: int
    dimension_coverage: float
    composition_coverage: float
    basis: str


@dataclass(frozen=True)
class MineralMatchResult:
    """Ranked candidate matches for one cluster (exploratory, not an ID)."""

    cluster_id: int | None
    candidates: tuple[MineralCandidate, ...]        # rank-eligible, best-first
    input_reliability: str | None
    reliability_gated: bool
    library_name: str
    library_version: str
    insufficient: tuple[MineralCandidate, ...] = ()  # flagged, not rank-eligible
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def best(self) -> MineralCandidate | None:
        """Top scored candidate, or ``None`` when nothing qualifies."""
        return self.candidates[0] if self.candidates else None


__all__ = ["CANDIDATE_OUTCOMES", "MineralCandidate", "MineralMatchResult"]
