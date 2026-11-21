"""The N-energy map group for multi-energy fusion (stage two, S8).

A :class:`MultiEnergyMapGroup` is an ordered set of energy-tagged maps of the
**same spatial region**, acquired at different excitation energies so each
element can be measured from the energy that best excites it. Each member is an
ordinary :class:`~axiomm.io.converters.models.AxiommSignalPayload`, so every
reader/format works. The group is constructed **explicitly** by the user —
AXIOMM never infers it from filenames — and a single-member group is valid
(fusion is then the identity).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from axiomm.analysis.errors import PayloadValidationError


def _is_pos_number(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0)


@dataclass(frozen=True)
class EnergyMap:
    """One energy-tagged map: an excitation energy (keV) and its payload."""

    excitation_kev: float
    payload: Any

    def __post_init__(self) -> None:
        if not _is_pos_number(self.excitation_kev):
            raise PayloadValidationError(
                f"EnergyMap excitation_kev must be a finite number > 0; "
                f"got {self.excitation_kev!r}.")
        if not (hasattr(self.payload, "axes") and hasattr(self.payload, "data")):
            raise PayloadValidationError(
                "EnergyMap payload must be an AxiommSignalPayload (with .axes and .data).")
        object.__setattr__(self, "excitation_kev", float(self.excitation_kev))


@dataclass(frozen=True)
class MultiEnergyMapGroup:
    """An ordered set of co-registered maps of one region at different energies."""

    maps: tuple[EnergyMap, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "maps", tuple(self.maps))
        if not self.maps:
            raise PayloadValidationError("MultiEnergyMapGroup needs at least one EnergyMap.")
        for m in self.maps:
            if not isinstance(m, EnergyMap):
                raise PayloadValidationError(
                    f"MultiEnergyMapGroup members must be EnergyMap; got {type(m).__name__}.")

    @classmethod
    def from_pairs(cls, pairs) -> MultiEnergyMapGroup:
        """Build from ``[(excitation_kev, payload), ...]`` — the ergonomic constructor."""
        return cls(tuple(EnergyMap(kev, payload) for kev, payload in pairs))

    def energies(self) -> tuple[float, ...]:
        return tuple(m.excitation_kev for m in self.maps)

    def __len__(self) -> int:
        return len(self.maps)

    def __iter__(self):
        return iter(self.maps)


__all__ = ["EnergyMap", "MultiEnergyMapGroup"]
