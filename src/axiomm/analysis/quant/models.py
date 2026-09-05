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

    ``observation_status`` records, per element, *how* it was observed — one of
    :data:`OBSERVATION_STATUSES` — so downstream tools never infer that an
    element was unobserved merely because its wt% is zero. It is empty when the
    result was constructed without measurement facts (e.g. by hand); consumers
    must then treat observation as unknown rather than invent a status.
    """

    net_intensities: Mapping[str, float]
    wt_percent_element: Mapping[str, float]   # metals / cation basis
    wt_percent_oxide: Mapping[str, float]
    reference_element: str
    gross_intensities: Mapping[str, float] = field(default_factory=dict)
    background_per_channel: Mapping[str, float] = field(default_factory=dict)
    window_channels: Mapping[str, int] = field(default_factory=dict)
    observation_status: Mapping[str, str] = field(default_factory=dict)
    cluster_id: int | None = None
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


#: How an element was observed, from the retained measurement facts.
#: ``measured_positive`` — a peak was measured with net > 0;
#: ``measured_zero`` — a peak was measured with net <= 0 (looked, saw nothing);
#: ``not_measured`` — no peak/window for this element;
#: ``invalid`` — the measurement was non-finite/incoherent.
OBSERVATION_STATUSES: frozenset[str] = frozenset(
    {"measured_positive", "measured_zero", "not_measured", "invalid"}
)


__all__ = ["OBSERVATION_STATUSES", "KFactorSet", "QuantResult"]
