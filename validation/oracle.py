"""C3 Cliff–Lorimer hand-derived oracle + eXSpy cross-check + analytic fixture.

Convention (verified empirically against eXSpy 0.3.2 and matching AXIOMM):
composition fraction ``C_i = k_i * I_i / sum_j(k_j * I_j)``.

Analytic fixture (recorded in the preregistration): intensities ``I = [100, 50]``,
k-factors ``k = [2, 1]`` → expected ratio ``A/B = (2*100)/(1*50) = 4.0``. This is
the factor-orientation check (decision report §7.2).
"""
from __future__ import annotations

import numpy as np

ANALYTIC_FIXTURE = {
    "intensities": [100.0, 50.0],
    "kfactors": [2.0, 1.0],
    "expected_ratio_A_over_B": 4.0,
}


def oracle_fractions(intensities, kfactors) -> np.ndarray:
    """Cliff–Lorimer weight fractions ``C_i = k_i*I_i / sum(k_j*I_j)``."""
    inten = np.asarray(intensities, dtype=float)
    kf = np.asarray(kfactors, dtype=float)
    w = kf * inten
    return w / w.sum()


def oracle_ratio(intensities, kfactors, a: int, b: int) -> float:
    f = oracle_fractions(intensities, kfactors)
    return float(f[a] / f[b])


def exspy_fractions(intensities, kfactors) -> np.ndarray:
    """eXSpy's independent Cliff–Lorimer implementation (same convention)."""
    from exspy._misc.eds.utils import quantification_cliff_lorimer
    inten = np.asarray(intensities, dtype=float).reshape(-1, 1)
    comp = quantification_cliff_lorimer(inten, [float(k) for k in kfactors])
    return np.array([float(np.ravel(c)[0]) for c in comp], dtype=float)
