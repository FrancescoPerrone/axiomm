"""Settings for :class:`axiomm.pipeline.Pipeline` — plainly named, validated.

The names read as plain English on purpose: ``groups`` (how many mineral groups
to look for), ``components`` (how much spectral detail to keep), ``reference``
(which mineral library), ``beam_energy_kev`` (the acquisition beam energy —
required before quantification/matching can run, never assumed), and ``seed``
(for reproducible runs). Power users can still pass the underlying
``MatchConfig`` / ``ReliabilityConfig`` objects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from axiomm.analysis.errors import PayloadValidationError


def _pos_int(value, name: str) -> None:
    if not (isinstance(value, int) and not isinstance(value, bool) and value >= 1):
        raise PayloadValidationError(f"Pipeline {name} must be an integer >= 1; got {value!r}.")


def _check_stage(field_name: str, spec, method: str) -> None:
    """A stage backend is ``None``, a name, a ``{'name': ...}`` dict, or an
    instance exposing ``method``. Shape only — name existence is checked at run
    time so building a config stays import-light."""
    if spec is None or isinstance(spec, str):
        return
    if isinstance(spec, dict):
        name = spec.get("name")
        if not isinstance(name, str) or not name:
            raise PayloadValidationError(
                f"Pipeline {field_name} dict must have a non-empty string 'name'; got {spec!r}.")
        return
    if hasattr(spec, method):
        return
    raise PayloadValidationError(
        f"Pipeline {field_name} must be a backend name, a {{'name': ...}} dict, or a "
        f"backend instance with a {method}() method; got {type(spec).__name__}.")


@dataclass
class PipelineConfig:
    """How a :class:`Pipeline` run behaves. All fields have sensible defaults."""

    groups: int = 8                      # number of clusters (mineral groups) to find
    components: int = 8                  # PCA components (spectral detail) to keep
    reduction: object = None             # dim-reduction backend: name / dict / instance
    clustering: object = None            # clustering backend: name / dict / instance
    reference: object = "minerals_default_v2"   # library name or a MineralogyReference
    beam_energy_kev: float | None = None        # required to quantify + match
    reference_element: str = "Si"
    seed: int = 0
    match: object = None                 # optional MatchConfig
    reliability: object = None           # optional ReliabilityConfig
    exclude_elements: frozenset[str] = frozenset()   # elements to drop from quant (e.g. a line interferent)
    line_resolution_kev: float = 0.13    # detector FWHM proxy; lines closer than this overlap
    normalize: bool = True               # divide by the payload's intensity_norm (I0/dead-time) when present
    classification: object = "family_aware"   # label policy: name / dict / ClassificationPolicy instance
    fusion_cross_cal: str = "none"             # multi-energy cross-calibration: "none" (default) or "bridge" (experimental)
    fusion_clustering: str = "primary"         # cluster on "primary" (highest-energy map, default) or "fused" (all energies, experimental)
    bridge_dispersion_limit: float = 2.0       # bridge ratios spreading wider than this (max/min) = low confidence
    bridge_low_confidence: str = "flag"        # what to do then: "flag" (apply+warn), "refuse" (scale=1+warn), "raise"
    energy_selection: object = "best_excited"  # fusion per-element energy policy: name / policy instance
    extra: dict = field(default_factory=dict)   # reserved for future settings

    def __post_init__(self) -> None:
        _pos_int(self.groups, "groups")
        _pos_int(self.components, "components")
        _check_stage("reduction", self.reduction, "decompose")
        _check_stage("clustering", self.clustering, "cluster")
        _check_stage("classification", self.classification, "classify")
        if not (isinstance(self.seed, int) and not isinstance(self.seed, bool)):
            raise PayloadValidationError(f"Pipeline seed must be an integer; got {self.seed!r}.")
        if isinstance(self.exclude_elements, str):
            # a bare string would iterate into single characters ('Ba' -> 'B','a')
            raise PayloadValidationError(
                f"Pipeline exclude_elements must be a list/set of element symbols, not a bare "
                f"string; pass e.g. ['Ba'], not {self.exclude_elements!r}.")
        if not all(isinstance(e, str) and e for e in self.exclude_elements):
            raise PayloadValidationError(
                f"Pipeline exclude_elements must be element symbols (non-empty strings); "
                f"got {self.exclude_elements!r}.")
        self.exclude_elements = frozenset(self.exclude_elements)
        lr = self.line_resolution_kev
        if not (isinstance(lr, (int, float)) and not isinstance(lr, bool)
                and math.isfinite(float(lr)) and lr >= 0):
            raise PayloadValidationError(
                f"Pipeline line_resolution_kev must be a finite number >= 0; got {lr!r}.")
        if self.beam_energy_kev is not None:
            b = self.beam_energy_kev
            if not (isinstance(b, (int, float)) and not isinstance(b, bool)
                    and math.isfinite(float(b)) and b > 0):
                raise PayloadValidationError(
                    f"Pipeline beam_energy_kev must be a finite number > 0 (or None); got {b!r}.")
        if not isinstance(self.reference_element, str) or not self.reference_element:
            raise PayloadValidationError("Pipeline reference_element must be a non-empty string.")
        if self.fusion_cross_cal not in ("bridge", "none"):
            raise PayloadValidationError(
                f"Pipeline fusion_cross_cal must be 'bridge' or 'none'; got {self.fusion_cross_cal!r}.")
        if self.fusion_clustering not in ("fused", "primary"):
            raise PayloadValidationError(
                f"Pipeline fusion_clustering must be 'fused' or 'primary'; got {self.fusion_clustering!r}.")
        dl = self.bridge_dispersion_limit
        if not (isinstance(dl, (int, float)) and not isinstance(dl, bool)
                and math.isfinite(float(dl)) and dl >= 1.0):
            raise PayloadValidationError(
                f"Pipeline bridge_dispersion_limit must be a finite number >= 1.0; got {dl!r}.")
        if self.bridge_low_confidence not in ("flag", "refuse", "raise"):
            raise PayloadValidationError(
                "Pipeline bridge_low_confidence must be 'flag', 'refuse', or 'raise'; "
                f"got {self.bridge_low_confidence!r}.")
        es = self.energy_selection
        if not (es is None or isinstance(es, str) or hasattr(es, "select")):
            raise PayloadValidationError(
                "Pipeline energy_selection must be a policy name (str) or a policy object with "
                f"a select() method; got {type(es).__name__}.")


__all__ = ["PipelineConfig"]
