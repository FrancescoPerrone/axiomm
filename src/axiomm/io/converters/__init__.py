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
from axiomm.io.converters.calibration import (
    CalibrationSource,
    ConversionMode,
    ResolvedValue,
)
from axiomm.io.converters.discovery import discover_inputs
from axiomm.io.converters.errors import (
    AxiommConverterError,
    CalibrationUnresolvedError,
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
    # calibration provenance primitives (Phase 4, Chunk 15)
    "CalibrationSource",
    "ConversionMode",
    "ResolvedValue",
    # exception hierarchy
    "AxiommConverterError",
    "CalibrationUnresolvedError",
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
    # workflow orchestrator (eagerly importable: no heavy deps at module load)
    "convert_file",
    # registry (eagerly importable: no heavy deps at module load)
    "Registry",
    "get_reader",
    "get_writer",
    "iter_readers",
    "iter_writers",
    "register_reader",
    "register_writer",
    # plugin discovery via Python entry points
    "ENTRY_POINT_READERS",
    "ENTRY_POINT_WRITERS",
    "find_reader_plugins",
    "find_writer_plugins",
    "load_plugins",
    # concrete readers + builders + writers (lazily imported — see __getattr__ below)
    "XRMMapH5Reader",
    "GenericHDF5MapReader",
    "HDF5MapConfig",
    "HDF5MapSchema",
    "XRMMAP_H5_SCHEMA",
    # calibration presets (Phase 4, Chunk 17)
    "XRMMapH5Calibration",
    "XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1",
    "get_preset",
    "iter_presets",
    "register_preset",
    "HyperSpyBuilder",
    "build_hyperspy_signal",
    "HSpyWriter",
    "ManifestWriter",
]


# Re-export validate_axes and convert_file eagerly: neither pulls heavy deps
# at module load time (h5py / hyperspy are imported inside call sites).
from axiomm.io.converters.registry import (  # noqa: E402
    ENTRY_POINT_READERS,
    ENTRY_POINT_WRITERS,
    Registry,
    find_reader_plugins,
    find_writer_plugins,
    get_reader,
    get_writer,
    iter_readers,
    iter_writers,
    load_plugins,
    register_reader,
    register_writer,
)
from axiomm.io.converters.signals.validation import validate_axes  # noqa: E402
from axiomm.io.converters.workflows import convert_file  # noqa: E402


# Lazy attribute imports (PEP 562). Concrete readers, builders and writers
# may carry optional runtime dependencies (h5py, hyperspy, …). Importing
# the converters package must stay light, so we only pull these in when
# user code actually touches the name.

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "XRMMapH5Reader": (
        "axiomm.io.converters.readers.xrmmap_h5",
        "XRMMapH5Reader",
    ),
    "XRMMapH5Calibration": (
        "axiomm.io.converters.presets",
        "XRMMapH5Calibration",
    ),
    "XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1": (
        "axiomm.io.converters.presets",
        "XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1",
    ),
    "get_preset": (
        "axiomm.io.converters.presets",
        "get_preset",
    ),
    "iter_presets": (
        "axiomm.io.converters.presets",
        "iter_presets",
    ),
    "register_preset": (
        "axiomm.io.converters.presets",
        "register_preset",
    ),
    "GenericHDF5MapReader": (
        "axiomm.io.converters.readers.hdf5_generic",
        "GenericHDF5MapReader",
    ),
    "HDF5MapConfig": (
        "axiomm.io.converters.readers.hdf5_generic",
        "HDF5MapConfig",
    ),
    "HDF5MapSchema": (
        "axiomm.io.converters.readers.hdf5_schema",
        "HDF5MapSchema",
    ),
    "XRMMAP_H5_SCHEMA": (
        "axiomm.io.converters.readers.hdf5_schema",
        "XRMMAP_H5_SCHEMA",
    ),
    "HyperSpyBuilder": (
        "axiomm.io.converters.signals.hyperspy_builder",
        "HyperSpyBuilder",
    ),
    "build_hyperspy_signal": (
        "axiomm.io.converters.signals.hyperspy_builder",
        "build_hyperspy_signal",
    ),
    "HSpyWriter": (
        "axiomm.io.converters.writers.hspy",
        "HSpyWriter",
    ),
    "ManifestWriter": (
        "axiomm.io.converters.writers.manifest",
        "ManifestWriter",
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
