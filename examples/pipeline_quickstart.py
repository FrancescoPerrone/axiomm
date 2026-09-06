"""AXIOMM quick start — the pipeline is the front door.

The whole analysis in one call. Give the pipeline a map, get back one result you
can read, plot, and save:

    from axiomm import Pipeline
    result = Pipeline(beam_energy_kev=15).run("map.bcf")
    print(result.summary())

This script shows that on a small synthetic map so it runs anywhere (a real run
would pass a file path instead of a payload). It needs the analysis + quant
extras:  pip install -e ".[all,quant]"
"""

from __future__ import annotations

import numpy as np

from axiomm import Pipeline
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _demo_reference():
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "ideal", basis="atom_counts"),
        MineralEndmember("Wollastonite", "pyroxenoid", {"Ca": 1, "Si": 1, "O": 3}, None, "ideal", basis="atom_counts"),
    )
    return MineralogyReference(
        name="quickstart_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}),
        family_display={"olivine": "Olivine", "pyroxenoid": "Ca-silicate"})


def _demo_map(ny=40, nx=50, ne=500, seed=0):
    """Two mineral domains as a synthetic (y, x, energy) EDS map."""
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)

    def add(sl, lines):
        for centre, amp in lines:
            cube[sl] += amp * np.exp(-((e - centre) ** 2) / (2 * 0.05 ** 2))

    add((slice(None, ny // 2),), [(1.254, 4000), (1.740, 2000)])   # olivine (Mg, Si)
    add((slice(ny // 2, None),), [(3.690, 3500), (1.740, 3500)])   # Ca-silicate (Ca, Si)
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


def main() -> int:
    map_payload = _demo_map()

    # --- the one call ---------------------------------------------------------
    result = Pipeline(
        groups=2,                       # how many mineral groups to look for
        beam_energy_kev=15.0,           # needed to quantify + match
        reference=_demo_reference(),    # which mineral library
    ).run(map_payload)

    print(result.summary())
    print("\nwhat it found:")
    for row in result.clusters:
        print(" ", row)

    if result.phase_map is not None:
        names, counts = np.unique(result.phase_map, return_counts=True)
        print("\nphase map (pixels per phase):",
              {str(n): int(c) for n, c in zip(names, counts, strict=True)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
