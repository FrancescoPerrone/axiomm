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


def _covers(coverage, energy: float, line_kev: float) -> bool:
    """Does the ``energy`` acquisition's spectral window include ``line_kev``?
    ``coverage`` maps ``energy -> (emin_kev, emax_kev)``; ``None`` assumes every
    excited acquisition covers the line (the single-energy / unit-test case)."""
    if coverage is None:
        return True
    rng = coverage.get(energy)
    return rng is not None and rng[0] <= line_kev <= rng[1]


def select_energies(group, element_refs, *, policy=None, edge_energy=None, coverage=None):
    """Choose each element's source energy across ``group`` by **joint eligibility**.

    An acquisition is *eligible* for an element only when it BOTH excites it (energy
    above the absorption edge) AND covers its line (the line falls within that map's
    spectral window). The policy ranks **only among eligible acquisitions**, so a
    preferred-but-uncovered source falls back to the next eligible one rather than
    discarding a measurable alternative. Physical eligibility is a non-configurable
    gate here; the policy decides ranking, not whether a source is usable.

    ``group`` is a :class:`MultiEnergyMapGroup` (or a bare iterable of energies).
    ``policy`` is a name or a policy instance (default ``best_excited``). ``edge_energy``
    overrides the xraylib edge lookup. ``coverage`` maps ``energy -> (emin_kev, emax_kev)``;
    ``None`` assumes full coverage (used where only one map, or no axis, is in play).

    Returns ``({symbol: chosen eligible energy or None}, {symbol: reason}, diagnostics)``
    where ``reason`` is ``not_excited`` (no acquisition excites) or ``out_of_coverage``
    (excited by >=1 acquisition, but none of those cover the line) for every element with
    no eligible source; eligible elements are absent from ``reasons``.
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
    energies = sorted(float(e) for e in
                      (group.energies() if hasattr(group, "energies") else group))
    chosen: dict = {}
    reasons: dict = {}
    diagnostics: list[Diagnostic] = []
    for ref in element_refs:
        edge_kev = float(edge(ref))
        excited = [e for e in energies if e > edge_kev]
        if not excited:
            chosen[ref.symbol] = None
            reasons[ref.symbol] = "not_excited"
            diagnostics.append(Diagnostic(
                "warning", "not_excited",
                f"{ref.symbol} absorption edge {edge_kev:.3f} keV is above every supplied "
                f"energy {energies}; it cannot be measured by this group."))
            continue
        eligible = [e for e in excited if _covers(coverage, e, float(ref.line_energy_kev))]
        if not eligible:
            chosen[ref.symbol] = None
            reasons[ref.symbol] = "out_of_coverage"
            diagnostics.append(Diagnostic(
                "warning", "out_of_coverage",
                f"{ref.symbol} is excited (edge {edge_kev:.3f} keV) but its line "
                f"{float(ref.line_energy_kev):.3f} keV is outside the spectral window of every "
                "exciting acquisition; no eligible source."))
            continue
        # The policy ranks among ELIGIBLE acquisitions only (fallback is automatic).
        sub, _ = policy.select([ref], eligible, edge)
        pick = sub[ref.symbol]
        chosen[ref.symbol] = pick if pick in eligible else min(eligible)
    return chosen, reasons, diagnostics


__all__ = [
    "BestExcitedPolicy",
    "EnergySelectionPolicy",
    "element_edge_kev",
    "energy_selectors",
    "select_energies",
]
