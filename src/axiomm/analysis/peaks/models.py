"""Peak-measurement result payloads (composition, not inheritance)."""

from __future__ import annotations

from dataclasses import dataclass, field

from axiomm.analysis.models import AnalysisProvenance, Diagnostic


@dataclass(frozen=True)
class PeakMeasurement:
    """Net intensity of one line, plus the facts behind it."""

    label: str
    center_kev: float
    net: float
    gross: float
    background: float   # per-channel background under the peak
    n_channels: int     # channels in the peak window
    in_range: bool      # was the line inside the axis span


@dataclass
class PeakMeasurementSet:
    """All line measurements for one spectrum."""

    measurements: tuple[PeakMeasurement, ...]
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    cluster_id: int | None = None   # identity when this set is one cluster's mean

    def net_by_label(self) -> dict[str, float]:
        """Convenience map ``label -> net`` (used by S3c)."""
        return {m.label: m.net for m in self.measurements}


__all__ = ["PeakMeasurement", "PeakMeasurementSet"]
