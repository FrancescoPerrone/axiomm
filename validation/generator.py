"""Synthetic XRF spectrum generator for the v0.1 validation pilot.

Independent of AXIOMM, PyMca and eXSpy (numpy only). Produces ``(counts, truth)``
where ``truth[label]`` is the TRUE net peak counts **within the measurement
window** — the same integration support the estimators use — so an estimator's net
refers to the same line component as the injected truth (decision report §5.2).

The window half-width here MUST equal the NetIntensityMeasurer default
(``PeakWindowConfig.half_width_kev = 0.06`` keV); it is asserted in the harness.
"""
from __future__ import annotations

import numpy as np

from axiomm.io.converters.models import AxisSpec

HALF_WIDTH_KEV = 0.06  # must match NetIntensityMeasurer PeakWindowConfig.half_width_kev


def make_axis(n_channels: int, scale_kev: float, offset_kev: float = 0.0) -> AxisSpec:
    return AxisSpec("Energy", "signal", int(n_channels), units="keV",
                    scale=float(scale_kev), offset=float(offset_kev), index_in_array=0)


def _grid(axis: AxisSpec) -> np.ndarray:
    return np.arange(axis.size) * float(axis.scale) + float(axis.offset)


def _gauss_mean(grid: np.ndarray, center: float, sigma: float, area: float) -> np.ndarray:
    """Per-channel MEAN counts for a Gaussian of total ``area`` (pdf x bin width;
    bins are fine relative to sigma so the per-bin approximation is accurate)."""
    bw = float(grid[1] - grid[0])
    pdf = np.exp(-0.5 * ((grid - center) / sigma) ** 2) / (sigma * np.sqrt(2.0 * np.pi))
    return area * pdf * bw


def window_mask(grid: np.ndarray, center: float, half_width: float = HALF_WIDTH_KEV) -> np.ndarray:
    return (grid >= center - half_width) & (grid <= center + half_width)


def generate(axis: AxisSpec, lines, background_per_ch: float, seed: int, poisson: bool = True):
    """``lines``: list of ``(label, center_kev, sigma_kev, area)``.

    Returns ``(counts, truth)``. ``truth[label]`` is the noiseless discrete sum of
    the pure peak component over the measurement window — exactly what a correct
    background-subtracted net recovers in the noiseless limit."""
    grid = _grid(axis)
    mean = np.full(axis.size, float(background_per_ch), dtype=float)
    peak_means: dict[str, np.ndarray] = {}
    for label, center, sigma, area in lines:
        gm = _gauss_mean(grid, float(center), float(sigma), float(area))
        mean += gm
        peak_means[label] = gm
    rng = np.random.default_rng(int(seed))
    counts = rng.poisson(mean).astype(float) if poisson else mean.copy()
    truth: dict[str, float] = {}
    for label, center, _sigma, _area in lines:
        m = window_mask(grid, float(center))
        truth[label] = float(peak_means[label][m].sum())
    return counts, truth
