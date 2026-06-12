"""Exception hierarchy for the AXIOMM converter package.

All converter-specific exceptions inherit from :class:`AxiommConverterError`,
which itself inherits from the standard :class:`Exception`. Workflow code
should catch specific subclasses rather than the base where possible, and
must avoid bare ``except Exception`` outside workflow boundaries.

See spec §13.
"""

from __future__ import annotations


class AxiommConverterError(Exception):
    """Base exception for AXIOMM converter errors."""


class InputDiscoveryError(AxiommConverterError):
    """Raised when input discovery cannot resolve any usable input file."""


class ReaderDetectionError(AxiommConverterError):
    """Raised when reader auto-detection cannot decide which reader to use,
    or when no registered reader supports the given input.
    """


class UnsupportedFormatError(AxiommConverterError):
    """Raised when a request targets a format AXIOMM does not (yet) support."""


class DatasetNotFoundError(AxiommConverterError):
    """Raised when a required dataset is missing from the source file."""


class MetadataParseError(AxiommConverterError):
    """Raised when required metadata cannot be parsed (e.g. malformed beam size)."""


class SignalValidationError(AxiommConverterError):
    """Raised when an :class:`AxiommSignalPayload` fails validation before build."""


class OutputExistsError(AxiommConverterError):
    """Raised when an output path already exists and overwrite was not requested."""


class ConversionWorkflowError(AxiommConverterError):
    """Raised by workflow orchestrators when a conversion fails for reasons that
    do not fit a more specific exception (e.g. unexpected post-build state).
    """


class CalibrationUnresolvedError(AxiommConverterError):
    """Raised by the calibration resolution ladder in
    :class:`~axiomm.io.converters.calibration.ConversionMode.STRICT`
    when a required calibration value cannot be resolved from either
    source metadata or explicit user configuration.

    The message names the missing calibration and how to provide it
    (e.g. ``calibration={"energy_scale": ResolvedValue(...)}`` or the
    relevant config field).

    Declared in Phase 4, Chunk 16 alongside the resolution-ladder
    helpers; raised from Chunk 17 onwards once ``XRMMapH5Calibration``
    defaults become ``UNRESOLVED`` sentinels rather than concrete
    legacy values.
    """


__all__ = [
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
]
