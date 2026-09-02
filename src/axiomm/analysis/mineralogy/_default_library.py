"""The default mineralogy reference preset (``minerals_default_v1``).

Ported from the corrected MELTS pipeline candidates in
``refactoring_meta/`` — element X-ray/chemical data from ``cliff_lorimer.py``
and the 44 provenance-tagged endmembers + family display strings from
``hybrid_phase_pipeline.py``. Physics constants (Kα line energies, atomic
weights, atomic numbers) are universal; the endmember library is a
documented, swappable default.
"""

from __future__ import annotations

from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)

# element_symbol -> (line_energy_kev, atomic_weight, atomic_number, oxide_form)
# Ported from cliff_lorimer.py LINE_KEV / ATOMIC_WEIGHTS / Z / OXIDE_FORM.
_ELEMENT_DATA = {
    "O": (0.525, 15.999, 8, None),
    "F": (0.677, 18.998, 9, None),
    "Na": (1.041, 22.990, 11, ("Na2O", 2, 1)),
    "Mg": (1.254, 24.305, 12, ("MgO", 1, 1)),
    "Al": (1.486, 26.982, 13, ("Al2O3", 2, 3)),
    "Si": (1.740, 28.085, 14, ("SiO2", 1, 2)),
    "P": (2.013, 30.974, 15, ("P2O5", 2, 5)),
    "S": (2.307, 32.06, 16, None),
    "Cl": (2.622, 35.45, 17, None),
    "K": (3.312, 39.098, 19, ("K2O", 2, 1)),
    "Ca": (3.690, 40.078, 20, ("CaO", 1, 1)),
    "Ti": (4.508, 47.867, 22, ("TiO2", 1, 2)),
    "Cr": (5.415, 51.996, 24, ("Cr2O3", 2, 3)),
    "Mn": (5.899, 54.938, 25, ("MnO", 1, 1)),
    "Fe": (6.404, 55.845, 26, ("FeO", 1, 1)),
    "Ni": (7.478, 58.693, 28, ("NiO", 1, 1)),
    "Cu": (8.048, 63.546, 29, None),
    "Zn": (8.638, 65.38, 30, ("ZnO", 1, 1)),
    "Br": (11.924, 79.904, 35, None),
    "I": (3.940, 126.904, 53, None),
}

_ELEMENTS = {
    sym: ElementRef(sym, e, w, z, ox, "La" if sym == "I" else "Ka")
    for sym, (e, w, z, ox) in _ELEMENT_DATA.items()
}

# Per-endmember provenance, per MINERAL_LIBRARY_ADDITIONS.md: the original
# 24 are idealized stoichiometric formulae; the 20 additions are data-driven —
# 7 measured phase averages from Experiment_compositions.xlsx and 13 GeoReM
# reference values from Standards.xlsx.
_PROV_IDEAL = "Idealized stoichiometric formula"
_PROV_EXPERIMENT = "Measured phase average — Experiment_compositions.xlsx (EPMA)"
_PROV_STANDARD = "GeoReM reference value — Standards.xlsx (Compiled)"


def _provenance_for(name: str) -> str:
    if "(measured)" in name:
        return _PROV_EXPERIMENT
    if name.startswith("Glass std ") or name.startswith("Std "):
        return _PROV_STANDARD
    return _PROV_IDEAL


# (name, family, formula) ported verbatim from hybrid_phase_pipeline.py MINERAL_LIBRARY.
_RAW_MINERALS = [
    ("Quartz", "quartz_silica", {"Si": 1, "O": 2}),
    ("Albite", "feldspar", {"Na": 1, "Al": 1, "Si": 3, "O": 8}),
    ("Anorthite", "feldspar", {"Ca": 1, "Al": 2, "Si": 2, "O": 8}),
    ("Orthoclase", "feldspar", {"K": 1, "Al": 1, "Si": 3, "O": 8}),
    ("Diopside", "clinopyroxene_pyroxene", {"Ca": 1, "Mg": 1, "Si": 2, "O": 6}),
    ("Hedenbergite", "clinopyroxene_pyroxene", {"Ca": 1, "Fe": 1, "Si": 2, "O": 6}),
    ("Tremolite", "amphibole", {"Ca": 2, "Mg": 5, "Si": 8, "O": 22}),
    ("Phlogopite", "phlogopite_mica", {"K": 1, "Mg": 3, "Al": 1, "Si": 3, "O": 10, "F": 1}),
    ("Apatite", "apatite_phosphate", {"Ca": 5, "P": 3, "O": 12, "F": 1}),
    ("Cl-Apatite", "apatite_phosphate", {"Ca": 5, "P": 3, "O": 12, "Cl": 1}),
    ("Titanite", "titanite_ti_phase", {"Ca": 1, "Ti": 1, "Si": 1, "O": 5}),
    ("Rutile", "rutile_ti_oxide", {"Ti": 1, "O": 2}),
    ("Pseudobrookite", "fe_ti_oxide", {"Fe": 2, "Ti": 1, "O": 5}),
    ("Ilmenite", "fe_ti_oxide", {"Fe": 1, "Ti": 1, "O": 3}),
    ("Ulvospinel", "fe_ti_oxide", {"Fe": 2, "Ti": 1, "O": 4}),
    ("Magnetite", "fe_ti_oxide", {"Fe": 3, "O": 4}),
    ("Hematite", "fe_ti_oxide", {"Fe": 2, "O": 3}),
    ("Chromite", "spinel_chromite", {"Fe": 1, "Cr": 2, "O": 4}),
    ("Spinel", "spinel_chromite", {"Mg": 1, "Al": 2, "O": 4}),
    ("Forsterite", "clinopyroxene_pyroxene", {"Mg": 2, "Si": 1, "O": 4}),
    ("Fayalite", "clinopyroxene_pyroxene", {"Fe": 2, "Si": 1, "O": 4}),
    ("Pyrite", "sulfide", {"Fe": 1, "S": 2}),
    ("Pyrrhotite", "sulfide", {"Fe": 1, "S": 1}),
    ("Sodalite", "feldspar", {"Na": 8, "Al": 6, "Si": 6, "O": 24, "Cl": 2}),
    ("Apatite (measured)", "apatite_phosphate", {"Mg": 0.8, "Si": 0.5, "P": 35.1, "Ca": 57.5, "F": 5.4}),
    ("Rutile (measured)", "rutile_ti_oxide", {"Ti": 96.9, "Cr": 0.6, "Fe": 1.9}),
    ("Phlogopite (measured)", "phlogopite_mica", {"Mg": 29.4, "Al": 11.2, "Si": 36.5, "K": 11.4, "Ti": 2.9, "Fe": 3.7, "F": 4.3}),
    ("Silicate glass (measured)", "glass_melt", {"Na": 6.1, "Mg": 2.9, "Al": 12.1, "Si": 60.9, "P": 0.5, "K": 9.4, "Ca": 2.0, "Ti": 1.5, "Fe": 3.5, "Ba": 0.6}),
    ("Clinopyroxene (measured)", "clinopyroxene_pyroxene", {"Mg": 24.7, "Al": 0.5, "Si": 49.5, "Ca": 20.9, "Fe": 2.9}),
    ("Amphibole (measured)", "amphibole", {"Na": 5.1, "Mg": 22.6, "Al": 8.4, "Si": 41.9, "K": 2.6, "Ca": 10.1, "Ti": 1.8, "Fe": 6.0, "F": 1.4}),
    ("Titanomagnetite (measured)", "fe_ti_oxide", {"Mg": 6.4, "Al": 2.6, "Ti": 22.8, "Cr": 1.0, "Mn": 0.5, "Fe": 66.3}),
    ("Glass std GSE-1G", "glass_melt", {"Si": 51.8, "Al": 14.8, "Fe": 10.2, "Mg": 5.0, "Ca": 7.6, "Na": 7.3, "K": 3.2}),
    ("Glass std GSD-1G", "glass_melt", {"Si": 51.2, "Al": 15.2, "Fe": 10.7, "Mg": 5.2, "Ca": 7.4, "Na": 6.7, "K": 3.7}),
    ("Glass std GOR128-G", "glass_melt", {"Si": 21.7, "Al": 5.5, "Fe": 3.9, "Mg": 18.3, "Ca": 3.1, "Na": 0.5, "F": 37.2, "Cl": 9.6}),
    ("Glass std BHVO-2G", "glass_melt", {"Si": 46.8, "Al": 15.2, "Fe": 9.0, "Mg": 10.1, "Ca": 11.6, "Na": 4.4, "K": 0.6, "Ti": 2.0}),
    ("Glass std BCR-2G", "glass_melt", {"Si": 52.3, "Al": 15.2, "Fe": 10.0, "Mg": 5.1, "Ca": 7.3, "Na": 6.0, "K": 2.1, "Ti": 1.6}),
    ("Glass std BB1", "glass_melt", {"Si": 48.6, "Al": 22.6, "Ca": 6.5, "Na": 16.0, "K": 1.6, "Cl": 4.6}),
    ("Glass std SP", "glass_melt", {"Si": 48.9, "Al": 19.7, "Ca": 1.6, "Na": 22.4, "K": 1.3, "Cl": 6.1}),
    ("Std UGY(mica)", "phlogopite_mica", {"Si": 36.5, "Ti": 1.4, "Al": 14.8, "Fe": 6.2, "Mg": 27.9, "Na": 0.5, "K": 12.3}),
    ("Std BFS-AMP(amph)", "amphibole", {"Si": 41.7, "Ti": 0.8, "Al": 11.9, "Fe": 15.2, "Mg": 13.7, "Ca": 12.1, "Na": 2.6, "K": 1.7}),
    ("Std BFS-AP(apatite)", "apatite_phosphate", {"Ca": 56.0, "P": 34.0, "F": 9.5}),
    ("Std DAP(apatite)", "apatite_phosphate", {"Ca": 54.1, "P": 32.8, "F": 12.4}),
    ("Std MDAP(apatite)", "apatite_phosphate", {"Ca": 57.3, "P": 35.5, "F": 6.7}),
    ("Std ODAP(apatite)", "apatite_phosphate", {"Mg": 0.5, "Ca": 59.2, "Na": 1.0, "P": 38.4, "F": 0.5}),
]

_MINERALS = tuple(
    MineralEndmember(name, family, formula, None, _provenance_for(name))
    for name, family, formula in _RAW_MINERALS
)

# Ported verbatim from hybrid_phase_pipeline.py FAMILY_DISPLAY.
_FAMILY_DISPLAY = {
    "apatite_phosphate": "Ca-phosphate (apatite family)",
    "phlogopite_mica": "Mica (phlogopite family)",
    "clinopyroxene_pyroxene": "Pyroxene / mafic silicate",
    "amphibole": "Amphibole",
    "quartz_silica": "Silica / quartz-family",
    "feldspar": "Feldspar / feldspathoid",
    "glass_melt": "Glass / mixed silicate melt",
    "titanite_ti_phase": "Titanite (Ca-Ti silicate)",
    "rutile_ti_oxide": "Ti oxide (rutile family)",
    "fe_ti_oxide": "Fe-Ti oxide",
    "spinel_chromite": "Spinel / chromite",
    "sulfide": "Sulfide",
    "unknown_mixed": "Mixed / unresolved",
    "artifact_void_crack": "Artifact / crack / void",
}

MINERALOGY_DEFAULT_V1 = MineralogyReference(
    name="minerals_default_v1",
    version="1",
    description="Default silicate/oxide mineralogy reference ported from the "
    "corrected MELTS pipeline (44 endmembers, O-excluded matching).",
    elements=_ELEMENTS,
    minerals=_MINERALS,
    structural_exclude=frozenset({"O", "Br", "I"}),
    family_display=_FAMILY_DISPLAY,
)
MINERALOGY_DEFAULT_V1.validate()

__all__ = ["MINERALOGY_DEFAULT_V1"]
