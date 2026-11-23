"""Chunk 2 — plain-English aliases in the stage tools (energy + library/reference_element)."""

from __future__ import annotations

import pytest

from axiomm import compute_k_factors, get_reference, match_minerals
from axiomm.analysis.aliases import UNSET, resolve_alias
from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.reference import ElementRef

# -- the shared resolver -----------------------------------------------------

def test_resolve_alias_picks_the_supplied_one():
    assert resolve_alias("a", 1, "b", UNSET) == 1
    assert resolve_alias("a", UNSET, "b", 2) == 2


def test_resolve_alias_both_supplied_errors():
    with pytest.raises(PayloadValidationError):
        resolve_alias("a", 1, "b", 2)


def test_resolve_alias_default_and_required():
    assert resolve_alias("a", UNSET, "b", UNSET, default=7) == 7
    with pytest.raises(PayloadValidationError):
        resolve_alias("a", UNSET, "b", UNSET)   # required, no default


# -- compute_k_factors -------------------------------------------------------

def _els():
    return [ElementRef("Si", 1.74, 28.085, 14, None, "Ka"),
            ElementRef("Fe", 6.40, 55.845, 26, None, "Ka")]


def test_kfactors_beam_energy_and_reference_element_aliases():
    pytest.importorskip("xraylib")
    new = compute_k_factors(_els(), beam_energy="13.55 keV", reference_element="Si")
    old = compute_k_factors(_els(), excitation_kev=13.55, reference="Si")
    assert new.k_factors == old.k_factors
    assert new.excitation_kev == 13.55


def test_kfactors_rejects_both_energy_words():
    with pytest.raises(PayloadValidationError):      # raised before xraylib is touched
        compute_k_factors(_els(), beam_energy="13 keV", excitation_kev=13.0, reference="Si")


def test_kfactors_rejects_both_reference_words():
    with pytest.raises(PayloadValidationError):
        compute_k_factors(_els(), beam_energy="13 keV", reference="Si", reference_element="Si")


def test_kfactors_requires_an_energy():
    with pytest.raises(PayloadValidationError):
        compute_k_factors(_els(), reference="Si")    # neither excitation_kev nor beam_energy


# -- match_minerals (match_clusters) -----------------------------------------

def test_match_library_alias_accepted():
    ref = get_reference("minerals_default_v2")
    assert match_minerals([], library=ref) == ()     # library threads; empty in -> empty out
    assert match_minerals([], ref) == ()              # positional reference still works


def test_match_rejects_both_library_words():
    with pytest.raises(PayloadValidationError):
        match_minerals([], reference="x", library="y")


def test_match_requires_a_library():
    with pytest.raises(PayloadValidationError):
        match_minerals([])     # neither reference nor library
