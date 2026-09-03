"""Exception hierarchy for the AXIOMM analysis-tool suite.

Rooted at :class:`AxiommAnalysisError`, mirroring
:class:`axiomm.io.converters.errors.AxiommConverterError`. Public
functions in the analysis suite raise a named subclass of this base —
never a bare :class:`Exception`.
"""

from __future__ import annotations


class AxiommAnalysisError(Exception):
    """Base class for every error raised by the analysis suite."""


class BackendNotFoundError(AxiommAnalysisError):
    """Raised when a named backend is not registered in a registry."""


class PayloadValidationError(AxiommAnalysisError):
    """Raised when a result payload fails a required-field or shape check."""


class PayloadSerializationError(PayloadValidationError):
    """Raised when a persisted payload is malformed, incompatible, or corrupt.

    Covers everything a *reader* rejects beyond well-formed JSON: an
    unsupported ``schema_version``, a wrong payload ``kind``, missing or
    mistyped fields, non-finite numbers, out-of-range values, or an
    unrecognised status vocabulary. A subclass of
    :class:`PayloadValidationError` (a corrupt file is a failed validation),
    so callers catching either type still catch it, while ``except
    PayloadSerializationError`` isolates the persistence layer specifically.
    """


class ReferenceLibraryError(AxiommAnalysisError):
    """Raised for missing or malformed reference libraries."""


class OutputExistsError(AxiommAnalysisError):
    """Raised when writing would overwrite an existing output without opt-in."""


class AnalysisDependencyError(AxiommAnalysisError):
    """Raised when an optional dependency required for an operation is absent."""


__all__ = [
    "AnalysisDependencyError",
    "AxiommAnalysisError",
    "BackendNotFoundError",
    "OutputExistsError",
    "PayloadSerializationError",
    "PayloadValidationError",
    "ReferenceLibraryError",
]
