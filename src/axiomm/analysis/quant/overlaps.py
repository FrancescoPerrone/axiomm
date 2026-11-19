"""Emission-line overlap detection for quantification.

An energy-dispersive detector cannot resolve two emission lines closer than its
energy resolution, so measuring each in its own window double-counts the shared
peak. This module finds such overlaps among a set of element lines so the
quantifier can report them (a diagnostic) and refuse to quantify the blend as
independent elements — it does not guess which element the peak belongs to.

Pure and headless: operates on ``{symbol: line_energy_keV}`` + a resolution.
"""

from __future__ import annotations


def detect_line_overlaps(line_energies: dict[str, float],
                         resolution_kev: float) -> list[tuple[str, ...]]:
    """Group element symbols whose lines fall within ``resolution_kev``.

    Lines are sorted by energy; a run of lines each within ``resolution_kev`` of
    its neighbour forms one unresolvable group. Returns a list of sorted symbol
    tuples (groups of size >= 2); an empty list when nothing overlaps. A
    ``resolution_kev`` of 0 disables detection.
    """
    if resolution_kev <= 0:
        return []
    items = sorted((float(e), s) for s, e in line_energies.items())
    groups: list[tuple[str, ...]] = []
    run: list[tuple[float, str]] = []
    for e, s in items:
        if run and e - run[-1][0] <= resolution_kev:
            run.append((e, s))
        else:
            if len(run) > 1:
                groups.append(tuple(sorted(x[1] for x in run)))
            run = [(e, s)]
    if len(run) > 1:
        groups.append(tuple(sorted(x[1] for x in run)))
    return groups


__all__ = ["detect_line_overlaps"]
