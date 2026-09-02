"""Tests for the decomposers registry + convenience API (Stage two, S1)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import BackendNotFoundError
from axiomm.io.converters.models import AxisSpec, AxiommSignalPayload


def test_get_decomposer_returns_pca():
    from axiomm.analysis.decomposition import get_decomposer
    from axiomm.analysis.decomposition.base import Decomposer

    dec = get_decomposer("pca")
    assert dec.name == "pca"
    assert isinstance(dec, Decomposer)


def test_unknown_decomposer_raises():
    from axiomm.analysis.decomposition import get_decomposer

    with pytest.raises(BackendNotFoundError):
        get_decomposer("nope")


def test_decompose_convenience_dispatches():
    pytest.importorskip("sklearn")
    from axiomm.analysis.decomposition import decompose

    rng = np.random.default_rng(1)
    data = rng.random((3, 3, 6))
    axes = (
        AxisSpec("x", "navigation", 3, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 6, index_in_array=2),
    )
    payload = AxiommSignalPayload(data=data, axes=axes, signal_kind="signal1d")
    result = decompose(payload, backend="pca", n_components=2)
    assert result.n_components == 2
    assert result.loadings.shape == (9, 2)
