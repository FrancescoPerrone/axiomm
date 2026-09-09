"""Ergonomic API chunk 3 — AxiommSignalPayload.from_array."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.io.converters.errors import SignalValidationError
from axiomm.io.converters.models import AxiommSignalPayload


def test_from_array_builds_nav_and_signal_axes():
    cube = np.zeros((8, 10, 200))
    p = AxiommSignalPayload.from_array(cube, energy_scale=0.02, energy_offset=-0.1)
    roles = [(a.name, a.role, a.size, a.index_in_array) for a in p.axes]
    assert roles == [
        ("y", "navigation", 8, 0),
        ("x", "navigation", 10, 1),
        ("Energy", "signal", 200, 2),
    ]
    sig = next(a for a in p.axes if a.role == "signal")
    assert sig.scale == 0.02 and sig.offset == -0.1 and sig.units == "keV"
    assert p.signal_kind == "signal1d"
    assert p.data.shape == (8, 10, 200)


def test_from_array_2d_single_navigation_axis():
    p = AxiommSignalPayload.from_array(np.zeros((5, 300)), energy_scale=0.01)
    assert [a.role for a in p.axes] == ["navigation", "signal"]
    assert p.axes[0].name == "y" and p.axes[0].index_in_array == 0


def test_from_array_custom_nav_names_and_passthrough():
    p = AxiommSignalPayload.from_array(
        np.zeros((4, 6, 100)), energy_scale=0.05, nav_names=("row", "col"), title="run A")
    assert [a.name for a in p.axes[:2]] == ["row", "col"]
    assert p.title == "run A"


def test_from_array_requires_energy_scale():
    with pytest.raises(TypeError):
        AxiommSignalPayload.from_array(np.zeros((4, 5, 10)))   # energy_scale is keyword-only, required


def test_from_array_rejects_too_few_dims_and_bad_nav_names():
    with pytest.raises(SignalValidationError):
        AxiommSignalPayload.from_array(np.zeros(10), energy_scale=0.02)
    with pytest.raises(SignalValidationError):
        AxiommSignalPayload.from_array(np.zeros((4, 5, 10)), energy_scale=0.02, nav_names=("only-one",))


def test_from_array_feeds_the_pipeline():
    pytest.importorskip("sklearn")
    from axiomm import Pipeline
    rng = np.random.default_rng(0)
    ne = 200
    e = np.arange(ne) * 0.02
    cube = np.full((10, 12, ne), 2.0)
    cube[:5] += 300 * np.exp(-((e - 1.25) ** 2) / (2 * 0.05**2))
    cube[5:] += 300 * np.exp(-((e - 3.69) ** 2) / (2 * 0.05**2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    payload = AxiommSignalPayload.from_array(cube, energy_scale=0.02)
    r = Pipeline(groups=2, components=4).run(payload)
    assert len(r.clusters) == 2
