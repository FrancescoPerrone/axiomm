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


@dataclass
class PipelineConfig:
    """How a :class:`Pipeline` run behaves. All fields have sensible defaults."""

    groups: int = 8                      # number of clusters (mineral groups) to find
    components: int = 8                  # PCA components (spectral detail) to keep
    reference: object = "minerals_default_v2"   # library name or a MineralogyReference
    beam_energy_kev: float | None = None        # required to quantify + match
    reference_element: str = "Si"
    seed: int = 0
    match: object = None                 # optional MatchConfig
    reliability: object = None           # optional ReliabilityConfig
    extra: dict = field(default_factory=dict)   # reserved for future settings

    def __post_init__(self) -> None:
        _pos_int(self.groups, "groups")
        _pos_int(self.components, "components")
        if not (isinstance(self.seed, int) and not isinstance(self.seed, bool)):
            raise PayloadValidationError(f"Pipeline seed must be an integer; got {self.seed!r}.")
        if self.beam_energy_kev is not None:
            b = self.beam_energy_kev
            if not (isinstance(b, (int, float)) and not isinstance(b, bool)
                    and math.isfinite(float(b)) and b > 0):
                raise PayloadValidationError(
                    f"Pipeline beam_energy_kev must be a finite number > 0 (or None); got {b!r}.")
        if not isinstance(self.reference_element, str) or not self.reference_element:
            raise PayloadValidationError("Pipeline reference_element must be a non-empty string.")


__all__ = ["PipelineConfig"]
