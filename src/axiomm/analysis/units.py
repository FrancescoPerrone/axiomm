"""Small unit helpers shared across the public API.

Currently: :func:`parse_energy_kev`, the one routine that normalises a user-supplied
energy (a units-bearing string or a number) to keV, so every public boundary that
takes an energy agrees on the contract.
"""

from __future__ import annotations

import math
import re

from axiomm.analysis.errors import PayloadValidationError

_ENERGY_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*(keV|eV)\s*$", re.IGNORECASE)
_PER_UNIT_KEV = {"kev": 1.0, "ev": 1e-3}


def parse_energy_kev(value) -> float:
    """Return an incident energy in **keV** from a units-string or a number.

    - ``"13.55 keV"`` → 13.55; ``"2900 eV"`` → 2.9 (case-insensitive, optional space);
      scientific notation is accepted (``"1e4 eV"`` → 10.0).
    - a plain number is interpreted as **keV** by documented convention (``13.55`` → 13.55).
    - a unitless string (``"13.55"``), an unknown unit, a boolean, or a non-finite /
      non-positive value raises :class:`PayloadValidationError` — the contract never guesses.
    """
    if isinstance(value, bool):
        raise PayloadValidationError(f"beam energy must be a number or units-string, not a bool; got {value!r}.")
    if isinstance(value, (int, float)):
        kev = float(value)
    elif isinstance(value, str):
        m = _ENERGY_RE.match(value)
        if not m:
            raise PayloadValidationError(
                f"beam energy string must be a number with a unit, e.g. '13.55 keV' or "
                f"'2900 eV'; got {value!r} (a bare number string has no unit).")
        kev = float(m.group(1)) * _PER_UNIT_KEV[m.group(2).lower()]
    else:
        raise PayloadValidationError(
            f"beam energy must be a units-string or a number (keV); got {type(value).__name__}.")
    if not math.isfinite(kev) or kev <= 0:
        raise PayloadValidationError(f"beam energy must be finite and > 0 keV; got {kev!r}.")
    return kev


__all__ = ["parse_energy_kev"]
