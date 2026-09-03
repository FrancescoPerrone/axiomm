"""Peak-identification tools (stage two, S3b).

A general spectroscopy primitive: net intensity per line energy, pluggable
behind the :class:`PeakMeasurer` protocol. Backends are *configured*, so —
like clusterers — the ``peak_measurers`` registry resolves a name to the
backend **class**; the caller constructs it with its typed config. The
flanking-window ``net_intensity`` backend is the first; smoothing,
Beer-Lambert, and interactive backends plug in behind the same contract.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

import numpy as np

from axiomm.analysis.peaks.base import PeakMeasurer
from axiomm.analysis.peaks.energy import resolve_energy_axis
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet
from axiomm.analysis.peaks.net_intensity import NetIntensityMeasurer, PeakWindowConfig
from axiomm.analysis.registry import Registry

if TYPE_CHECKING:
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    from axiomm.io.converters.models import AxisSpec

#: Registry mapping a stable name to a peak-measurer **class**.
peak_measurers: Registry = Registry("peak measurer")
peak_measurers.register("net_intensity", lambda: NetIntensityMeasurer)


def get_peak_measurer(name: str):
    """Return the peak-measurer **class** registered under ``name``."""
    return peak_measurers.get(name)


def measure_cluster_means(
    means: ClusterMeanSpectra,
    energy_axis: AxisSpec,
    line_energies: Mapping[str, float],
    *,
    measurer: PeakMeasurer,
) -> tuple[PeakMeasurementSet, ...]:
    """Measure peaks for each cluster mean, stamping the cluster id."""
    matrix = np.asarray(means.means)
    ids = np.asarray(means.cluster_ids)
    results = []
    for i in range(matrix.shape[0]):
        measured = measurer.measure(matrix[i], energy_axis, line_energies)
        measured.cluster_id = int(ids[i])
        results.append(measured)
    return tuple(results)


__all__ = [
    "NetIntensityMeasurer",
    "PeakMeasurement",
    "PeakMeasurementSet",
    "PeakMeasurer",
    "PeakWindowConfig",
    "get_peak_measurer",
    "measure_cluster_means",
    "peak_measurers",
    "resolve_energy_axis",
]
