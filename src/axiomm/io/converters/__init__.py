"""AXIOMM converter package.

This package provides format-agnostic conversion of scientific datasets into
analysis-ready signal objects. The four core components are decomposed into
sub-packages:

* :mod:`axiomm.io.converters.readers`  — format-specific readers.
* :mod:`axiomm.io.converters.signals`  — neutral-to-backend signal builders.
* :mod:`axiomm.io.converters.writers`  — output writers.

A neutral in-memory representation lives in :mod:`axiomm.io.converters.models`
and the exception hierarchy in :mod:`axiomm.io.converters.errors`.

Importing this package must have no side effects — no GUI windows, no
``input()`` prompts, no stdout writes. UX adapters (CLI, notebook helpers,
Tk dialogs) live separately and wrap the core; they are never imported here.
"""

from __future__ import annotations

from axiomm.io.converters import errors, models
from axiomm.io.converters.discovery import discover_inputs
from axiomm.io.converters.errors import (
    AxiommConverterError,
    ConversionWorkflowError,
    DatasetNotFoundError,
    InputDiscoveryError,
    MetadataParseError,
    OutputExistsError,
    ReaderDetectionError,
    SignalValidationError,
    UnsupportedFormatError,
)
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    ConversionResult,
    Diagnostic,
    SourceProvenance,
)
from axiomm.io.converters.readers.base import Reader
from axiomm.io.converters.signals.base import SignalBuilder
from axiomm.io.converters.writers.base import Writer

__all__ = [
    # subpackages re-exported for discoverability
    "errors",
    "models",
    # exception hierarchy
    "AxiommConverterError",
    "ConversionWorkflowError",
    "DatasetNotFoundError",
    "InputDiscoveryError",
    "MetadataParseError",
    "OutputExistsError",
    "ReaderDetectionError",
    "SignalValidationError",
    "UnsupportedFormatError",
    # data model
    "AxisSpec",
    "AxiommSignalPayload",
    "ConversionResult",
    "Diagnostic",
    "SourceProvenance",
    # protocols
    "Reader",
    "SignalBuilder",
    "Writer",
    # discovery
    "discover_inputs",
    # validation
    "validate_axes",
    # concrete readers + builders (lazily imported — see __getattr__ below)
    "XRMMapH5Config",
    "XRMMapH5Reader",
    "HyperSpyBuilder",
    "build_hyperspy_signal",
]


# Re-export validate_axes eagerly: it has no heavy deps.
from axiomm.io.converters.signals.validation import validate_axes  # noqa: E402


# Lazy attribute imports (PEP 562). Concrete readers, builders and writers
# may carry optional runtime dependencies (h5py, hyperspy, …). Importing
# the converters package must stay light, so we only pull these in when
# user code actually touches the name.

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "XRMMapH5Reader": (
        "axiomm.io.converters.readers.xrmmap_h5",
        "XRMMapH5Reader",
    ),
    "XRMMapH5Config": (
        "axiomm.io.converters.readers.xrmmap_h5",
        "XRMMapH5Config",
    ),
    "HyperSpyBuilder": (
        "axiomm.io.converters.signals.hyperspy_builder",
        "HyperSpyBuilder",
    ),
    "build_hyperspy_signal": (
        "axiomm.io.converters.signals.hyperspy_builder",
        "build_hyperspy_signal",
    ),
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        import importlib

        module_name, attr = _LAZY_EXPORTS[name]
        return getattr(importlib.import_module(module_name), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(__all__))
