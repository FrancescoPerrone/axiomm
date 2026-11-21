"""S8.2 — per-element energy-selection policy."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import BackendNotFoundError, PayloadValidationError
from axiomm.analysis.fusion import BestExcitedPolicy, energy_selectors, select_energies
from axiomm.analysis.mineralogy.reference import ElementRef

# Approximate K-edge energies (keV), used as a stub so the policy logic is tested
# without xraylib.
_EDGES = {"P": 2.145, "Si": 1.839, "Ca": 4.038, "Ti": 4.966, "Fe": 7.112, "Zr": 17.998}


def _ref(sym, z, line="Ka"):
    return ElementRef(sym, 1.0, 20.0, z, None, line)


def _edge(ref):
    return _EDGES[ref.symbol]


def test_best_excited_splits_light_and_mid_z():
    """The dual-energy intent: light elements → low energy, mid-Z → high energy."""
    refs = [_ref("P", 15), _ref("Si", 14), _ref("Ca", 20), _ref("Ti", 22), _ref("Fe", 26)]
    chosen, diags = select_energies((2.9, 13.55), refs, edge_energy=_edge)
    assert chosen == {"P": 2.9, "Si": 2.9, "Ca": 13.55, "Ti": 13.55, "Fe": 13.55}
    assert not [d for d in diags if d.code == "not_excited"]


def test_lowest_energy_above_edge_is_chosen():
    # Ca edge 4.038: among {2.9, 5.0, 13.55} the lowest ABOVE the edge is 5.0.
    chosen, _ = select_energies((2.9, 5.0, 13.55), [_ref("Ca", 20)], edge_energy=_edge)
    assert chosen == {"Ca": 5.0}


def test_not_excited_when_edge_above_all_energies():
    chosen, diags = select_energies((2.9, 13.55), [_ref("Zr", 40)], edge_energy=_edge)
    assert chosen == {"Zr": None}
    assert any(d.code == "not_excited" and d.severity == "warning" for d in diags)


def test_policy_by_name_and_params():
    chosen, _ = select_energies((2.9, 13.55), [_ref("Fe", 26)], policy="best_excited",
                                edge_energy=_edge)
    assert chosen == {"Fe": 13.55}
    assert BestExcitedPolicy().params() == {"policy": "best_excited"}


def test_registry_resolves_and_rejects():
    assert isinstance(energy_selectors.get("best_excited"), BestExcitedPolicy)
    with pytest.raises(BackendNotFoundError):
        energy_selectors.get("nope")


def test_select_energies_rejects_bad_policy():
    with pytest.raises(PayloadValidationError):
        select_energies((2.9,), [_ref("Fe", 26)], policy=object(), edge_energy=_edge)


def test_real_xraylib_edges_split_as_expected():
    """With real absorption edges, P/Si go to 2.9 keV and Ca/Ti/Fe to 13.55 keV."""
    pytest.importorskip("xraylib")
    refs = [_ref("P", 15), _ref("Si", 14), _ref("Ca", 20), _ref("Ti", 22), _ref("Fe", 26)]
    chosen, diags = select_energies((2.9, 13.55), refs)   # real element_edge_kev
    assert chosen["P"] == 2.9 and chosen["Si"] == 2.9
    assert chosen["Ca"] == 13.55 and chosen["Ti"] == 13.55 and chosen["Fe"] == 13.55
    assert not [d for d in diags if d.code == "not_excited"]
