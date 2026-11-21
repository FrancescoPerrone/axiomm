"""Per-element energy selection for multi-energy fusion (stage two, S8.2).

For each element to quantify, choose which map's excitation energy measures it
best. The rule is a **pluggable policy** (same socket as `reduction=` /
`clustering=`); the default :class:`BestExcitedPolicy` picks the lowest supplied
energy *above* the element's absorption edge, where fluorescence efficiency is
highest. An element excited by no supplied energy is reported ``not_excited`` (a
diagnostic), never fabricated.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from axiomm.analysis.errors import AnalysisDependencyError, PayloadValidationError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.registry import Registry


def element_edge_kev(ref) -> float:
    """Absorption-edge energy (keV) for an element's measured line — K for a
    ``Ka`` line, L3 for ``La``. Needs xraylib (the k-factor dependency)."""
    try:
        import xraylib
    except ImportError as exc:  # pragma: no cover - exercised where xraylib is absent
        raise AnalysisDependencyError(
            "xraylib is required for energy selection (absorption-edge energies).") from exc
    line = str(getattr(ref, "emission_line", "Ka"))
    shell = xraylib.K_SHELL if line.upper().startswith("K") else xraylib.L3_SHELL
    return float(xraylib.EdgeEnergy(int(ref.atomic_number), shell))


class EnergySelectionPolicy(ABC):
    """Chooses, per element, which map's energy measures it best."""

    name: ClassVar[str] = "policy"

    @abstractmethod
    def select(self, element_refs, energies, edge_energy):
        """Return ``({symbol: chosen excitation_kev or None}, diagnostics)``."""

    def params(self) -> dict:
        return {"policy": self.name}


@dataclass(frozen=True)
class BestExcitedPolicy(EnergySelectionPolicy):
    """Pick the lowest supplied energy above the element's absorption edge.

    Fluorescence efficiency peaks just above the edge and falls as the excitation
    energy rises, so the lowest supplied energy that still exceeds the edge is the
    best exciter. An element whose edge is above every supplied energy is
    ``not_excited``.
    """

    name: ClassVar[str] = "best_excited"

    def select(self, element_refs, energies, edge_energy):
        energies = sorted(float(e) for e in energies)
        chosen: dict = {}
        diagnostics: list[Diagnostic] = []
        for ref in element_refs:
            edge = float(edge_energy(ref))
            above = [e for e in energies if e > edge]
            if above:
                chosen[ref.symbol] = above[0]
            else:
                chosen[ref.symbol] = None
                diagnostics.append(Diagnostic(
                    "warning", "not_excited",
                    f"{ref.symbol} absorption edge {edge:.3f} keV is above every supplied "
                    f"energy {energies}; it cannot be measured by this group."))
        return chosen, diagnostics


#: Pluggable energy-selection backends (name -> instance).
energy_selectors: Registry = Registry("energy selector")
energy_selectors.register("best_excited", lambda: BestExcitedPolicy())


def select_energies(group, element_refs, *, policy=None, edge_energy=None):
    """Choose each element's best-excited energy across ``group``.

    ``group`` is a :class:`MultiEnergyMapGroup` (or a bare iterable of energies).
    ``policy`` is a name or a policy instance (default ``best_excited``);
    ``edge_energy`` overrides the xraylib edge lookup (tests / alternative
    sources). Returns ``({symbol: excitation_kev or None}, diagnostics)``.
    """
    if policy is None:
        policy = BestExcitedPolicy()
    elif isinstance(policy, str):
        policy = energy_selectors.get(policy)
    elif not hasattr(policy, "select"):
        raise PayloadValidationError(
            f"energy-selection policy must be a name or a policy with select(); "
            f"got {type(policy).__name__}.")
    edge = edge_energy or element_edge_kev
    energies = group.energies() if hasattr(group, "energies") else tuple(group)
    return policy.select(list(element_refs), energies, edge)


__all__ = [
    "BestExcitedPolicy",
    "EnergySelectionPolicy",
    "element_edge_kev",
    "energy_selectors",
    "select_energies",
]
