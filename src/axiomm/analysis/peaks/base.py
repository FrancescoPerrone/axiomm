"""The PeakMeasurer protocol.

Backends measure net intensity at given line energies; parameters live on
the instance so the protocol stays backend-agnostic (smoothing,
Beer-Lambert, interactive backends fit the same contract).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from axiomm.io.converters.models import AxisSpec
    from axiomm.analysis.peaks.models import PeakMeasurementSet


@runtime_checkable
class PeakMeasurer(Protocol):
    name: str

    def measure(
        self,
        spectrum,
        energy_axis: "AxisSpec",
        line_energies: Mapping[str, float],
    ) -> "PeakMeasurementSet": ...


__all__ = ["PeakMeasurer"]
