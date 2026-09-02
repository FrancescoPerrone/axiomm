"""Tests for peaks energy-axis resolution (Stage two, S3b)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.peaks.energy import resolve_energy_axis
from axiomm.io.converters.models import AxisSpec


def _axis(size, scale, offset=0.0, units="keV"):
    return AxisSpec("Energy", "signal", size, units=units, scale=scale, offset=offset)


def test_kev_axis_builds_expected_grid():
    e = resolve_energy_axis(_axis(5, 0.01), 5)
    np.testing.assert_allclose(e, [0.0, 0.01, 0.02, 0.03, 0.04])


def test_ev_units_convert_to_kev():
    e = resolve_energy_axis(_axis(5, 10.0, units="eV"), 5)
    np.testing.assert_allclose(e, [0.0, 0.01, 0.02, 0.03, 0.04])


def test_size_mismatch_raises():
    with pytest.raises(PayloadValidationError, match="size"):
        resolve_energy_axis(_axis(5, 0.01), 6)


def test_missing_scale_raises():
    with pytest.raises(PayloadValidationError, match="scale"):
        resolve_energy_axis(AxisSpec("Energy", "signal", 5, units="keV", scale=None), 5)


def test_unknown_units_raise_no_silent_default():
    with pytest.raises(PayloadValidationError, match="not recognised"):
        resolve_energy_axis(_axis(5, 0.01, units="channel"), 5)
    with pytest.raises(PayloadValidationError, match="not recognised"):
        resolve_energy_axis(AxisSpec("Energy", "signal", 5, units=None, scale=0.01), 5)
