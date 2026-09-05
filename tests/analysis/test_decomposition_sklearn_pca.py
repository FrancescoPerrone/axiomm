"""Tests for SklearnPCADecomposer (Stage two, S1)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _payload_last_axis_signal():
    """A (4, 3, 8) spectrum image (12 pixels, 8 channels), signal last."""
    rng = np.random.default_rng(0)
    base = rng.random((2, 8))          # two latent spectra
    coeffs = rng.random((12, 2))       # per-pixel mixtures
    data = (coeffs @ base).reshape(4, 3, 8)
    axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 8, index_in_array=2),
    )
    return AxiommSignalPayload(data=data, axes=axes, signal_kind="signal1d")


def test_pca_shapes_variance_and_provenance():
    pytest.importorskip("sklearn")
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer

    result = SklearnPCADecomposer().decompose(_payload_last_axis_signal(), n_components=2)
    assert result.factors.shape == (8, 2)
    assert result.loadings.shape == (12, 2)
    assert result.explained_variance_ratio.shape == (2,)
    assert result.nav_shape == (4, 3)
    assert result.n_components == 2
    assert result.explained_variance_ratio[0] >= result.explained_variance_ratio[1]
    assert result.provenance.tool == "decomposition"
    assert result.provenance.backend == "pca"
    assert result.provenance.params == {"n_components": 2, "random_state": 0}


def test_pca_none_keeps_min_components():
    pytest.importorskip("sklearn")
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer

    result = SklearnPCADecomposer().decompose(_payload_last_axis_signal())
    # min(n_pixels=12, n_channels=8) == 8
    assert result.n_components == 8
    assert result.factors.shape == (8, 8)


def test_pca_handles_non_last_signal_axis():
    pytest.importorskip("sklearn")
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer

    p_last = _payload_last_axis_signal()
    data_first = np.moveaxis(p_last.data, -1, 0)  # (8, 4, 3), Energy first
    axes = (
        AxisSpec("Energy", "signal", 8, index_in_array=0),
        AxisSpec("x", "navigation", 4, index_in_array=1),
        AxisSpec("y", "navigation", 3, index_in_array=2),
    )
    p_first = AxiommSignalPayload(data=data_first, axes=axes, signal_kind="signal1d")

    r_last = SklearnPCADecomposer().decompose(p_last, n_components=3)
    r_first = SklearnPCADecomposer().decompose(p_first, n_components=3)
    assert r_first.factors.shape == (8, 3)
    assert r_first.nav_shape == (4, 3)
    assert np.allclose(r_first.explained_variance_ratio, r_last.explained_variance_ratio)


def test_pca_too_many_components_raises():
    # Validation happens before sklearn import → no importorskip needed.
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer

    with pytest.raises(PayloadValidationError, match="exceeds"):
        SklearnPCADecomposer().decompose(_payload_last_axis_signal(), n_components=99)


def test_pca_requires_exactly_one_signal_axis():
    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer

    data = np.zeros((4, 3, 8))
    axes = (  # no signal-role axis
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("z", "navigation", 8, index_in_array=2),
    )
    payload = AxiommSignalPayload(data=data, axes=axes, signal_kind="signal1d")
    with pytest.raises(PayloadValidationError, match="exactly one signal axis"):
        SklearnPCADecomposer().decompose(payload)


def test_pca_is_reproducible_by_default():
    """Default random_state seeds the randomized SVD, so PCA is deterministic."""
    pytest.importorskip("sklearn")
    import numpy as np

    from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer
    rng = np.random.default_rng(0)
    payload = _payload_last_axis_signal()
    payload.data = rng.random(payload.data.shape)   # larger-variance input
    a = SklearnPCADecomposer().decompose(payload, n_components=2)
    b = SklearnPCADecomposer().decompose(payload, n_components=2)
    assert np.array_equal(a.loadings, b.loadings)
    assert a.provenance.params["random_state"] == 0
