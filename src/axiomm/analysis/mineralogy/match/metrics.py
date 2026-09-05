"""Similarity/distance metric contract + registry (S3d).

Every metric declares its identity (name + version), direction and scale, and
provides a monotonic ``rank_score`` in ``[0, 1]`` (1 = best match), so ranking
and thresholding are metric-agnostic: ranking is always by ``rank_score``
descending, and the config ``min_score`` is always a ``[0, 1]`` threshold.

The registry is guarded: a name cannot be overwritten unless ``replace=True``,
non-callable score functions and malformed bounds are rejected, and every
computed score is validated (raw finite and within the metric's documented
domain, rank in ``[0, 1]``) by :func:`evaluate`, which also returns the raw
value so it can be persisted alongside the rank.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from axiomm.analysis.errors import PayloadValidationError


@dataclass(frozen=True)
class Metric:
    """A named, versioned similarity/distance with an explicit direction."""

    name: str
    version: str
    kind: str                       # "similarity" | "distance"
    raw_bounds: tuple[float, float]
    raw: Callable[[Sequence[float], Sequence[float]], float]
    rank_score: Callable[[float], float]   # -> [0, 1], 1 = best


def _cosine_raw(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return num / (na * nb)


#: On non-negative molar-proportion vectors cosine similarity lies in [0, 1].
_COSINE = Metric(
    name="cosine", version="1", kind="similarity", raw_bounds=(0.0, 1.0),
    raw=_cosine_raw, rank_score=lambda r: max(0.0, min(1.0, r)),
)

_METRICS: dict[str, Metric] = {"cosine": _COSINE}


def get_metric(name: str) -> Metric:
    """Return the registered metric, or raise for an unknown name."""
    try:
        return _METRICS[name]
    except KeyError:
        raise PayloadValidationError(
            f"unknown metric {name!r}; registered: {sorted(_METRICS)}."
        ) from None


def register_metric(metric: Metric, *, replace: bool = False) -> None:
    """Register a metric, refusing to silently overwrite an existing name.

    Rejects non-callable score functions, malformed bounds, and an unknown
    ``kind``; overwriting an existing name requires ``replace=True``.
    """
    if not isinstance(metric, Metric):
        raise PayloadValidationError("register_metric expects a Metric instance.")
    if not (callable(metric.raw) and callable(metric.rank_score)):
        raise PayloadValidationError(f"metric {metric.name!r} raw/rank_score must be callable.")
    if metric.kind not in ("similarity", "distance"):
        raise PayloadValidationError(
            f"metric {metric.name!r} has unknown kind {metric.kind!r}."
        )
    lo, hi = metric.raw_bounds
    if not (math.isfinite(lo) and math.isfinite(hi) and lo <= hi):
        raise PayloadValidationError(
            f"metric {metric.name!r} has malformed raw_bounds {metric.raw_bounds!r}."
        )
    if metric.name in _METRICS and not replace:
        raise PayloadValidationError(
            f"metric {metric.name!r} already registered; pass replace=True to override."
        )
    _METRICS[metric.name] = metric


def evaluate(metric: Metric, a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    """Compute ``(raw, rank)`` for ``metric``, validating both against its domain."""
    raw = float(metric.raw(a, b))
    lo, hi = metric.raw_bounds
    if not math.isfinite(raw) or raw < lo - 1e-9 or raw > hi + 1e-9:
        raise PayloadValidationError(
            f"metric {metric.name!r} produced raw score {raw!r} outside bounds {metric.raw_bounds}."
        )
    rank = float(metric.rank_score(raw))
    if not math.isfinite(rank) or rank < -1e-9 or rank > 1 + 1e-9:
        raise PayloadValidationError(
            f"metric {metric.name!r} produced rank score {rank!r} outside [0, 1]."
        )
    return raw, max(0.0, min(1.0, rank))


__all__ = ["Metric", "evaluate", "get_metric", "register_metric"]
