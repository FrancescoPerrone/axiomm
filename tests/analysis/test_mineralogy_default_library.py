"""Tests for the default mineralogy preset (Stage two, S3a)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.mineralogy._default_library import MINERALOGY_DEFAULT_V1
from axiomm.analysis.mineralogy.reference import MineralogyReference


def test_preset_is_a_valid_mineralogy_reference():
    assert isinstance(MINERALOGY_DEFAULT_V1, MineralogyReference)
    MINERALOGY_DEFAULT_V1.validate()  # must not raise


def test_preset_has_the_full_endmember_set_including_glass():
    names = [m.name for m in MINERALOGY_DEFAULT_V1.minerals]
    assert len(names) >= 43
    assert any("glass" in n.lower() for n in names)          # silicate glass endmember
    assert "Magnetite" in names and "Hematite" in names


def test_preset_structural_exclude_and_family_coverage():
    ref = MINERALOGY_DEFAULT_V1
    assert ref.structural_exclude == frozenset({"O", "Br", "I"})
    used = {m.family for m in ref.minerals}
    assert used.issubset(set(ref.family_display))            # every family displayable


def test_preset_vectors_normalized_and_o_excluded():
    ref = MINERALOGY_DEFAULT_V1
    order = ref.element_order()
    o_idx = order.index("O")
    for _name, vec in ref.mineral_vectors():
        assert vec[o_idx] == 0.0
        assert vec.sum() == pytest.approx(1.0)


def test_preset_magnetite_hematite_degeneracy():
    vectors = dict(MINERALOGY_DEFAULT_V1.mineral_vectors())
    assert np.allclose(vectors["Magnetite"], vectors["Hematite"])


def test_endmember_provenance_distinguishes_ideal_measured_standard():
    prov = {m.name: m.provenance for m in MINERALOGY_DEFAULT_V1.minerals}
    # Idealized stoichiometric endmember.
    assert "idealized" in prov["Quartz"].lower()
    # Measured phase from the experiment EPMA tables.
    assert "experiment_compositions" in prov["Silicate glass (measured)"].lower()
    # GeoReM reference standard.
    assert "standards.xlsx" in prov["Glass std GSE-1G"].lower()
    assert "standards.xlsx" in prov["Std ODAP(apatite)"].lower()


def test_preset_emission_lines_ka_except_iodine():
    elements = MINERALOGY_DEFAULT_V1.elements
    assert elements["I"].emission_line == "La"
    assert elements["Si"].emission_line == "Ka"
    assert elements["Fe"].emission_line == "Ka"
