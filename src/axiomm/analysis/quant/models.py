"""Quantification result payloads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

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
    """Uncorrected theoretical sensitivity-ratio element + oxide wt% estimate.

    These weight percents apply theoretical fluorescence-cross-section
    ratios only (see :mod:`axiomm.analysis.quant.kfactors`); they are an
    uncorrected estimate, not a validated quantitative composition.

    ``gross_intensities`` / ``background_per_channel`` / ``window_channels``
    carry the raw peak facts so a later statistically defined LOD/LOQ can
    be computed from gross counts, background and window width.
    """

    net_intensities: Mapping[str, float]
    wt_percent_element: Mapping[str, float]   # metals / cation basis
    wt_percent_oxide: Mapping[str, float]
    reference_element: str
    gross_intensities: Mapping[str, float] = field(default_factory=dict)
    background_per_channel: Mapping[str, float] = field(default_factory=dict)
    window_channels: Mapping[str, int] = field(default_factory=dict)
    cluster_id: int | None = None
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


__all__ = ["KFactorSet", "QuantResult"]
