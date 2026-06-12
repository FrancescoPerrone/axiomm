"""Shared HDF5 reading primitives (Chunk 14, spec §23 Phase 3).

The XRM-map reader and the new generic schema-driven reader perform
exactly the same low-level work to extract environ tables, ROI
tables, and the navigation pixel scale from an HDF5 file — only the
paths and a few scientific constants vary. This module hosts those
primitives as pure module-level functions so both readers (and any
future ones that consume the same XRM-like layout) call into a
single implementation.

Per the modularity rule each function answers one question:

* :func:`read_environ_table` — pull a name/value HDF5 metadata table.
* :func:`read_roi_table` — pull an ROI name + limits table, with
  built-in handling for both the ``(n_rois, 2)`` shape the prototype
  assumed and the ``(n_rois, n_variants, 2)`` shape real files use.
* :func:`resolve_navigation_scale` — work out the navigation pixel
  scale, with a source tag so callers can place the result in the
  right provenance bucket.

All three return ``(value, diagnostics)`` (and ``resolve_navigation_scale``
adds a third element — see its docstring). Missing optional metadata
becomes a structured :class:`~axiomm.io.converters.models.Diagnostic`
rather than an exception, matching spec §7.8.

These helpers don't import ``h5py`` themselves — they expect an
already-open ``h5py.File`` object, so the caller controls when h5py
is required.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from axiomm.io.converters.calibration import (
    CalibrationSource,
    ConversionMode,
    ResolvedValue,
)
from axiomm.io.converters.errors import MetadataParseError
from axiomm.io.converters.models import Diagnostic
# Pure data-decoding helpers — defined in xrmmap_h5 because that
# module landed first; importable from either location.
from axiomm.io.converters.readers.xrmmap_h5 import (
    decode_hdf5_string_array,
    parse_micrometre_value,
)


logger = logging.getLogger(__name__)


def read_environ_table(
    h5_file: Any,
    *,
    name_path: str | None,
    value_path: str | None,
) -> tuple[dict[str, str], list[Diagnostic]]:
    """Return ``({name: value}, diagnostics)`` from an HDF5 environ table.

    Parameters
    ----------
    h5_file
        An already-open ``h5py.File`` (or any object supporting
        ``__contains__`` + ``__getitem__`` over HDF5-style paths).
    name_path, value_path
        HDF5 paths to the parallel arrays of names and values.
        Either being ``None`` (or missing from the file) returns
        ``({}, [warning])`` — environ metadata is optional.

    Diagnostic codes:

    * ``environ_missing`` — one or both paths absent / ``None``.
    * ``environ_unreadable`` — datasets present but decoding failed.
    * ``environ_length_mismatch`` — the two arrays have different
      lengths; the pair is still returned but the warning surfaces.
    """
    diagnostics: list[Diagnostic] = []
    if (
        name_path is None
        or value_path is None
        or name_path not in h5_file
        or value_path not in h5_file
    ):
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="environ_missing",
                message=(
                    f"Configuration table not found at {name_path!r} and "
                    f"{value_path!r}; environ metadata not extracted."
                ),
            )
        )
        return {}, diagnostics

    try:
        names = decode_hdf5_string_array(h5_file[name_path][...])
        values = decode_hdf5_string_array(h5_file[value_path][...])
    except (TypeError, OSError, KeyError) as exc:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="environ_unreadable",
                message=f"Could not decode configuration table: {exc}",
            )
        )
        return {}, diagnostics

    if len(names) != len(values):
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="environ_length_mismatch",
                message=(
                    f"Configuration name/value arrays have different "
                    f"lengths ({len(names)} vs {len(values)}); "
                    f"truncating to the shorter."
                ),
            )
        )
    return dict(zip(names, values)), diagnostics


def read_roi_table(
    h5_file: Any,
    *,
    name_path: str | None,
    limits_path: str | None,
    roi_variant_index: int = 0,
    roi_limit_scale: float = 0.01,
) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
    """Return ``(rois, diagnostics)`` from an HDF5 ROI name + limits table.

    Accepts limits arrays of shape ``(n_rois, 2)`` or
    ``(n_rois, n_variants, 2)``; in the 3-D case selects the
    ``roi_variant_index``-th variant. Each ROI is returned as
    ``{"name": str, "start": float, "end": float}`` with start/end
    scaled by ``roi_limit_scale``.

    Diagnostic codes (each one short-circuits and returns ``([], [d])``):

    * ``roi_missing`` — either path is ``None`` / missing.
    * ``roi_unreadable`` — datasets present but decoding failed.
    * ``roi_limits_unexpected_shape`` — neither ``(n, 2)`` nor
      ``(n, k, 2)``.
    * ``roi_variant_out_of_bounds`` — 3-D shape but the configured
      ``roi_variant_index`` is out of range.
    * ``roi_names_limits_length_mismatch`` — names and limits arrays
      disagree on count; refusing to guess which to keep.
    """
    diagnostics: list[Diagnostic] = []
    if (
        name_path is None
        or limits_path is None
        or name_path not in h5_file
        or limits_path not in h5_file
    ):
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="roi_missing",
                message=(
                    f"ROI metadata not found at {name_path!r} and "
                    f"{limits_path!r}; continuing without ROI info."
                ),
            )
        )
        return [], diagnostics

    try:
        names = decode_hdf5_string_array(h5_file[name_path][...])
        limits = np.asarray(h5_file[limits_path][...])
    except (TypeError, OSError, KeyError) as exc:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="roi_unreadable",
                message=f"Could not decode ROI metadata: {exc}",
            )
        )
        return [], diagnostics

    if limits.ndim == 3 and limits.shape[2] == 2:
        n_variants = limits.shape[1]
        if not 0 <= roi_variant_index < n_variants:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="roi_variant_out_of_bounds",
                    message=(
                        f"ROI limits dataset has shape {limits.shape!r} "
                        f"({n_variants} variants per ROI); configured "
                        f"roi_variant_index={roi_variant_index} is out of "
                        f"bounds [0, {n_variants}). Skipping ROI extraction. "
                        f"Set roi_variant_index to a value in that range "
                        f"to extract."
                    ),
                )
            )
            return [], diagnostics
        limits = limits[:, roi_variant_index, :]
    elif not (limits.ndim == 2 and limits.shape[1] == 2):
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="roi_limits_unexpected_shape",
                message=(
                    f"ROI limits array has unexpected shape "
                    f"{limits.shape!r}; expected exactly (n_rois, 2) or "
                    f"(n_rois, n_variants, 2). Skipping ROI extraction."
                ),
            )
        )
        return [], diagnostics

    if len(names) != len(limits):
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="roi_names_limits_length_mismatch",
                message=(
                    f"ROI names ({len(names)}) and limits ({len(limits)}) "
                    f"have different lengths; refusing to guess which "
                    f"to keep. Skipping ROI extraction."
                ),
            )
        )
        return [], diagnostics

    return [
        {
            "name": names[i],
            "start": float(limits[i, 0]) * roi_limit_scale,
            "end": float(limits[i, 1]) * roi_limit_scale,
        }
        for i in range(len(names))
    ], diagnostics


def resolve_navigation_scale(
    environ: dict[str, str],
    *,
    beam_size_key: str | None,
    fallback_field_width_um: float | None,
    xdim: int,
) -> tuple[float, list[Diagnostic], str]:
    """Return ``(scale_um, diagnostics, source_tag)``.

    ``source_tag`` is one of ``"beam_size"``, ``"fallback"``, or
    ``"unit"`` so callers can classify the resulting axis scale per
    spec §15:

    * ``beam_size`` → ``observed`` (came from the file's environ table).
    * ``fallback`` → ``assumed`` (came from ``fallback_field_width_um``).
    * ``unit`` → ``assumed`` (no beam size and no fallback configured).
    """
    diagnostics: list[Diagnostic] = []
    beam_size_str = (
        environ.get(beam_size_key) if beam_size_key is not None else None
    )
    if beam_size_str is not None:
        try:
            return (
                parse_micrometre_value(beam_size_str),
                diagnostics,
                "beam_size",
            )
        except MetadataParseError as exc:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="beam_size_unparseable",
                    message=(
                        f"Could not parse beam size {beam_size_str!r}: "
                        f"{exc}. Falling back to "
                        f"fallback_field_width_um / xdim."
                    ),
                )
            )
    else:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="beam_size_missing",
                message=(
                    f"Beam-size key {beam_size_key!r} not found in the "
                    f"configuration table; falling back to "
                    f"fallback_field_width_um / xdim."
                ),
            )
        )

    if fallback_field_width_um is None:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="navigation_scale_unknown",
                message=(
                    "No beam size available and no "
                    "fallback_field_width_um configured; navigation "
                    "scale set to 1.0."
                ),
            )
        )
        return 1.0, diagnostics, "unit"

    return float(fallback_field_width_um) / xdim, diagnostics, "fallback"


# ---------------------------------------------------------------------------
# Resolution-ladder helpers (Phase 4, Chunk 16)
# ---------------------------------------------------------------------------
#
# These three helpers stamp calibration values with their
# :class:`CalibrationSource` so downstream code can tell what came from
# the source file's metadata, what came from a recognised legacy
# preset, and what remains unresolved. Chunk 16 keeps the *values*
# unchanged (legacy-equivalent behaviour for the AXIOMM author's
# inherited dataset); only the provenance annotation is new.
#
# Strict-mode enforcement and source-metadata extraction for the
# energy + ROI-units paths land in later chunks once the calibration
# dataclasses gain explicit-units / explicit-geometry fields. For now,
# helpers receive the configured value and the active mode, and
# return a :class:`ResolvedValue` whose ``source`` reflects what the
# reader *actually did* on this conversion.

def resolve_energy_scale(
    config_value: float,
    *,
    mode: ConversionMode,
) -> ResolvedValue:
    """Resolve the per-channel energy width for the spectral axis.

    Chunk 16 scope: the configured value is taken as a recognised
    legacy preset and stamped ``CalibrationSource.LEGACY_PRESET``.
    Source-metadata extraction (e.g. from an HDF5 calibration block)
    and strict-mode enforcement are introduced in later Phase 4
    chunks once the calibration dataclass gains an explicit
    ``UNRESOLVED`` sentinel distinct from a concrete legacy value.
    """
    return ResolvedValue(
        value=float(config_value),
        source=CalibrationSource.LEGACY_PRESET,
        note=f"reader config default (mode={mode.value})",
    )


def resolve_roi_limit_interpretation(
    roi_limit_scale: float,
    *,
    mode: ConversionMode,
) -> ResolvedValue:
    """Resolve the unit interpretation of ROI limits.

    The historical reader scales raw integer ROI limits at
    ``/xrmmap/config/rois/limits`` by a configured
    ``roi_limit_scale``; the prototype used ``0.01``. The AXIOMM
    metadata audit (2026-06-12, ``melts/data/metadata_audit_report
    .md``) confirms that for the inherited APS 13-ID-E dataset the
    integer limits at ``/xrmmap/config/rois/limits`` are **MCA
    channel indices** (shape ``(n_rois, n_variants, 2)``, dtype
    ``int32``/``int64``, values like ``[10, 4090]``, no ``keV``
    or ``type`` attrs), and the ``0.01`` multiplier numerically
    coincides with the MCA ``slope`` calibration — so the
    operation is a channel→keV conversion via the energy
    calibration, **not** a centi-keV unit scaling. The audit also
    notes that this dataset additionally stores explicit keV-form
    ROI windows at ``/xrmmap/roimap/mcasum/<ROI>/limits`` with
    ``attrs.type='energy'`` and ``attrs.units='keV'``, which the
    converter should prefer once Chunk 18 lands.

    For Chunk 16 the helper records what the reader *currently
    does* (multiply integer limits by ``roi_limit_scale``) and
    stamps the unit interpretation as :attr:`CalibrationSource
    .INFERRED` — not :attr:`LEGACY_PRESET` — because the unit
    token is inferred from the numeric scale, not from a recognised
    named preset. When the scale equals the historic ``0.01`` the
    inferred token is ``"channel_index"`` (audit-supported);
    otherwise ``"unknown"``. Chunk 18 will introduce an explicit
    ``roi_limit_units`` literal (``centi_keV`` / ``keV`` /
    ``channel_index``) that disambiguates and switches the source
    to :attr:`USER_CONFIG` when supplied.

    In :class:`ConversionMode.STRICT` the helper reports
    :attr:`CalibrationSource.UNKNOWN` so downstream Chunk-17 code
    can raise :class:`CalibrationUnresolvedError`; the actual
    raise is not wired in Chunk 16.
    """
    if mode is ConversionMode.STRICT:
        return ResolvedValue(
            value="unknown",
            source=CalibrationSource.UNKNOWN,
            note=(
                "strict mode: ROI limit units must be supplied "
                "explicitly via the calibration dataclass field "
                "introduced in Chunk 18."
            ),
        )
    inferred = (
        "channel_index" if abs(roi_limit_scale - 0.01) < 1e-9 else "unknown"
    )
    return ResolvedValue(
        value=inferred,
        source=CalibrationSource.INFERRED,
        note=(
            f"roi_limit_scale={roi_limit_scale} inferred as "
            f"{inferred!r} (mode={mode.value}); per 2026-06-12 "
            f"audit of /xrmmap/config/rois/limits on the inherited "
            f"APS 13-ID-E dataset, integer ROI limits are channel "
            f"indices and the 0.01 multiplier matches mca_calib/slope. "
            f"Prefer /xrmmap/roimap/mcasum/<ROI>/limits when reading "
            f"keV-labelled ROIs (planned for Chunk 18)."
        ),
    )


def resolve_navigation_scale_calibration(
    environ: dict[str, str],
    *,
    beam_size_key: str | None,
    fallback_field_width_um: float | None,
    xdim: int,
    mode: ConversionMode,
) -> tuple[ResolvedValue, list[Diagnostic]]:
    """Resolve the navigation pixel scale with provenance.

    Thin wrapper over :func:`resolve_navigation_scale` that maps the
    legacy ``source_tag`` string into a :class:`CalibrationSource`:

    * ``beam_size`` → :attr:`CalibrationSource.SOURCE_METADATA` —
      the value was read from the file's environ table.
    * ``fallback`` → :attr:`CalibrationSource.LEGACY_PRESET` —
      ``fallback_field_width_um / xdim`` was applied; the geology
      team flagged this fallback as *not beam size*, more likely a
      scan-field width legacy.
    * ``unit`` → :attr:`CalibrationSource.UNKNOWN` — no environ
      beam size, no fallback, scale defaulted to ``1.0``.

    The existing :func:`resolve_navigation_scale` remains as-is so
    callers that don't need provenance continue to work unchanged.
    """
    value, diagnostics, source_tag = resolve_navigation_scale(
        environ,
        beam_size_key=beam_size_key,
        fallback_field_width_um=fallback_field_width_um,
        xdim=xdim,
    )
    source_map = {
        "beam_size": CalibrationSource.SOURCE_METADATA,
        "fallback": CalibrationSource.LEGACY_PRESET,
        "unit": CalibrationSource.UNKNOWN,
    }
    note_map = {
        "beam_size": (
            f"parsed from environ {beam_size_key!r} (mode={mode.value})"
        ),
        "fallback": (
            f"fallback_field_width_um={fallback_field_width_um} / "
            f"xdim={xdim} (mode={mode.value})"
        ),
        "unit": (
            f"no beam size, no fallback: scale 1.0 (mode={mode.value})"
        ),
    }
    return (
        ResolvedValue(
            value=value,
            source=source_map[source_tag],
            note=note_map[source_tag],
        ),
        diagnostics,
    )


__all__ = [
    "read_environ_table",
    "read_roi_table",
    "resolve_energy_scale",
    "resolve_navigation_scale",
    "resolve_navigation_scale_calibration",
    "resolve_roi_limit_interpretation",
]
