"""AXIOMM analysis-tool suite (stage two).

Domain-grouped analysis tools (decomposition, clustering, mineralogy,
reporting) plus the shared substrate they build on. Importing this
package must have no side effects — no GUI windows, no ``input()``
prompts, no stdout writes. UX adapters wrap the core and are never
imported here.

S0 exports the shared foundations only; tool subpackages are added in
later chunks and lazily where they carry heavy optional dependencies.
"""

from __future__ import annotations

from axiomm.analysis import errors, models, reference, registry
from axiomm.analysis.errors import (
    AxiommAnalysisError,
    BackendNotFoundError,
    PayloadValidationError,
    ReferenceLibraryError,
)
from axiomm.analysis.models import (
    AnalysisProvenance,
    AnalysisResult,
    Diagnostic,
    Severity,
)
from axiomm.analysis.reference import (
    ReferenceLibrary,
    get_reference,
    references,
    register_reference,
)
from axiomm.analysis.registry import (
    Factory,
    Registry,
    discover_entry_points,
    load_into,
)

__all__ = [
    "AnalysisProvenance",
    "AnalysisResult",
    "AxiommAnalysisError",
    "BackendNotFoundError",
    "Diagnostic",
    "Factory",
    "PayloadValidationError",
    "ReferenceLibrary",
    "ReferenceLibraryError",
    "Registry",
    "Severity",
    "discover_entry_points",
    "errors",
    "get_reference",
    "load_into",
    "models",
    "reference",
    "references",
    "register_reference",
    "registry",
]
