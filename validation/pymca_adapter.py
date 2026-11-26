"""PyMca secondary diagnostic for C1 (decision report §5.2).

Within-window net from a PyMca ``Gefit`` Gaussian + linear-background fit, integrated
over the SAME window AXIOMM uses — so AXIOMM net, PyMca net and the injected truth all
refer to the same line component and integration support.

Sealed fit settings (committed before the held-out run):
  region  = line center ± REGION_HALF_KEV
  model   = a + b*x + SpecfitFuns.gauss([H, pos, fwhm], x)   (linear bg + one Gaussian)
  solver  = PyMca Gefit.LeastSquaresFit
  net     = sum of the FITTED Gaussian over [center ± generator.HALF_WIDTH_KEV]
Verified on noiseless pilot fixtures: PyMca net == within-window truth to ~1e-13.
"""
from __future__ import annotations

import numpy as np

import generator

REGION_HALF_KEV = 0.25   # fit-region half-width around each line


def _grid(axis) -> np.ndarray:
    return np.arange(axis.size) * float(axis.scale) + float(axis.offset)


def pymca_net_in_window(counts, axis, center: float) -> float:
    """PyMca fitted-Gaussian net integrated over AXIOMM's peak window. NaN on fit failure."""
    from PyMca5.PyMcaMath.fitting import Gefit, SpecfitFuns
    grid = _grid(axis)
    reg = (grid >= center - REGION_HALF_KEV) & (grid <= center + REGION_HALF_KEV)
    x = grid[reg]
    y = np.asarray(counts, dtype=float)[reg]

    def model(p, xx):
        a, b, h, pos, fwhm = p
        return a + b * xx + SpecfitFuns.gauss([h, pos, fwhm], xx)

    p0 = [float(np.median(y)), 0.0, float(max(y.max() - np.median(y), 1.0)), float(center), 0.05]
    try:
        pars = Gefit.LeastSquaresFit(model, p0, xdata=x, ydata=y)[0]
    except Exception:
        return float("nan")
    w = (grid >= center - generator.HALF_WIDTH_KEV) & (grid <= center + generator.HALF_WIDTH_KEV)
    return float(SpecfitFuns.gauss([pars[2], pars[3], pars[4]], grid[w]).sum())


def verify_adapter(axis, lines, background_per_ch) -> dict:
    """Verify on NOISELESS pilot fixtures: PyMca within-window net must recover the
    within-window truth. Returns the max relative difference across the lines."""
    counts, truth = generator.generate(axis, lines, background_per_ch, seed=0, poisson=False)
    diffs = {}
    for label, center, _sigma, _area in lines:
        pn = pymca_net_in_window(counts, axis, center)
        diffs[label] = abs(pn - truth[label]) / truth[label]
    max_diff = max(diffs.values())
    return {"max_rel_diff": max_diff, "per_line": diffs,
            "verified": bool(max_diff < 1e-6)}
