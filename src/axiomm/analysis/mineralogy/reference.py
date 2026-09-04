"""Mineralogy reference library — the science every mineralogy tool reads.

The reference owns the structural exclusion of O/Br/I and the
construction of normalized cation vectors, so downstream tools (S3c/S3d)
consume vectors rather than re-deriving them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.reference import ReferenceLibrary

#: Recognised compositional bases an endmember's ``composition`` may be in.
#: ``atom_counts`` — stoichiometric atom counts or pre-normalised cation
#: proportions (both normalise to molar/element fractions). ``element_mass_fraction``
#: — elemental wt%. ``oxide_mass_fraction`` — oxide wt% (converted with each
#: oxide's molecular mass and stoichiometry, F/S/Cl treated as element wt%).
#: ``None`` marks a legacy, basis-unaudited endmember that the S3d matcher
#: refuses unless the caller explicitly opts in.
COMPOSITION_BASES: frozenset[str] = frozenset(
    {"atom_counts", "element_mass_fraction", "oxide_mass_fraction"}
)


@dataclass(frozen=True)
class ElementRef:
    """Per-element X-ray + chemical data."""

    symbol: str
    line_energy_kev: float
    atomic_weight: float
    atomic_number: int
    oxide_form: tuple[str, int, int] | None  # (oxide_name, n_cation, n_O); None = element
    emission_line: str = "Ka"                # "Ka" or "La" — detected characteristic line


@dataclass(frozen=True)
class MineralEndmember:
    """A named mineral endmember with a composition, family, and declared basis.

    ``basis`` names the compositional basis of ``composition`` (see
    :data:`COMPOSITION_BASES`); ``None`` (the default, for legacy V1 entries)
    means the basis was never audited, and the S3d matcher rejects such an
    endmember unless the caller explicitly opts in.
    """

    name: str
    family: str
    composition: Mapping[str, float]
    family_element_weights: Mapping[str, float] | None
    provenance: str
    basis: str | None = None


@dataclass(frozen=True, kw_only=True)
class MineralogyReference(ReferenceLibrary):
    """A named, versioned mineralogy reference bundle.

    The four fields below are keyword-only so they can follow
    :class:`ReferenceLibrary`'s ``description`` default without a dataclass
    field-ordering error.
    """

    elements: Mapping[str, ElementRef]
    minerals: tuple[MineralEndmember, ...]
    structural_exclude: frozenset[str]
    family_display: Mapping[str, str]

    def element_order(self) -> tuple[str, ...]:
        """Stable element ordering used for vector construction."""
        return tuple(self.elements.keys())

    def validate(self, *, strict: bool = False) -> None:
        """Raise :class:`PayloadValidationError` on a malformed reference.

        ``strict=True`` additionally enforces the basis-audit invariants used
        by the S3d matcher: a known, non-``None`` basis on every endmember;
        finite, positive atomic weights/line energies and valid atomic numbers;
        finite, non-negative composition values with no duplicate/unknown
        element keys; unique, non-empty mineral names; and a non-degenerate
        (non-zero over included elements) composition. The lenient default is
        kept for the legacy V1 preset.
        """
        for sym in self.structural_exclude:
            if sym not in self.elements:
                raise PayloadValidationError(
                    f"structural_exclude symbol {sym!r} is not a known element."
                )
        for sym, el in self.elements.items():
            if not (math.isfinite(el.line_energy_kev) and el.line_energy_kev > 0):
                raise PayloadValidationError(
                    f"element {sym!r} has non-positive/non-finite line_energy_kev {el.line_energy_kev}."
                )
            if not (math.isfinite(el.atomic_weight) and el.atomic_weight > 0):
                raise PayloadValidationError(
                    f"element {sym!r} has non-positive/non-finite atomic_weight {el.atomic_weight}."
                )
            if el.emission_line not in ("Ka", "La"):
                raise PayloadValidationError(
                    f"element {sym!r} has invalid emission_line "
                    f"{el.emission_line!r} (expected 'Ka' or 'La')."
                )
            if strict and not (isinstance(el.atomic_number, int) and el.atomic_number > 0):
                raise PayloadValidationError(
                    f"element {sym!r} has invalid atomic_number {el.atomic_number}."
                )
        seen_names: set[str] = set()
        for mineral in self.minerals:
            if mineral.family not in self.family_display:
                raise PayloadValidationError(
                    f"mineral {mineral.name!r} family {mineral.family!r} has no "
                    f"family_display entry."
                )
            if not strict:
                continue
            if not mineral.name:
                raise PayloadValidationError("a mineral endmember has an empty name.")
            if mineral.name in seen_names:
                raise PayloadValidationError(f"duplicate mineral name {mineral.name!r}.")
            seen_names.add(mineral.name)
            if mineral.basis not in COMPOSITION_BASES:
                raise PayloadValidationError(
                    f"mineral {mineral.name!r} has unknown/unaudited basis "
                    f"{mineral.basis!r} (expected one of {sorted(COMPOSITION_BASES)})."
                )
            included_total = 0.0
            for el_sym, value in mineral.composition.items():
                if el_sym not in self.elements:
                    raise PayloadValidationError(
                        f"mineral {mineral.name!r} composition element {el_sym!r} "
                        "is not in the reference element set."
                    )
                if not (math.isfinite(value) and value >= 0):
                    raise PayloadValidationError(
                        f"mineral {mineral.name!r} composition value for {el_sym!r} "
                        f"must be finite and >= 0; got {value!r}."
                    )
                if el_sym not in self.structural_exclude:
                    included_total += float(value)
            if included_total <= 0:
                raise PayloadValidationError(
                    f"mineral {mineral.name!r} has a degenerate composition "
                    "(zero over included elements)."
                )

    def build_vectors_with_diagnostics(
        self, minerals: tuple[MineralEndmember, ...]
    ) -> tuple[list[tuple[str, np.ndarray]], list[Diagnostic]]:
        """Build normalized, O/Br/I-excluded cation vectors + diagnostics.

        Elements outside the element set are dropped (with a diagnostic),
        matching the reference implementation's tolerance of trace
        elements.
        """
        order = self.element_order()
        index = {sym: i for i, sym in enumerate(order)}
        vectors: list[tuple[str, np.ndarray]] = []
        diagnostics: list[Diagnostic] = []
        for mineral in minerals:
            vec = np.zeros(len(order), dtype=float)
            for sym, count in mineral.composition.items():
                if sym not in index:
                    diagnostics.append(
                        Diagnostic(
                            "info",
                            "unknown_composition_element",
                            f"{mineral.name!r} composition element {sym!r} is not in "
                            f"the element set; dropped from its vector.",
                        )
                    )
                    continue
                if sym in self.structural_exclude:
                    continue
                vec[index[sym]] += float(count)
            total = vec.sum()
            if total > 0:
                vec = vec / total
            vectors.append((mineral.name, vec))
        return vectors, diagnostics

    def mineral_vectors(self) -> tuple[tuple[str, np.ndarray], ...]:
        """Normalized O/Br/I-excluded cation vectors for every endmember."""
        vectors, _ = self.build_vectors_with_diagnostics(self.minerals)
        return tuple(vectors)


__all__ = ["COMPOSITION_BASES", "ElementRef", "MineralEndmember", "MineralogyReference"]
