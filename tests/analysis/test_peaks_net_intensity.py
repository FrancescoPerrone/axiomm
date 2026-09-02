"""Tests for the net-intensity peak backend (Stage two, S3b)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.peaks.net_intensity import NetIntensityMeasurer
from axiomm.io.converters.models import AxisSpec


def _axis(n=1000, scale=0.01):
    return AxisSpec("Energy", "signal", n, units="keV", scale=scale, offset=0.0)


def test_net_recovers_injected_area_over_flat_background():
    spec = np.full(1000, 10.0)
    # inject 5 channels x +20 = 100 counts around 6.40 keV (index 640)
    spec[638:643] += 20.0
    result = NetIntensityMeasurer().measure(spec, _axis(), {"Fe": 6.40})
    m = result.measurements[0]
    assert m.in_range is True
    assert m.net == pytest.approx(100.0, abs=1e-6)
    assert m.gross > m.net                       # background was present
    assert m.background == pytest.approx(10.0)


def test_flat_region_line_has_zero_net():
    spec = np.full(1000, 10.0)
    result = NetIntensityMeasurer().measure(spec, _axis(), {"Ctrl": 2.0})
    assert result.measurements[0].net == pytest.approx(0.0, abs=1e-9)


def test_line_out_of_range_flagged_not_error():
    spec = np.full(1000, 10.0)
    result = NetIntensityMeasurer().measure(spec, _axis(), {"Far": 50.0})
    m = result.measurements[0]
    assert m.in_range is False and m.net == 0.0
    assert any(d.code == "line_out_of_range" for d in result.diagnostics)


def test_non_finite_spectrum_raises():
    spec = np.full(1000, 10.0)
    spec[0] = np.nan
    with pytest.raises(PayloadValidationError, match="non-finite"):
        NetIntensityMeasurer().measure(spec, _axis(), {"Fe": 6.40})


def test_provenance_records_backend_and_windows():
    result = NetIntensityMeasurer().measure(np.full(1000, 1.0), _axis(), {"Fe": 6.40})
    assert result.provenance.tool == "peaks"
    assert result.provenance.backend == "net_intensity"
    assert result.provenance.params["half_width_kev"] == pytest.approx(0.06)
