"""Reference-library scaffolding for the analysis suite.

A :class:`ReferenceLibrary` is a named, versioned bundle of scientific
constants (element line energies, atomic weights, mineral definitions,
...) supplied to tools as swappable configuration rather than hidden
magic numbers — the analysis-side analogue of the converter's
calibration presets. Concrete libraries subclass this and register
themselves in the default :data:`references` registry; the MELTS
mineralogy library lands in S3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from axiomm.analysis.registry import Factory, Registry


@dataclass(frozen=True)
class ReferenceLibrary:
    """Base for a named, versioned reference-data bundle."""

    name: str
    version: str
    description: str = ""


#: Default registry of reference libraries. Populated by concrete
#: libraries (e.g. mineralogy in S3); empty at S0.
references: Registry = Registry("reference library")


def register_reference(name: str, factory: Factory) -> None:
    """Register a reference-library factory in the default registry."""
    references.register(name, factory)


def get_reference(name: str) -> Any:
    """Return the reference library registered under ``name``."""
    return references.get(name)


__all__ = [
    "ReferenceLibrary",
    "get_reference",
    "references",
    "register_reference",
]
