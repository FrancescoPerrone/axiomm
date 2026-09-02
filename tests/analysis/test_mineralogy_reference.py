"""Tests for the mineralogy reference data model (Stage two, S3a)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)


def _mini():
    elements = {
        "O": ElementRef("O", 0.525, 15.999, 8, None),
        "Fe": ElementRef("Fe", 6.404, 55.845, 26, ("FeO", 1, 1)),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2)),
    }
    minerals = (
        MineralEndmember("Magnetite", "fe_ti_oxide", {"Fe": 3, "O": 4}, None, "ideal"),
        MineralEndmember("Hematite", "fe_ti_oxide", {"Fe": 2, "O": 3}, None, "ideal"),
        MineralEndmember("Quartz", "quartz_silica", {"Si": 1, "O": 2}, None, "ideal"),
    )
    return MineralogyReference(
        name="mini", version="1", description="",
        elements=elements, minerals=minerals,
        structural_exclude=frozenset({"O"}),  # only O present in this mini set
        family_display={"fe_ti_oxide": "Fe-Ti oxide", "quartz_silica": "Silica"},
    )


def test_mineral_vectors_exclude_o_and_sum_to_one():
    ref = _mini()
    vectors = dict(ref.mineral_vectors())
    order = ref.element_order()
    o_idx = order.index("O")
    for name, vec in vectors.items():
        assert vec[o_idx] == 0.0                      # O excluded
        assert vec.sum() == pytest.approx(1.0)        # normalized over retained cations


def test_magnetite_hematite_are_identical_cation_vectors():
    vectors = dict(_mini().mineral_vectors())
    assert np.allclose(vectors["Magnetite"], vectors["Hematite"])  # oxidation degeneracy


def test_validate_rejects_exclude_symbol_not_an_element():
    ref = _mini()
    bad = MineralogyReference(
        name="b", version="1", description="",
        elements=ref.elements, minerals=ref.minerals,
        structural_exclude=frozenset({"O", "Zz"}),
        family_display=ref.family_display,
    )
    with pytest.raises(PayloadValidationError, match="Zz"):
        bad.validate()


def test_validate_rejects_family_without_display():
    ref = _mini()
    bad = MineralogyReference(
        name="b", version="1", description="",
        elements=ref.elements, minerals=ref.minerals,
        structural_exclude=ref.structural_exclude,
        family_display={"fe_ti_oxide": "Fe-Ti oxide"},  # missing quartz_silica
    )
    with pytest.raises(PayloadValidationError, match="family_display"):
        bad.validate()


def test_validate_rejects_nonpositive_line_energy():
    bad_elements = {"Si": ElementRef("Si", 0.0, 28.085, 14, ("SiO2", 1, 2))}
    ref = MineralogyReference(
        name="b", version="1", description="",
        elements=bad_elements,
        minerals=(MineralEndmember("Quartz", "quartz_silica", {"Si": 1}, None, "x"),),
        structural_exclude=frozenset(),
        family_display={"quartz_silica": "Silica"},
    )
    with pytest.raises(PayloadValidationError, match="line_energy"):
        ref.validate()


def test_out_of_set_element_is_dropped_with_diagnostic():
    ref = _mini()
    end = MineralEndmember("Trace", "quartz_silica", {"Si": 1, "Ba": 0.6}, None, "x")
    vectors, diagnostics = ref.build_vectors_with_diagnostics((end,))
    order = ref.element_order()
    # Ba is not in the element set → dropped; Si retained and normalized to 1.
    assert vectors[0][1][order.index("Si")] == pytest.approx(1.0)
    assert any(d.code == "unknown_composition_element" for d in diagnostics)


def test_default_preset_is_registered_in_references():
    import axiomm.analysis.mineralogy  # noqa: F401 — triggers registration
    from axiomm.analysis.reference import get_reference

    ref = get_reference("minerals_default_v1")
    assert isinstance(ref, MineralogyReference)
    assert ref.name == "minerals_default_v1"


def test_element_ref_emission_line_defaults_to_ka():
    ref = _mini()
    assert ref.elements["Fe"].emission_line == "Ka"


def test_validate_rejects_bad_emission_line():
    from axiomm.analysis.mineralogy.reference import ElementRef
    bad = MineralogyReference(
        name="b", version="1", description="",
        elements={"Si": ElementRef("Si", 1.74, 28.085, 14, ("SiO2", 1, 2), "Kb")},
        minerals=(),
        structural_exclude=frozenset(),
        family_display={},
    )
    with pytest.raises(PayloadValidationError, match="emission_line"):
        bad.validate()
