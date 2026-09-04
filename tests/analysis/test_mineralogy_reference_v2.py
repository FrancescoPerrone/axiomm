"""Tests for the basis-audited V2 mineralogy reference (S3d audit-closure)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.mineralogy import (
    MINERALOGY_DEFAULT_V1,
    MINERALOGY_DEFAULT_V2,
    MINERALOGY_V2_BASIS_AUDIT,
)
from axiomm.analysis.mineralogy.reference import (
    COMPOSITION_BASES,
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)


def test_v2_every_endmember_has_audited_basis():
    assert MINERALOGY_DEFAULT_V2.version == "2"
    assert all(m.basis in COMPOSITION_BASES for m in MINERALOGY_DEFAULT_V2.minerals)
    MINERALOGY_DEFAULT_V2.validate(strict=True)


def test_v1_endmembers_remain_unaudited():
    # V1 meaning is unchanged: its endmembers carry no declared basis
    assert all(m.basis is None for m in MINERALOGY_DEFAULT_V1.minerals)


def test_v2_audit_records_oxide_source():
    audit = MINERALOGY_V2_BASIS_AUDIT
    assert "oxide wt%" in audit["measured"]["units"]
    assert "FeO" in audit["measured"]["fe_convention"]
    assert "Experiment_compositions.xlsx" in audit["measured"]["source"]
    assert "Standards.xlsx" in audit["standard"]["source"]


def test_strict_rejects_unknown_basis():
    els = {"Si": ElementRef("Si", 1.74, 28.085, 14, ("SiO2", 1, 2), "Ka"),
           "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka")}
    ref = MineralogyReference(
        name="x", version="1", elements=els,
        minerals=(MineralEndmember("Q", "silica", {"Si": 1, "O": 2}, None, "p",
                                   basis="mystery_basis"),),
        structural_exclude=frozenset({"O"}),
        family_display={"silica": "Silica"},
    )
    with pytest.raises(PayloadValidationError, match="basis"):
        ref.validate(strict=True)


def test_strict_rejects_composition_key_not_in_elements():
    els = {"Si": ElementRef("Si", 1.74, 28.085, 14, ("SiO2", 1, 2), "Ka")}
    ref = MineralogyReference(
        name="x", version="1", elements=els,
        minerals=(MineralEndmember("Q", "silica", {"Si": 1, "Zz": 1}, None, "p",
                                   basis="atom_counts"),),
        structural_exclude=frozenset(),
        family_display={"silica": "Silica"},
    )
    with pytest.raises(PayloadValidationError, match="not in the reference element set"):
        ref.validate(strict=True)


def test_strict_rejects_duplicate_names():
    els = {"Si": ElementRef("Si", 1.74, 28.085, 14, ("SiO2", 1, 2), "Ka")}
    m = MineralEndmember("Q", "silica", {"Si": 1}, None, "p", basis="atom_counts")
    ref = MineralogyReference(
        name="x", version="1", elements=els, minerals=(m, m),
        structural_exclude=frozenset(), family_display={"silica": "Silica"},
    )
    with pytest.raises(PayloadValidationError, match="duplicate"):
        ref.validate(strict=True)


def test_strict_rejects_degenerate_composition():
    els = {"Si": ElementRef("Si", 1.74, 28.085, 14, ("SiO2", 1, 2), "Ka"),
           "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka")}
    ref = MineralogyReference(
        name="x", version="1", elements=els,
        minerals=(MineralEndmember("AllOxygen", "silica", {"O": 2}, None, "p",
                                   basis="atom_counts"),),   # zero over included
        structural_exclude=frozenset({"O"}),
        family_display={"silica": "Silica"},
    )
    with pytest.raises(PayloadValidationError, match="degenerate"):
        ref.validate(strict=True)
