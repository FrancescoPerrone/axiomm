"""Quantification result payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from axiomm.analysis.models import AnalysisProvenance, Diagnostic


@dataclass
class KFactorSet:
    """Theoretical Cliff-Lorimer k-factors relative to a reference element."""

    k_factors: Mapping[str, float]        # k_{i,ref} per element symbol
    sensitivities: Mapping[str, float]    # S_i (cm^2/g)
    reference_element: str
    excitation_kev: float
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class QuantResult:
    """Cliff-Lorimer element + oxide weight percents for one spectrum."""

    net_intensities: Mapping[str, float]
    wt_percent_element: Mapping[str, float]   # metals / cation basis
    wt_percent_oxide: Mapping[str, float]
    reference_element: str
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


__all__ = ["KFactorSet", "QuantResult"]
