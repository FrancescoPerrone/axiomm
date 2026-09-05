"""Configuration for exploratory mineral matching (S3d).

All thresholds are the caller's to set; every value is validated (finite,
admissible range, integral where required, known vocabulary) and recorded in
the result provenance so a ranking is reproducible from its record alone.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from axiomm.analysis.errors import PayloadValidationError

#: Missing-data modes. ``penalize`` is deferred until a formal LOD/LOQ exists.
_MISSING_MODES = frozenset({"exclude", "zero"})


def _normalize_sum_to_one(vec: Sequence[float]) -> list[float]:
    total = float(sum(vec))
    return [float(v) / total for v in vec] if total > 0 else [0.0 for _ in vec]


#: Registry of *supported* vector normalizations, applied before scoring. Only
#: methods present here are accepted by :class:`MatchConfig`; the applied method
#: (not merely the requested string) is recorded in result provenance. Cosine is
#: scale-invariant, so ``sum_to_one`` is the canonical molar/element basis.
NORMALIZATIONS: dict[str, object] = {"sum_to_one": _normalize_sum_to_one}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _unit(value: object, name: str) -> None:
    if not (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and 0.0 <= float(value) <= 1.0):
        raise PayloadValidationError(f"MatchConfig.{name} must be a finite number in [0, 1]; got {value!r}.")


@dataclass(frozen=True)
class MissingDataPolicy:
    """How censored / unavailable elements are treated before scoring.

    * ``exclude`` (default) — drop them from both vectors: they neither
      confirm nor refute a candidate.
    * ``zero`` — treat them as 0. A naive sensitivity mode only, always
      emitted with an explicit warning.
    * ``penalize`` — **deferred** (needs a real LOD/LOQ); rejected here.
    """

    mode: str = "exclude"

    def __post_init__(self) -> None:
        if self.mode == "penalize":
            raise PayloadValidationError(
                "MissingDataPolicy 'penalize' is deferred until a formal LOD/LOQ "
                "exists; use 'exclude' (default) or 'zero'."
            )
        if self.mode not in _MISSING_MODES:
            raise PayloadValidationError(
                f"MissingDataPolicy.mode must be one of {sorted(_MISSING_MODES)} "
                f"(or the deferred 'penalize'); got {self.mode!r}."
            )


@dataclass(frozen=True)
class MatchConfig:
    """Similarity metric, normalization, exclusions and ranking thresholds.

    ``min_score`` thresholds the metric's ``rank_score`` and so lives in
    ``[0, 1]``. ``min_informative_dims`` (default 2) is the minimum number of
    shared scored dimensions, so a one-element overlap is insufficient evidence.
    ``min_composition_coverage`` (default 0.5) is a **support-aware eligibility
    gate**: a candidate whose measured elements represent less than this
    fraction of its own composition is not rank-eligible, however high its
    numerical similarity — a candidate must be at least half-explained by the
    observation to be a credible identification.
    """

    metric: str = "cosine"
    normalization: str = "sum_to_one"
    exclude: frozenset[str] = frozenset()
    min_score: float = 0.0
    top_k: int | None = None
    min_informative_dims: int = 2
    min_coverage: float = 0.0                 # dimension-coverage floor
    min_composition_coverage: float = 0.5     # composition-coverage eligibility gate
    missing_data: MissingDataPolicy = field(default_factory=MissingDataPolicy)

    def __post_init__(self) -> None:
        for name in ("min_score", "min_coverage", "min_composition_coverage"):
            _unit(getattr(self, name), name)
        if not _is_int(self.min_informative_dims) or self.min_informative_dims < 1:
            raise PayloadValidationError(
                f"MatchConfig.min_informative_dims must be an integer >= 1; "
                f"got {self.min_informative_dims!r}."
            )
        if self.top_k is not None and (not _is_int(self.top_k) or self.top_k < 1):
            raise PayloadValidationError(
                f"MatchConfig.top_k must be a positive integer or None; got {self.top_k!r}."
            )
        if self.normalization not in NORMALIZATIONS:
            raise PayloadValidationError(
                f"MatchConfig.normalization {self.normalization!r} is not supported; "
                f"registered: {sorted(NORMALIZATIONS)}."
            )
        if not isinstance(self.missing_data, MissingDataPolicy):
            raise PayloadValidationError("MatchConfig.missing_data must be a MissingDataPolicy.")


__all__ = ["NORMALIZATIONS", "MatchConfig", "MissingDataPolicy"]
