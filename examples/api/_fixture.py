"""A tiny synthetic map for exercising the worked API examples without real data.

Two spatial domains with different element peaks, on a 0-20 keV energy axis, so the
whole public chain (decompose -> cluster -> means -> peaks -> k-factors -> quantify ->
reliability -> match) runs end to end. Not science — just a runnable fixture.
"""
from __future__ import annotations

import numpy as np

from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def synthetic_payload(ny: int = 10, nx: int = 10, ne: int = 1000, seed: int = 0):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02  # 0.02 keV/channel -> 0..~20 keV
    cube = np.full((ny, nx, ne), 3.0)

    def add(sl, lines):
        for centre, amp in lines:
            cube[sl] += amp * np.exp(-((e - centre) ** 2) / (2 * 0.06 ** 2))

    add((slice(None, ny // 2),), [(1.740, 300), (3.690, 260), (4.510, 200)])  # Si, Ca, Ti
    add((slice(ny // 2, None),), [(1.740, 300), (6.400, 320)])                # Si, Fe
    cube += rng.normal(0, 2.0, cube.shape).clip(min=-3)

    axes = (
        AxisSpec("y", "navigation", ny, units="µm", scale=1.0, offset=0.0, index_in_array=0),
        AxisSpec("x", "navigation", nx, units="µm", scale=1.0, offset=0.0, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")
