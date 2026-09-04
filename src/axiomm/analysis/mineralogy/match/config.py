"""Configuration for exploratory mineral matching (S3d).

All thresholds are the caller's to set; every value is validated (finite,
admissible range, integral where required) and recorded in the result
provenance so a ranking is reproducible from its record alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from axiomm.analysis.errors import PayloadValidationError

#: Missing-data modes. ``penalize`` is deferred until a formal LOD/LOQ exists.
_MISSING_MODES = frozenset({"exclude", "zero"})


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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

    ``min_score`` is a threshold on the metric's ``rank_score`` and therefore
    lives in ``[0, 1]`` (1 = best match), whatever the metric — so a cosine
    range like 2.0 is not representable. ``min_informative_dims`` (default 2)
    is the minimum number of shared scored dimensions before a candidate is
    rank-eligible, so a one-element overlap is insufficient evidence.
    """

    metric: str = "cosine"
    normalization: str = "sum_to_one"
    exclude: frozenset[str] = frozenset()
    min_score: float = 0.0
    top_k: int | None = None
    min_informative_dims: int = 2
    min_coverage: float = 0.0
    missing_data: MissingDataPolicy = field(default_factory=MissingDataPolicy)

    def __post_init__(self) -> None:
        for name in ("min_score", "min_coverage"):
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(float(v)) and 0.0 <= float(v) <= 1.0):
                raise PayloadValidationError(
                    f"MatchConfig.{name} must be a finite number in [0, 1]; got {v!r}."
                )
        if not _is_int(self.min_informative_dims) or self.min_informative_dims < 1:
            raise PayloadValidationError(
                f"MatchConfig.min_informative_dims must be an integer >= 1; "
                f"got {self.min_informative_dims!r}."
            )
        if self.top_k is not None and (not _is_int(self.top_k) or self.top_k < 1):
            raise PayloadValidationError(
                f"MatchConfig.top_k must be a positive integer or None; got {self.top_k!r}."
            )
        if not isinstance(self.missing_data, MissingDataPolicy):
            raise PayloadValidationError("MatchConfig.missing_data must be a MissingDataPolicy.")


__all__ = ["MatchConfig", "MissingDataPolicy"]
