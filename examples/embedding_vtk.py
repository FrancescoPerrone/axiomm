"""Native VTK 3-D embedding viewer — a local desktop window (no browser).

Run on a machine with a display:

    pip install -e ".[analysis,vtk]"
    python examples/embedding_vtk.py

It builds a synthetic four-phase map, runs PCA + clustering through the pipeline,
and opens a native VTK window with the reduction embedding coloured by cluster.
Swap ``clustering="hdbscan"`` to view a density-clustering result (noise shown grey).

Interaction (no auto-spin): drag = rotate, scroll = zoom, shift/middle-drag = pan,
``r`` re-fits the camera, ``s``/``w`` toggle solid points / wireframe.

The embedding axes are reduced components, not physical quantities — an exploratory
view of cluster separation, not a validated result.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.reporting.embedding_vtk import show_embedding_vtk_from_result
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def _four_phase_map(ny=60, nx=60, ne=400, seed=0):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02

    def peak(c, a):
        return a * np.exp(-((e - c) ** 2) / (2 * 0.05**2))

    cube = np.full((ny, nx, ne), 2.0)
    cube[: ny // 2, : nx // 2] += 300 * (peak(1.254, 1) + peak(1.740, 0.5))   # Mg-Si
    cube[: ny // 2, nx // 2:] += 300 * (peak(3.690, 1) + peak(1.740, 0.6))    # Ca-Si
    cube[ny // 2:, : nx // 2] += 300 * (peak(6.400, 1) + peak(1.740, 0.6))    # Fe-Si
    cube[ny // 2:, nx // 2:] += 300 * (peak(1.486, 1) + peak(1.740, 0.6))     # Al-Si
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


def main() -> int:
    result = Pipeline(groups=4, components=4, seed=0).run(_four_phase_map())
    print("Opening the native VTK viewer — close the window to exit.")
    show_embedding_vtk_from_result(result, title="AXIOMM — reduction embedding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
