"""Result model for S7 phase classification.

A :class:`ClusterLabel` is the *decision* a :class:`ClassificationPolicy`
reaches for one cluster, derived from the S3d matching *evidence*. It records
the decision level (a specific species, a mineral family, or ``unresolved``),
the chosen name, and a plain-language rationale — never a calibrated
probability. The similarity score is carried as context only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: The confidence level of a label: a specific mineral species, a broader
#: mineral family (when species discrimination is unsupported), or unresolved.
LabelLevel = Literal["species", "family", "unresolved"]

#: Phase-map value for an unresolved cluster. Matches
#: :data:`axiomm.pipeline.result.UNRESOLVED` so the map value is unchanged.
UNRESOLVED_NAME = "unresolved"


@dataclass(frozen=True)
class ClusterLabel:
    """The classification decision for one cluster (not a validated ID).

    Attributes
    ----------
    cluster_id
        The cluster this label is for (``None`` only for an unkeyed input).
    level
        ``"species"``, ``"family"``, or ``"unresolved"``.
    name
        The species name, the family display name, or ``"unresolved"``.
    family
        The mineral family, when known (set for species and family levels).
    score
        The top candidate's similarity score — context, never a probability.
    rationale
        Plain-language reason the policy reached this level.
    contenders
        Candidate names within the policy's ambiguity margin of the top.
    policy
        Name of the policy that produced this label (for provenance).
    """

    cluster_id: int | None
    level: LabelLevel
    name: str
    family: str | None
    score: float | None
    rationale: str
    contenders: tuple[str, ...]
    policy: str


__all__ = ["UNRESOLVED_NAME", "ClusterLabel", "LabelLevel"]
