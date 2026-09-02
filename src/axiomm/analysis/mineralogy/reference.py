"""Mineralogy reference library — the science every mineralogy tool reads.

The reference owns the structural exclusion of O/Br/I and the
construction of normalized cation vectors, so downstream tools (S3c/S3d)
consume vectors rather than re-deriving them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.reference import ReferenceLibrary


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
    """A named mineral endmember with a cation composition and family."""

    name: str
    family: str
    composition: Mapping[str, float]
    family_element_weights: Mapping[str, float] | None
    provenance: str


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

    def validate(self) -> None:
        """Raise :class:`PayloadValidationError` on a malformed reference."""
        for sym in self.structural_exclude:
            if sym not in self.elements:
                raise PayloadValidationError(
                    f"structural_exclude symbol {sym!r} is not a known element."
                )
        for sym, el in self.elements.items():
            if el.line_energy_kev <= 0:
                raise PayloadValidationError(
                    f"element {sym!r} has non-positive line_energy_kev {el.line_energy_kev}."
                )
            if el.atomic_weight <= 0:
                raise PayloadValidationError(
                    f"element {sym!r} has non-positive atomic_weight {el.atomic_weight}."
                )
            if el.emission_line not in ("Ka", "La"):
                raise PayloadValidationError(
                    f"element {sym!r} has invalid emission_line "
                    f"{el.emission_line!r} (expected 'Ka' or 'La')."
                )
        for mineral in self.minerals:
            if mineral.family not in self.family_display:
                raise PayloadValidationError(
                    f"mineral {mineral.name!r} family {mineral.family!r} has no "
                    f"family_display entry."
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


__all__ = ["ElementRef", "MineralEndmember", "MineralogyReference"]
