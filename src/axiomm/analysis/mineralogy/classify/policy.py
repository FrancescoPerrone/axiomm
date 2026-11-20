"""Classification policies — the general decision layer over matching evidence.

A :class:`ClassificationPolicy` turns one cluster's ranked candidate matches
(S3d evidence) into a :class:`ClusterLabel` (species / family / unresolved).
The policy never touches the evidence — same matches in, a label out — so a
user can compare policies on the *same* run without re-quantifying.

Two policies ship:

* :class:`ThresholdPolicy` (the general rule) — name a species when there is a
  clear leader above a score floor; fall back to the mineral *family* when the
  near-ties agree on family (or a clear leader sits below the species floor);
  abstain (``unresolved``) when the best match is too weak or the near-ties
  span families.
* :class:`PermissivePolicy` — always name the top candidate's species (today's
  behaviour), reachable by name so the S7 default change is reversible.

Scores are cosine similarities, **not** probabilities; thresholds are
similarity cutoffs and every label carries a text rationale, never a percent.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.classify.models import UNRESOLVED_NAME, ClusterLabel


def _unit(value: object, name: str) -> None:
    if not (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0):
        raise PayloadValidationError(f"{name} must be a finite number in [0, 1]; got {value!r}.")


def _family_display(reference, family: str) -> str:
    """Human-readable family name from the reference, or the raw family string."""
    disp = getattr(reference, "family_display", None)
    if disp is not None and hasattr(disp, "get"):
        return disp.get(family, family)
    return family


class ClassificationPolicy(ABC):
    """Maps one cluster's :class:`MineralMatchResult` to a :class:`ClusterLabel`."""

    name: ClassVar[str] = "policy"

    @abstractmethod
    def classify(self, match_result, reference) -> ClusterLabel:
        """Return the label this policy assigns to ``match_result``."""

    def params(self) -> dict:
        """Policy settings for the result provenance."""
        return {"policy": self.name}


@dataclass(frozen=True)
class PermissivePolicy(ClassificationPolicy):
    """Always name the top candidate's species (the pre-S7 behaviour).

    Abstains only when matching returned no rank-eligible candidate at all.
    """

    name: ClassVar[str] = "permissive"

    def classify(self, match_result, reference) -> ClusterLabel:
        cid = match_result.cluster_id
        best = match_result.best()
        if best is None:
            return ClusterLabel(cid, "unresolved", UNRESOLVED_NAME, None, None,
                                "no rank-eligible candidate", (), self.name)
        return ClusterLabel(cid, "species", best.name, best.family, float(best.score),
                            "top-ranked candidate (permissive: always name the best)",
                            (best.name,), self.name)


@dataclass(frozen=True)
class ThresholdPolicy(ClassificationPolicy):
    """Species / family / unresolved by score, ambiguity margin and family.

    Parameters
    ----------
    species_floor
        Minimum top score to name a specific species (needs a clear leader).
    family_floor
        Minimum top score to emit any label; below it the cluster is unresolved.
        Must be ``<= species_floor``.
    family_margin
        Candidates within this score of the top are "near-ties" (contenders).
    allow_family
        When ``False``, only species-or-unresolved (a conservative mode).
    """

    species_floor: float = 0.80
    family_floor: float = 0.50
    family_margin: float = 0.05
    allow_family: bool = True

    name: ClassVar[str] = "threshold"

    def __post_init__(self) -> None:
        for n in ("species_floor", "family_floor", "family_margin"):
            _unit(getattr(self, n), f"ThresholdPolicy.{n}")
        if not isinstance(self.allow_family, bool):
            raise PayloadValidationError(
                f"ThresholdPolicy.allow_family must be a bool; got {self.allow_family!r}.")
        if self.family_floor > self.species_floor:
            raise PayloadValidationError(
                f"ThresholdPolicy.family_floor ({self.family_floor}) must be "
                f"<= species_floor ({self.species_floor}).")

    def params(self) -> dict:
        return {"policy": self.name, "species_floor": self.species_floor,
                "family_floor": self.family_floor, "family_margin": self.family_margin,
                "allow_family": self.allow_family}

    def classify(self, match_result, reference) -> ClusterLabel:
        cid = match_result.cluster_id
        cands = match_result.candidates  # rank-eligible, best-first
        if not cands:
            return ClusterLabel(cid, "unresolved", UNRESOLVED_NAME, None, None,
                                "insufficient evidence: no rank-eligible candidate",
                                (), self.name)
        top = cands[0]
        if top.score < self.family_floor:
            return ClusterLabel(
                cid, "unresolved", UNRESOLVED_NAME, None, float(top.score),
                f"best match {top.name} score {top.score:.3f} below family floor "
                f"{self.family_floor:.2f}", (top.name,), self.name)

        near = [c for c in cands if top.score - c.score <= self.family_margin]
        contenders = tuple(c.name for c in near)

        # a clear leader above the species floor -> name the species
        if len(near) == 1 and top.score >= self.species_floor:
            return ClusterLabel(
                cid, "species", top.name, top.family, float(top.score),
                f"clear leader {top.name} (score {top.score:.3f} >= species floor "
                f"{self.species_floor:.2f})", contenders, self.name)

        # otherwise: ambiguous, or a clear leader below the species floor
        if self.allow_family:
            families = {c.family for c in near}
            if len(families) == 1:
                fam = next(iter(families))
                if len(near) == 1:
                    why = (f"clear leader {top.name} but score {top.score:.3f} below "
                           f"species floor {self.species_floor:.2f}; resolved to family")
                else:
                    why = (f"top {len(near)} within {self.family_margin:.2f} "
                           f"({', '.join(contenders)}), all {fam}")
                return ClusterLabel(cid, "family", _family_display(reference, fam), fam,
                                    float(top.score), why, contenders, self.name)
            return ClusterLabel(
                cid, "unresolved", UNRESOLVED_NAME, None, float(top.score),
                f"near-ties span families ({', '.join(sorted(families))}); cannot resolve",
                contenders, self.name)

        # family labels disabled and no clear species leader
        return ClusterLabel(
            cid, "unresolved", UNRESOLVED_NAME, None, float(top.score),
            f"no clear species above floor {self.species_floor:.2f}; family labels disabled",
            contenders, self.name)


__all__ = ["ClassificationPolicy", "PermissivePolicy", "ThresholdPolicy"]
