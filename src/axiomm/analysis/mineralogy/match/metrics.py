"""Similarity/distance metric contract + registry (S3d).

Every metric declares its direction and scale and provides a monotonic
``rank_score`` in ``[0, 1]`` (1 = best match), so ranking and thresholding are
metric-agnostic: ranking is always by ``rank_score`` descending, and the
config ``min_score`` is always a ``[0, 1]`` threshold. This resolves the
cosine-vs-``min_score`` scale mismatch (no raw cosine range leaks into a
threshold).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from axiomm.analysis.errors import PayloadValidationError


@dataclass(frozen=True)
class Metric:
    """A named similarity/distance with an explicit direction and rank map."""

    name: str
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
    name="cosine", kind="similarity", raw_bounds=(0.0, 1.0),
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


def register_metric(metric: Metric) -> None:
    """Register a metric so it can be selected by name (used by extensions)."""
    _METRICS[metric.name] = metric


__all__ = ["Metric", "get_metric", "register_metric"]
