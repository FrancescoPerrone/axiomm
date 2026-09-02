"""AXIOMM calibration provenance primitives (Phase 4, Chunk 15).

These primitives carry **per-value provenance** for scientific
calibration scalars — energy scale, navigation pixel scale, ROI-limit
interpretation, spatial extent — so a downstream consumer can tell
whether a given value came from the source file's metadata, from
explicit user configuration, from a recognised named legacy preset,
from a heuristic inference, or remains unresolved.

The motivation is the AXIOMM geology team's reply (2026-06-12) on the
three legacy XRM-Map scientific constants that were previously bundled
into the reader's monolithic config dataclass. The team did not
confirm specific values; they returned a policy: legacy
beamline/sample-specific constants must not be silently applied as
universal defaults. The public converter must instead resolve each
calibration value through a precedence ladder and stamp it with its
source.

This module is intentionally **type-only and backend-neutral**: it
does not import readers, writers, h5py, or HyperSpy. The full
resolution ladder (precedence: source metadata → explicit user config
→ recognised legacy preset → cautious inference → strict-mode error)
is built on top of these primitives by the resolution helpers in
:mod:`axiomm.io.converters.readers.hdf5_helpers` and wired into both
readers; see ``docs/user/converter.md`` → *Calibration resolution*
for the canonical user-facing reference and ``docs/dev/STATE.md`` for
the Phase 4 chunk plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CalibrationSource(str, Enum):
    """Where a single resolved calibration value came from.

    Recorded *per value* rather than per reader: one conversion can
    legitimately mix sources — e.g. an ``energy_scale`` read from
    source metadata while a ``field_width_um`` comes from a legacy
    preset. The five values cover the geology team's recommended
    precedence ladder plus an explicit ``UNKNOWN`` for values that
    remain unresolved in non-strict modes.

    Stored as a ``str`` subclass so that ``json.dumps`` produces the
    bare string token (e.g. ``"source_metadata"``) rather than a
    repr — keeping the manifest sidecar human-readable.
    """

    SOURCE_METADATA = "source_metadata"
    """Read from the source file's metadata (HDF5 attribute, environ
    table, embedded calibration block, ...). Most authoritative."""

    USER_CONFIG = "user_config"
    """Supplied explicitly by the caller, typically via the
    ``calibration=`` keyword on :func:`convert_file` or by passing
    a configured reader. Wins over source metadata when both are
    present, on the assumption that the user knows their experiment."""

    LEGACY_PRESET = "legacy_preset"
    """Pulled from a recognised named preset for a known legacy
    dataset (e.g. the APS 13-ID-E preset for the AXIOMM author's
    inherited XRM samples). Only consulted in ``ConversionMode.LEGACY``."""

    INFERRED = "inferred"
    """Derived heuristically from observed values (e.g. a unit
    inferred from a numeric range). Always accompanied by a warning
    diagnostic. Never used in ``ConversionMode.STRICT``."""

    UNKNOWN = "unknown"
    """No source resolved the value. Reserved for diagnostic-mode
    reports and for entries the user must supply before re-running."""


class ConversionMode(str, Enum):
    """Conversion mode that controls how the resolution ladder behaves.

    The mode is a **policy switch** on the resolution ladder, not a
    behaviour switch on individual readers. The same reader produces
    different outcomes for the same input depending on the mode it
    runs under.

    Stored as a ``str`` subclass so the value round-trips cleanly
    through JSON manifests and dataclass dumps.
    """

    LEGACY = "legacy"
    """Backwards-compatible mode for the AXIOMM prototype's inherited
    dataset. Falls back to the recognised named legacy preset when
    neither user config nor source metadata resolves a required
    calibration value. Diagnostics still flag every preset use."""

    GENERIC = "generic"
    """Safe public default. **No silent legacy-preset fallback.**
    User config or source metadata must resolve every required value;
    otherwise a warning diagnostic is emitted and the value remains
    ``UNKNOWN``. Optional values may stay ``UNKNOWN`` without warning."""

    STRICT = "strict"
    """No inference allowed. Every required calibration value must
    be resolved from ``SOURCE_METADATA`` or ``USER_CONFIG``;
    anything else raises a clear error naming the missing parameter
    and how to provide it."""

    DIAGNOSTIC = "diagnostic"
    """Dry-run reporting mode. Walks the ladder, records every
    candidate source and unresolved ambiguity, but does not commit
    to one resolution. Output is the report itself; no signal is
    written."""


@dataclass(frozen=True)
class ResolvedValue:
    """A calibration value paired with its provenance.

    Parameters
    ----------
    value
        The resolved value. Typed as :class:`Any` so the primitive
        can carry floats (``energy_scale``, ``pixel_size_um``),
        string literals (units like ``"keV"`` or unit-system tokens
        like ``"channel_index"``), or ``None`` when the value
        remains unresolved in non-strict modes.
    source
        Which :class:`CalibrationSource` produced ``value``.
    note
        Optional human-readable context (e.g. the HDF5 path the
        value was read from, the preset name applied, or the
        inference rule that fired). ``None`` when no extra context
        applies. Surfaces in manifest sidecars so a user reading
        a converted artefact months later can tell *why* a value
        is what it is.

    The dataclass is frozen so :class:`ResolvedValue` instances are
    hashable and safe to share across a conversion's metadata tree
    without aliasing concerns.
    """

    value: Any
    source: CalibrationSource
    note: str | None = None


__all__ = [
    "CalibrationSource",
    "ConversionMode",
    "ResolvedValue",
]
