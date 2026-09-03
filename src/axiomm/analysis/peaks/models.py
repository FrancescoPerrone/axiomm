"""Peak-measurement result payloads (composition, not inheritance)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic


def _is_int(value: object) -> bool:
    """True for a real integer, rejecting bool (``True`` is not a count)."""
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class PeakMeasurement:
    """Net intensity of one line, plus the facts behind it.

    The retained facts (``gross``, ``background``, ``n_channels``) are the
    inputs a future statistical LOD/LOQ will consume, so their integrity is
    checked here rather than assumed: ``gross`` and ``background`` must be
    finite and non-negative, ``n_channels`` a non-negative integer,
    ``center_kev`` finite, and ``net`` finite (``net`` may be negative when
    background is over-subtracted).
    """

    label: str
    center_kev: float
    net: float
    gross: float
    background: float   # per-channel background under the peak
    n_channels: int     # channels in the peak window
    in_range: bool      # was the line inside the axis span

    def __post_init__(self) -> None:
        if not self.label:
            raise PayloadValidationError("PeakMeasurement.label must be non-empty.")
        for name in ("center_kev", "net", "gross", "background"):
            v = getattr(self, name)
            if not (isinstance(v, (int, float)) and math.isfinite(float(v))):
                raise PayloadValidationError(
                    f"PeakMeasurement.{name} must be finite; got {v!r} for {self.label!r}."
                )
        if self.gross < 0:
            raise PayloadValidationError(
                f"PeakMeasurement.gross must be >= 0; got {self.gross!r} for {self.label!r}."
            )
        if self.background < 0:
            raise PayloadValidationError(
                f"PeakMeasurement.background must be >= 0; got {self.background!r} for {self.label!r}."
            )
        if not _is_int(self.n_channels) or self.n_channels < 0:
            raise PayloadValidationError(
                f"PeakMeasurement.n_channels must be a non-negative integer; "
                f"got {self.n_channels!r} for {self.label!r}."
            )


@dataclass
class PeakMeasurementSet:
    """All line measurements for one spectrum."""

    measurements: tuple[PeakMeasurement, ...]
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    cluster_id: int | None = None   # identity when this set is one cluster's mean

    def __post_init__(self) -> None:
        labels = [m.label for m in self.measurements]
        dupes = sorted({lab for lab in labels if labels.count(lab) > 1})
        if dupes:
            raise PayloadValidationError(
                f"duplicate PeakMeasurement labels are not allowed: {dupes}."
            )
        if self.cluster_id is not None and not _is_int(self.cluster_id):
            raise PayloadValidationError(
                f"PeakMeasurementSet.cluster_id must be an integer or None; got {self.cluster_id!r}."
            )

    def net_by_label(self) -> dict[str, float]:
        """Convenience map ``label -> net`` (used by S3c)."""
        return {m.label: m.net for m in self.measurements}


__all__ = ["PeakMeasurement", "PeakMeasurementSet"]
