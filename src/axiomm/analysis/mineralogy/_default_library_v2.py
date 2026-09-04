"""The basis-audited mineralogy reference preset (``minerals_default_v2``).

V2 is V1's 44 endmembers with an **explicit, audited compositional basis** on
every entry, so the S3d matcher can convert every reference and every cluster to
one common molar/element basis before scoring. V1 is left untouched and its
scientific meaning is unchanged; V1 endmembers carry ``basis=None`` and the
matcher refuses them unless the caller explicitly opts in.

Source-basis audit (established from the original files + legacy extraction, not
inferred from the numbers):

* **Idealised endmembers (24)** — stoichiometric atom counts (oxygen included in
  the formula, masked at match time). Basis: ``atom_counts``.
* **Measured phase averages (7)** — source: ``Experiment_compositions.xlsx``,
  sheets *West Kimberley / Basanite / Gaussie*, "Average" rows (StDev rows
  skipped). Source columns are **oxide wt%** (``SiO2, TiO2, Al2O3, Cr2O3, FeO,
  NiO, MnO, MgO, CaO, BaO, …``); iron reported as a single **FeO** (total-Fe)
  column; **F, Cl** given as element wt%; oxygen not reported (implicit).
* **GeoReM standards (13)** — source: ``Standards.xlsx``, ``Compiled`` sheet
  (units row: ``wt%``), columns per standard (GSE-1G, GSD-1G, GOR128-G, BHVO-2G,
  BCR-2G, BB1, SP, UGY, BFS-AMP, BFS-AP, DAP, MDAP, ODAP). Same oxide-wt% basis,
  FeO total, F/Cl as element wt%.

**Conversion actually applied** (legacy ``hybrid_phase_pipeline`` extraction,
verified numerically here, e.g. Apatite Ca:P = 57.5:35.1 ≈ ideal 5:3): each
oxide → cation moles ``= n_cation · wt% / oxide_molar_mass``; F/Cl → moles
``= wt% / atomic_weight``; normalised to **cation atomic proportions per ~100
cations** (oxygen excluded). The stored values are therefore already molar
cation proportions — which is exactly what the ``atom_counts`` basis expects
(normalise counts/proportions over the included elements) — so every V2 entry is
tagged ``atom_counts``. Omitted/unavailable: oxygen (masked), and any trace
element outside the reference element set (e.g. none remain — Ba is included).

No entries were quarantined: the basis of every group is established from the
sources above.
"""

from __future__ import annotations

from axiomm.analysis.mineralogy._default_library import (
    _ELEMENT_DATA,
    _FAMILY_DISPLAY,
    _RAW_MINERALS,
    _provenance_for,
)
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)

# V2 element set = V1 elements + Ba (measured in "Silicate glass"; Ba La line),
# so every composition key resolves to a known element under strict validation.
_ELEMENT_DATA_V2 = dict(_ELEMENT_DATA)
_ELEMENT_DATA_V2["Ba"] = (4.466, 137.327, 56, ("BaO", 1, 1))

_ELEMENTS_V2 = {
    sym: ElementRef(sym, e, w, z, ox, "La" if sym in ("I", "Ba") else "Ka")
    for sym, (e, w, z, ox) in _ELEMENT_DATA_V2.items()
}

#: One machine-readable audit record per source group (see module docstring).
MINERALOGY_V2_BASIS_AUDIT = {
    "idealized": {
        "source": "stoichiometric formulae (hybrid_phase_pipeline MINERAL_LIBRARY)",
        "units": "atom counts", "basis": "atom_counts",
        "fe_convention": "n/a", "f_cl_s": "as formula atoms", "oxygen": "in formula, masked",
    },
    "measured": {
        "source": "Experiment_compositions.xlsx (West Kimberley / Basanite / Gaussie, Average rows)",
        "units": "oxide wt% (SiO2, TiO2, Al2O3, Cr2O3, FeO, NiO, MnO, MgO, CaO, BaO, ...)",
        "conversion": "oxide -> cation moles (n_cation*wt%/oxide_molar_mass); normalized to cation atomic proportions",
        "stored_basis": "atom_counts (pre-normalized cation proportions)",
        "fe_convention": "FeO (total Fe)", "f_cl_s": "F/Cl as element wt%",
        "oxygen": "not reported; masked", "omitted": "trace elements outside the element set",
    },
    "standard": {
        "source": "Standards.xlsx `Compiled` sheet (GeoReM), units row 'wt%'",
        "units": "oxide wt%", "conversion": "same as measured",
        "stored_basis": "atom_counts (pre-normalized cation proportions)",
        "fe_convention": "FeO (total Fe)", "f_cl_s": "F/Cl as element wt%",
        "oxygen": "not reported; masked",
    },
}


def _basis_note(name: str) -> str:
    if "(measured)" in name:
        return "measured EPMA oxide wt% -> cation proportions (see V2 audit)"
    if name.startswith("Glass std ") or name.startswith("Std "):
        return "GeoReM standard oxide wt% -> cation proportions (see V2 audit)"
    return "idealised stoichiometric atom counts"


_MINERALS_V2 = tuple(
    MineralEndmember(
        name, family, formula, None,
        f"{_provenance_for(name)} | basis-audited V2: {_basis_note(name)}",
        basis="atom_counts",
    )
    for name, family, formula in _RAW_MINERALS
)

MINERALOGY_DEFAULT_V2 = MineralogyReference(
    name="minerals_default_v2",
    version="2",
    description="Basis-audited silicate/oxide mineralogy reference (44 endmembers, "
    "explicit atom_counts basis on every entry; O/Br/I excluded at match).",
    elements=_ELEMENTS_V2,
    minerals=_MINERALS_V2,
    structural_exclude=frozenset({"O", "Br", "I"}),
    family_display=_FAMILY_DISPLAY,
)
MINERALOGY_DEFAULT_V2.validate(strict=True)

__all__ = ["MINERALOGY_DEFAULT_V2", "MINERALOGY_V2_BASIS_AUDIT"]
