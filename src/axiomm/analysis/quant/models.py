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
#: ``not_measured`` — a window was available but no peak was recorded for this element;
#: ``not_excited`` — the element's absorption edge is above every supplied excitation
#:     energy, so it *physically cannot* fluoresce here (a coverage reason, not an absence);
#: ``out_of_coverage`` — the element is excited, but its line falls outside the measured
#:     spectral window of the map that would measure it (an acquisition reason);
#: ``invalid`` — the measurement was non-finite/incoherent.
#: The last two (``not_excited`` / ``out_of_coverage``) describe elements with no measurement
#: at all, so — unlike the others — their keys need not appear in ``net_intensities``.
OBSERVATION_STATUSES: frozenset[str] = frozenset(
    {"measured_positive", "measured_zero", "not_measured",
     "not_excited", "out_of_coverage", "invalid"}
)

#: Statuses that describe an element with NO measurement (no net intensity entry).
NO_MEASUREMENT_STATUSES: frozenset[str] = frozenset({"not_excited", "out_of_coverage"})


__all__ = ["NO_MEASUREMENT_STATUSES", "OBSERVATION_STATUSES", "KFactorSet", "QuantResult"]
