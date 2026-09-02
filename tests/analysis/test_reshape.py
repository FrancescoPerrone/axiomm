"""Tests for the validating reshape helper (Stage two, S2)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.reshape import FlattenedSignal, pixels_by_channels
from axiomm.io.converters.models import AxisSpec, AxiommSignalPayload


def _payload(data, axes):
    return AxiommSignalPayload(data=data, axes=axes, signal_kind="signal1d")


def _good():
    data = np.arange(4 * 3 * 8, dtype=float).reshape(4, 3, 8)
    axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 8, index_in_array=2),
    )
    return _payload(data, axes)


def test_flattens_to_pixels_by_channels():
    flat = pixels_by_channels(_good())
    assert isinstance(flat, FlattenedSignal)
    assert flat.matrix.shape == (12, 8)
    assert flat.nav_shape == (4, 3)
    assert flat.n_pixels == 12
    assert flat.n_channels == 8
    assert flat.signal_index == 2


def test_non_last_signal_axis_moves_correctly():
    data = np.arange(8 * 4 * 3, dtype=float).reshape(8, 4, 3)
    axes = (
        AxisSpec("Energy", "signal", 8, index_in_array=0),
        AxisSpec("x", "navigation", 4, index_in_array=1),
        AxisSpec("y", "navigation", 3, index_in_array=2),
    )
    flat = pixels_by_channels(_payload(data, axes))
    assert flat.matrix.shape == (12, 8)
    assert flat.nav_shape == (4, 3)


def test_requires_exactly_one_signal_axis():
    data = np.zeros((4, 3, 8))
    axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("z", "navigation", 8, index_in_array=2),
    )
    with pytest.raises(PayloadValidationError, match="exactly one signal axis"):
        pixels_by_channels(_payload(data, axes))


def test_mismatched_navigation_size_raises():
    data = np.zeros((4, 3, 8))
    axes = (  # x declares size 5 but data dim 0 is 4
        AxisSpec("x", "navigation", 5, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 8, index_in_array=2),
    )
    with pytest.raises(PayloadValidationError, match="declares size"):
        pixels_by_channels(_payload(data, axes))


def test_non_numeric_dtype_raises():
    data = np.array([["a", "b"], ["c", "d"]], dtype=object).reshape(2, 1, 2)
    axes = (
        AxisSpec("x", "navigation", 2, index_in_array=0),
        AxisSpec("y", "navigation", 1, index_in_array=1),
        AxisSpec("Energy", "signal", 2, index_in_array=2),
    )
    with pytest.raises(PayloadValidationError, match="numeric"):
        pixels_by_channels(_payload(data, axes))


def test_non_finite_values_raise():
    data = np.arange(4 * 3 * 8, dtype=float).reshape(4, 3, 8)
    data[0, 0, 0] = np.nan
    axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 8, index_in_array=2),
    )
    with pytest.raises(PayloadValidationError, match="non-finite"):
        pixels_by_channels(_payload(data, axes))
