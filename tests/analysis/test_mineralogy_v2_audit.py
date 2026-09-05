"""Executable verification of the MINERALOGY_DEFAULT_V2 basis audit (finding 9).

Reproduces the reference-basis audit from the public repository: it loads the
machine-readable manifest (``docs/specs/mineralogy_v2_basis_audit.json``),
checks it covers every V2 endmember, distinguishes ideal-stoichiometric from
data-derived compositions, and — using a committed fixture of PUBLIC GeoReM
oxide wt% — verifies that the documented oxide→cation conversion reproduces the
stored V2 cation proportions. The owner's unpublished spreadsheet is not
committed; it is recorded by SHA-256 in the manifest.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V2 as V2
from axiomm.analysis.mineralogy.match.basis import to_molar_proportions

_MANIFEST = Path(__file__).resolve().parents[2] / "docs" / "specs" / "mineralogy_v2_basis_audit.json"


@pytest.fixture(scope="module")
def manifest():
    return json.loads(_MANIFEST.read_text())


def test_manifest_covers_every_endmember(manifest):
    manifest_names = {e["name"] for e in manifest["endmembers"]}
    live_names = {m.name for m in V2.minerals}
    assert manifest_names == live_names
    assert manifest["reference"]["version"] == V2.version


def test_manifest_records_source_hashes(manifest):
    files = {s["file"]: s for s in manifest["sources"]}
    for name in ("Standards.xlsx", "Experiment_compositions.xlsx"):
        assert len(files[name]["sha256"]) == 64          # a recorded SHA-256
        assert "units" in files[name] and "oxide wt%" in files[name]["units"]


def test_ideal_endmembers_are_stoichiometric(manifest):
    # ideal endmembers carry stoichiometric atom counts (all integers, O included)
    for e in manifest["endmembers"]:
        if e["category"] != "ideal_stoichiometric":
            continue
        comp = e["composition"]
        assert all(float(v).is_integer() for v in comp.values()), e["name"]


def test_data_derived_are_cation_proportions(manifest):
    # measured/standard endmembers are cation atomic proportions (no oxygen key)
    for e in manifest["endmembers"]:
        if e["category"] == "ideal_stoichiometric":
            continue
        assert "O" not in e["composition"], e["name"]


def test_oxide_conversion_reproduces_stored_proportions(manifest):
    """The documented oxide→cation conversion reproduces stored V2 values.

    Public GeoReM oxide wt% (committed fixture) -> the oxide_mass_fraction
    converter -> cation proportions must match the stored V2 endmember within a
    small tolerance (rounding in the stored table).
    """
    by_name = {m.name: m for m in V2.minerals}
    included = set(V2.element_order()) - set(V2.structural_exclude)
    # the converter keys by cation element; the fixture keys by oxide name.
    oxide_to_element = {el.oxide_form[0]: sym for sym, el in V2.elements.items()
                        if el.oxide_form is not None}
    for name, entry in manifest["verification_fixture"]["standards"].items():
        oxide = {oxide_to_element[ox]: wt for ox, wt in entry["oxide_wt_percent"].items()}
        derived = to_molar_proportions(oxide, "oxide_mass_fraction", V2, allowed=included)
        stored_raw = {k: float(v) for k, v in by_name[name].composition.items()}
        total = sum(stored_raw.values())
        stored = {k: v / total for k, v in stored_raw.items()}
        assert set(derived) == set(stored), name
        for el, frac in stored.items():
            assert derived[el] == pytest.approx(frac, abs=2e-3), f"{name}:{el}"
