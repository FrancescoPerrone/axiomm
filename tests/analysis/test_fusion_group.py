"""S8.1 — multi-energy map group + registration contract."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError, RegistrationError
from axiomm.analysis.fusion import EnergyMap, MultiEnergyMapGroup, verify_registration
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _payload(ny=4, nx=5, ne=8, scale=2.0, offset=0.0):
    axes = (
        AxisSpec("y", "navigation", ny, units="µm", scale=scale, offset=offset, index_in_array=0),
        AxisSpec("x", "navigation", nx, units="µm", scale=scale, offset=offset, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.01, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=np.zeros((ny, nx, ne)), axes=axes, signal_kind="signal1d")


# -- EnergyMap ---------------------------------------------------------------

@pytest.mark.parametrize("bad", [-1.0, 0.0, "x", True, float("nan")])
def test_energy_map_rejects_bad_energy(bad):
    with pytest.raises(PayloadValidationError):
        EnergyMap(bad, _payload())


def test_energy_map_rejects_non_payload():
    with pytest.raises(PayloadValidationError):
        EnergyMap(13.55, object())


def test_energy_map_coerces_energy_to_float():
    em = EnergyMap(13, _payload())
    assert isinstance(em.excitation_kev, float) and em.excitation_kev == 13.0


# -- MultiEnergyMapGroup -----------------------------------------------------

def test_group_from_pairs_iter_and_energies():
    g = MultiEnergyMapGroup.from_pairs([(2.9, _payload()), (13.55, _payload())])
    assert len(g) == 2
    assert g.energies() == (2.9, 13.55)
    assert [m.excitation_kev for m in g] == [2.9, 13.55]


def test_empty_group_raises():
    with pytest.raises(PayloadValidationError):
        MultiEnergyMapGroup(())


def test_group_rejects_non_energymap_members():
    with pytest.raises(PayloadValidationError):
        MultiEnergyMapGroup((object(),))


# -- registration verify -----------------------------------------------------

def test_verify_registration_ok_same_grid():
    g = MultiEnergyMapGroup.from_pairs([(2.9, _payload()), (13.55, _payload())])
    diags = verify_registration(g)
    codes = {d.code for d in diags}
    assert codes == {"registration_verified"}


def test_verify_registration_single_map_is_noop():
    g = MultiEnergyMapGroup.from_pairs([(13.55, _payload())])
    assert {d.code for d in verify_registration(g)} == {"registration_verified"}


def test_verify_registration_shape_mismatch_raises():
    g = MultiEnergyMapGroup.from_pairs([(2.9, _payload(nx=5)), (13.55, _payload(nx=6))])
    with pytest.raises(RegistrationError):
        verify_registration(g)


def test_verify_registration_scale_mismatch_raises():
    g = MultiEnergyMapGroup.from_pairs([(2.9, _payload(scale=2.0)), (13.55, _payload(scale=2.5))])
    with pytest.raises(RegistrationError):
        verify_registration(g)


def test_verify_registration_nonstrict_returns_warning():
    g = MultiEnergyMapGroup.from_pairs([(2.9, _payload(nx=5)), (13.55, _payload(nx=7))])
    diags = verify_registration(g, strict=False)
    assert any(d.code == "registration_mismatch" and d.severity == "warning" for d in diags)


def test_verify_registration_offset_within_tolerance_ok():
    g = MultiEnergyMapGroup.from_pairs([(2.9, _payload(offset=0.0)),
                                        (13.55, _payload(offset=0.0005))])
    assert {d.code for d in verify_registration(g, offset_atol=1e-3)} == {"registration_verified"}
