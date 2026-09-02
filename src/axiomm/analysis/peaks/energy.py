"""Validated channel->keV energy-axis resolution.

Shared by the peak backends and (later) Cliff-Lorimer quantification, so
the keV mapping is guaranteed identical. Recognises keV and eV units;
never assumes a calibration for unknown units.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import PayloadValidationError

_KEV_PER_UNIT = {"keV": 1.0, "kev": 1.0, "eV": 1e-3, "ev": 1e-3}


def resolve_energy_axis(axis_spec, n_channels: int) -> np.ndarray:
    """Validate ``axis_spec`` against ``n_channels`` and return the keV grid."""
    if axis_spec.size != n_channels:
        raise PayloadValidationError(
            f"energy axis size {axis_spec.size} != spectrum channels {n_channels}."
        )
    if axis_spec.scale is None:
        raise PayloadValidationError(
            "energy axis has no scale; cannot map channels to keV."
        )
    units = axis_spec.units
    if units not in _KEV_PER_UNIT:
        raise PayloadValidationError(
            f"energy axis units {units!r} not recognised (expected keV or eV); "
            f"refusing to assume a calibration."
        )
    factor = _KEV_PER_UNIT[units]
    scale_kev = axis_spec.scale * factor
    offset_kev = axis_spec.offset * factor
    return offset_kev + scale_kev * np.arange(n_channels)


__all__ = ["resolve_energy_axis"]
