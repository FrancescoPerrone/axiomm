"""Neutral in-memory data model for the AXIOMM converter.

These dataclasses are deliberately backend-agnostic: they describe an
N-dimensional scientific signal, its axes, its metadata, and its provenance
without referring to HyperSpy, h5py, or any other concrete library. Format
specifics live in readers; signal-backend specifics live in builders.

See spec §8.3 (signal model) and §9.6 (conversion result).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping

if TYPE_CHECKING:
    from axiomm.io.converters.calibration import ResolvedValue

AxisRole = Literal["navigation", "signal"]
"""The role an axis plays in the signal: a navigation axis indexes points in
sample space (e.g. spatial x/y); a signal axis is the dimension along which
the signal is measured (e.g. energy channels)."""

SignalKind = Literal["auto", "signal1d", "signal2d", "base"]
"""Hint for the signal builder. ``"auto"`` resolves deterministically from the
number of signal-role axes."""

Severity = Literal["info", "warning", "error"]
"""Severity levels for :class:`Diagnostic`."""


@dataclass(frozen=True)
class AxisSpec:
    """Description of a single axis of an N-dimensional signal.

    Parameters
    ----------
    name
        Human-readable axis name (e.g. ``"x"``, ``"Energy"``).
    role
        ``"navigation"`` or ``"signal"``.
    size
        Number of samples along this axis.
    units
        Physical units string (e.g. ``"µm"``, ``"keV"``). ``None`` when unknown.
    scale
        Step size between adjacent samples in ``units``.
    offset
        Value of the first sample in ``units``.
    index_in_array
        Position of this axis in the underlying ``data`` array. Builders use
        this to map between AXIOMM's neutral axis order and the backend's
        internal order.
    """

    name: str
    role: AxisRole
    size: int
    units: str | None = None
    scale: float | None = None
    offset: float = 0.0
    index_in_array: int | None = None


@dataclass(frozen=True)
class Diagnostic:
    """A structured warning, info, or error message attached to a conversion.

    Diagnostics travel with the payload so UX layers and the manifest writer
    can surface them without lossy ``print`` calls.
    """

    severity: Severity
    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceProvenance:
    """Provenance information about the source of a payload."""

    path: Path
    reader: str
    reader_version: str | None = None
    input_hash: str | None = None


@dataclass
class AxiommSignalPayload:
    """Neutral in-memory representation of a scientific signal.

    ``data`` is typed as :class:`Any` rather than :class:`numpy.ndarray` so
    that large HDF5-backed or otherwise lazy data is not forced into memory
    by the conversion pipeline. Builders are responsible for materialising
    or wrapping ``data`` as appropriate for their backend.

    Axis order in the underlying array is determined by
    :attr:`AxisSpec.index_in_array` — *not* by the position of axes in the
    ``axes`` tuple. Builders must consult that index when assigning axes to
    backend signal objects.
    """

    data: Any
    axes: tuple[AxisSpec, ...]
    signal_kind: SignalKind
    metadata: dict[str, Any] = field(default_factory=dict)
    original_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: SourceProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    title: str | None = None
    #: Per-value calibration provenance (Phase 4, Chunk 15). When non-None,
    #: maps a calibration name (e.g. ``"energy_scale"``,
    #: ``"navigation_scale"``, ``"roi_limit_units"``) to a
    #: :class:`~axiomm.io.converters.calibration.ResolvedValue` carrying
    #: the value plus its :class:`~axiomm.io.converters.calibration
    #: .CalibrationSource`. ``None`` until a reader populates it; readers
    #: pre-dating Chunk 16 leave it as ``None`` and the metadata namespace
    #: omits the ``"calibration"`` subkey accordingly.
    resolved_calibration: dict[str, "ResolvedValue"] | None = None


@dataclass(frozen=True)
class ConversionResult:
    """Outcome of a single end-to-end conversion."""

    input_path: Path
    output_path: Path
    manifest_path: Path | None
    reader_name: str
    writer_name: str
    diagnostics: tuple[Diagnostic, ...] = ()


__all__ = [
    "AxisRole",
    "AxisSpec",
    "AxiommSignalPayload",
    "ConversionResult",
    "Diagnostic",
    "Severity",
    "SignalKind",
    "SourceProvenance",
]
