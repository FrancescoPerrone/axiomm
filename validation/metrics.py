"""Metric definitions for the v0.1 validation pilot — committed before results.

Per the decision report: C1 uses signed truth-relative error with a 95% CI of the
mean per stratum; the margin is the smallest predeclared candidate whose band
contains every high-signal stratum's whole CI. Detection uses AXIOMM's declared
screening policy (the reliability net-count floor), not merely net > 0.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

#: AXIOMM's declared screening policy = ReliabilityConfig.count_floor default.
#: A positive background-subtracted estimate alone is NOT a detection.
DETECTION_THRESHOLD = 50.0

#: The ONLY candidate margins for systematic bias (decision report C1).
C1_CANDIDATE_MARGINS = (0.05, 0.10)

#: LOCKED C1 margin (signed off 26 Nov 2026): the smallest candidate the pilot
#: supported in every high-signal stratum. The held-out set is judged against this.
C1_LOCKED_MARGIN = 0.05


def signed_rel_error(estimate: float, truth: float) -> float:
    return (float(estimate) - float(truth)) / float(truth)


def ci95_mean(values) -> tuple[float, float, float, int]:
    """95% Student-t interval for the mean. Returns ``(mean, lo, hi, n)``."""
    v = np.asarray(values, dtype=float)
    n = int(v.size)
    mean = float(v.mean()) if n else float("nan")
    if n < 2:
        return mean, mean, mean, n
    half = float(stats.sem(v)) * float(stats.t.ppf(0.975, n - 1))
    return mean, mean - half, mean + half, n


def rmse(values) -> float:
    v = np.asarray(values, dtype=float)
    return float(np.sqrt(np.mean(v ** 2)))


def select_margin(ci_by_stratum: dict, candidates=C1_CANDIDATE_MARGINS):
    """Smallest candidate margin ``m`` whose band ``[-m, m]`` contains EVERY
    stratum's 95% CI for mean signed relative error. Returns ``(margin|None, detail)``."""
    for m in sorted(candidates):
        if all(lo >= -m and hi <= m for (lo, hi) in ci_by_stratum.values()):
            return m, f"all high-signal strata CIs within ±{m:.0%}"
    return None, "no candidate margin contains every high-signal stratum CI"


def within_margin(ci_by_stratum: dict, margin: float) -> bool:
    """True iff every stratum's 95% CI lies within the LOCKED band ``[-margin, margin]``."""
    return all(lo >= -margin and hi <= margin for (lo, hi) in ci_by_stratum.values())


def is_detection(net: float, threshold: float = DETECTION_THRESHOLD) -> bool:
    return float(net) >= float(threshold)
