"""Net-intensity peak backend: flanking-window linear background subtraction.

The first PeakMeasurer backend, ported from the corrected
``cliff_lorimer.py``. Window sizes are exposed config with documented
example defaults — never baked (parameter autonomy).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.peaks.energy import resolve_energy_axis
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet


@dataclass(frozen=True)
class PeakWindowConfig:
    """Background/peak window widths in keV (example defaults, adjustable)."""

    half_width_kev: float = 0.06
    bg_gap_kev: float = 0.04
    bg_width_kev: float = 0.10


class NetIntensityMeasurer:
    """Background-subtracted net peak areas at given line energies."""

    name = "net_intensity"

    def __init__(self, config: PeakWindowConfig | None = None) -> None:
        self.config = config or PeakWindowConfig()

    def measure(self, spectrum, energy_axis, line_energies) -> PeakMeasurementSet:
        spec = np.asarray(spectrum, dtype=float)
        if spec.ndim != 1:
            raise PayloadValidationError(
                f"spectrum must be 1-D; got shape {spec.shape}."
            )
        if not np.all(np.isfinite(spec)):
            raise PayloadValidationError("spectrum contains non-finite values.")

        energy = resolve_energy_axis(energy_axis, spec.size)
        cfg = self.config
        e_lo, e_hi = float(energy[0]), float(energy[-1])
        measurements: list[PeakMeasurement] = []
        diagnostics: list[Diagnostic] = []

        for label, raw_center in line_energies.items():
            center = float(raw_center)
            if center < e_lo or center > e_hi:
                diagnostics.append(
                    Diagnostic(
                        "info",
                        "line_out_of_range",
                        f"line {label!r} at {center} keV is outside the axis "
                        f"span [{e_lo:.3f}, {e_hi:.3f}].",
                    )
                )
                measurements.append(
                    PeakMeasurement(label, center, 0.0, 0.0, 0.0, 0, False)
                )
                continue

            lo, hi = center - cfg.half_width_kev, center + cfg.half_width_kev
            peak_mask = (energy >= lo) & (energy <= hi)
            n_peak = int(peak_mask.sum())
            if n_peak == 0:
                measurements.append(
                    PeakMeasurement(label, center, 0.0, 0.0, 0.0, 0, True)
                )
                continue

            left = (energy >= lo - cfg.bg_gap_kev - cfg.bg_width_kev) & (
                energy < lo - cfg.bg_gap_kev
            )
            right = (energy > hi + cfg.bg_gap_kev) & (
                energy <= hi + cfg.bg_gap_kev + cfg.bg_width_kev
            )
            flanks = []
            if left.any():
                flanks.append(float(np.median(spec[left])))
            if right.any():
                flanks.append(float(np.median(spec[right])))
            bg_per_ch = float(np.mean(flanks)) if flanks else 0.0
            gross = float(np.sum(spec[peak_mask]))
            net = max(gross - bg_per_ch * n_peak, 0.0)
            measurements.append(
                PeakMeasurement(label, center, net, gross, bg_per_ch, n_peak, True)
            )

        provenance = AnalysisProvenance(
            tool="peaks",
            backend=self.name,
            params={
                "half_width_kev": cfg.half_width_kev,
                "bg_gap_kev": cfg.bg_gap_kev,
                "bg_width_kev": cfg.bg_width_kev,
            },
        )
        return PeakMeasurementSet(
            measurements=tuple(measurements),
            provenance=provenance,
            diagnostics=diagnostics,
        )


__all__ = ["NetIntensityMeasurer", "PeakWindowConfig"]
