"""parse_energy_kev — the shared beam-energy contract."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.units import parse_energy_kev


@pytest.mark.parametrize("value,expected", [
    ("13.55 keV", 13.55),
    ("2900 eV", 2.9),
    ("13.55keV", 13.55),        # no space
    ("2.9 KEV", 2.9),           # case-insensitive
    ("  2900 eV  ", 2.9),       # surrounding space
    ("1e4 eV", 10.0),           # scientific notation
    ("1.5e3 eV", 1.5),
    ("2.9E0 keV", 2.9),
    (13.55, 13.55),             # number -> keV by convention
    (2900, 2900.0),             # a bare number is keV, not eV
])
def test_parse_energy_kev_valid(value, expected):
    assert parse_energy_kev(value) == pytest.approx(expected)


@pytest.mark.parametrize("bad", [
    "13.55",            # a string must carry a unit
    "13.55 joules",     # unknown unit
    "keV",              # no number
    "abc",
    True,               # bool is not a number here
    0,                  # non-positive
    -1.0,
    float("inf"),
    float("nan"),
    None,
    ["13.55 keV"],
])
def test_parse_energy_kev_rejects(bad):
    with pytest.raises(PayloadValidationError):
        parse_energy_kev(bad)
