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
from axiomm.io.converters.errors import (
    CalibrationUnresolvedError,
    MetadataParseError,
)
from axiomm.io.converters.models import Diagnostic
from axiomm.io.converters.presets import RoiLimitUnits
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
    user_value: float | None,
    preset_value: float | None,
    *,
    mode: ConversionMode,
) -> ResolvedValue:
    """Resolve the per-channel energy width for the spectral axis.

    The resolution ladder (Chunk 17) walks
    ``USER_CONFIG`` → ``LEGACY_PRESET`` → ``UNKNOWN``:

    * If ``user_value`` is not ``None``: the user supplied a value
      explicitly; returned with :attr:`CalibrationSource.USER_CONFIG`
      and always wins.
    * Otherwise, in :class:`ConversionMode.STRICT`: returned with
      :attr:`CalibrationSource.UNKNOWN`. The reader raises
      :class:`~axiomm.io.converters.errors.CalibrationUnresolvedError`
      on this.
    * Otherwise, if ``preset_value`` is not ``None``: returned with
      :attr:`CalibrationSource.LEGACY_PRESET`.
    * Otherwise: returned with :attr:`CalibrationSource.UNKNOWN`
      and ``value=None``; the reader handles the unresolved case.

    Source-metadata extraction from ``/xrmmap/config/mca_calib/*``
    (audit-confirmed) is the responsibility of Chunk 18 — when
    available it will outrank the preset but still lose to
    ``USER_CONFIG``.
    """
    if user_value is not None:
        return ResolvedValue(
            value=float(user_value),
            source=CalibrationSource.USER_CONFIG,
            note=(
                f"user-supplied via calibration field "
                f"(mode={mode.value})"
            ),
        )
    if mode is ConversionMode.STRICT:
        return ResolvedValue(
            value=None,
            source=CalibrationSource.UNKNOWN,
            note=(
                "strict mode: energy_scale must be supplied "
                "explicitly via XRMMapH5Calibration(energy_scale=...)."
            ),
        )
    if preset_value is None:
        return ResolvedValue(
            value=None,
            source=CalibrationSource.UNKNOWN,
            note=f"no user value, no preset (mode={mode.value})",
        )
    return ResolvedValue(
        value=float(preset_value),
        source=CalibrationSource.LEGACY_PRESET,
        note=f"applied from legacy preset (mode={mode.value})",
    )


def resolve_roi_limit_interpretation(
    user_units: RoiLimitUnits | None,
    preset_units: RoiLimitUnits | None,
    *,
    mode: ConversionMode,
) -> ResolvedValue:
    """Resolve the unit interpretation of integer ROI limits.

    Phase 4, Chunk 18: the helper now takes **explicit unit tokens**
    rather than a numeric scale. Three tokens are documented in
    :data:`~axiomm.io.converters.presets.RoiLimitUnits`:

    * ``"centi_keV"`` — limits are integers in centi-keV.
    * ``"keV"`` — limits are already in keV.
    * ``"channel_index"`` — limits are MCA channel indices; the
      reader scales them by the resolved ``energy_scale``.

    The token is the *meaning* of the integer limits. The numeric
    multiplier the reader actually applies is derived by
    :func:`compute_roi_scale_from_units` after both the unit and the
    ``energy_scale`` have been resolved — this removes the
    centi-keV ↔ channel-index degeneracy that motivated the rewrite.

    Resolution order: ``USER_CONFIG`` (non-``None`` user token) →
    :attr:`CalibrationSource.LEGACY_PRESET` (non-``None`` preset token
    in non-strict modes) → :attr:`CalibrationSource.UNKNOWN`.
    """
    if user_units is not None:
        return ResolvedValue(
            value=user_units,
            source=CalibrationSource.USER_CONFIG,
            note=(
                f"user-supplied roi_limit_units={user_units!r} "
                f"(mode={mode.value})"
            ),
        )
    if mode is ConversionMode.STRICT:
        return ResolvedValue(
            value="unknown",
            source=CalibrationSource.UNKNOWN,
            note=(
                "strict mode: roi_limit_units must be supplied "
                "explicitly via the calibration's `roi_limit_units` "
                "field."
            ),
        )
    if preset_units is None:
        return ResolvedValue(
            value="unknown",
            source=CalibrationSource.UNKNOWN,
            note=f"no user value, no preset (mode={mode.value})",
        )
    return ResolvedValue(
        value=preset_units,
        source=CalibrationSource.LEGACY_PRESET,
        note=(
            f"applied roi_limit_units={preset_units!r} from legacy "
            f"preset (mode={mode.value})"
        ),
    )


def compute_roi_scale_from_units(
    units: RoiLimitUnits | str,
    energy_scale: float | None,
) -> float | None:
    """Map a resolved :data:`RoiLimitUnits` token to a numeric
    multiplier for integer ROI limits.

    Returns ``None`` when the multiplier can't be derived (token is
    ``"channel_index"`` but no ``energy_scale`` resolved, or the
    token is unrecognised — e.g. ``"unknown"``). Callers fall back
    to ``1.0`` and emit a diagnostic, or raise in strict mode.
    """
    if units == "centi_keV":
        return 0.01
    if units == "keV":
        return 1.0
    if units == "channel_index":
        if energy_scale is None:
            return None
        return float(energy_scale)
    return None


def resolve_navigation_scale_calibration(
    environ: dict[str, str],
    *,
    beam_size_key: str | None,
    user_pixel_size_um: float | None = None,
    user_field_width_um: float | None = None,
    preset_legacy_field_width_um: float | None = None,
    xdim: int,
    mode: ConversionMode,
) -> tuple[ResolvedValue, list[Diagnostic]]:
    """Resolve the navigation pixel scale with the full ladder.

    Phase 4, Chunk 18: the ladder now consumes the explicit-geometry
    fields introduced on :class:`XRMMapH5Calibration` /
    :class:`HDF5MapCalibration`. Resolution order:

    1. **Environ table** ``beam_size_key`` →
       :attr:`CalibrationSource.SOURCE_METADATA`. The file's own
       beam-size metadata wins.
    2. ``user_pixel_size_um`` (non-``None``) →
       :attr:`CalibrationSource.USER_CONFIG`. Direct scale, no
       division.
    3. ``user_field_width_um`` (non-``None``) →
       :attr:`CalibrationSource.USER_CONFIG`. Scale =
       ``user_field_width_um / xdim``.
    4. ``preset_legacy_field_width_um`` (non-``None``, only in
       non-strict modes) → :attr:`CalibrationSource.LEGACY_PRESET`.
       Scale = ``preset_legacy_field_width_um / xdim``. The
       2026-06-12 audit confirmed this is scan-field extent, not
       beam size — hence the explicit ``legacy_field_width_um``
       naming (renamed from ``fallback_field_width_um``).
    5. Otherwise → :attr:`CalibrationSource.UNKNOWN` with scale
       ``1.0``; the reader raises in strict mode.
    """
    # Environ beam_size wins outright (when present and parseable).
    diagnostics: list[Diagnostic] = []
    beam_size_str = (
        environ.get(beam_size_key) if beam_size_key is not None else None
    )
    if beam_size_str is not None:
        try:
            parsed = parse_micrometre_value(beam_size_str)
            return (
                ResolvedValue(
                    value=parsed,
                    source=CalibrationSource.SOURCE_METADATA,
                    note=(
                        f"parsed from environ {beam_size_key!r} "
                        f"(mode={mode.value})"
                    ),
                ),
                diagnostics,
            )
        except MetadataParseError as exc:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="beam_size_unparseable",
                    message=(
                        f"Could not parse beam size {beam_size_str!r}: "
                        f"{exc}. Falling through the resolution ladder."
                    ),
                )
            )
    elif beam_size_key is not None:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="beam_size_missing",
                message=(
                    f"Beam-size key {beam_size_key!r} not found in the "
                    f"configuration table; falling through the "
                    f"resolution ladder."
                ),
            )
        )

    # User-supplied pixel size — direct scale.
    if user_pixel_size_um is not None:
        return (
            ResolvedValue(
                value=float(user_pixel_size_um),
                source=CalibrationSource.USER_CONFIG,
                note=(
                    f"user-supplied pixel_size_um="
                    f"{user_pixel_size_um} (mode={mode.value})"
                ),
            ),
            diagnostics,
        )

    # User-supplied field width — derived scale.
    if user_field_width_um is not None:
        return (
            ResolvedValue(
                value=float(user_field_width_um) / xdim,
                source=CalibrationSource.USER_CONFIG,
                note=(
                    f"user-supplied field_width_um="
                    f"{user_field_width_um} / xdim={xdim} "
                    f"(mode={mode.value})"
                ),
            ),
            diagnostics,
        )

    # Legacy preset (only in non-strict modes).
    if (
        mode is not ConversionMode.STRICT
        and preset_legacy_field_width_um is not None
    ):
        return (
            ResolvedValue(
                value=float(preset_legacy_field_width_um) / xdim,
                source=CalibrationSource.LEGACY_PRESET,
                note=(
                    f"applied legacy_field_width_um="
                    f"{preset_legacy_field_width_um} / xdim={xdim} "
                    f"from legacy preset (mode={mode.value})"
                ),
            ),
            diagnostics,
        )

    # Nothing resolved.
    diagnostics.append(
        Diagnostic(
            severity="warning",
            code="navigation_scale_unknown",
            message=(
                f"No beam size in environ, no user pixel_size_um / "
                f"field_width_um, no preset legacy_field_width_um "
                f"applicable (mode={mode.value}); navigation scale "
                f"set to 1.0."
            ),
        )
    )
    return (
        ResolvedValue(
            value=1.0,
            source=CalibrationSource.UNKNOWN,
            note=(
                f"no resolved scale (mode={mode.value}); scale "
                f"defaulted to 1.0"
            ),
        ),
        diagnostics,
    )


def raise_if_strict_unresolved(
    mode: ConversionMode,
    resolved_calibration: dict[str, ResolvedValue],
) -> None:
    """Raise :class:`CalibrationUnresolvedError` when any calibration
    value remains :attr:`CalibrationSource.UNKNOWN` under strict mode.

    Shared by both readers (Chunk 18) so the strict-mode policy is
    enforced from one canonical place.
    """
    if mode is not ConversionMode.STRICT:
        return
    unresolved = sorted(
        name for name, rv in resolved_calibration.items()
        if rv.source is CalibrationSource.UNKNOWN
    )
    if not unresolved:
        return
    raise CalibrationUnresolvedError(
        f"strict mode: the following calibration values could not be "
        f"resolved from user-supplied configuration: "
        f"{', '.join(unresolved)}. Pass an explicit calibration "
        f"(XRMMapH5Calibration / HDF5MapCalibration) with those fields "
        f"set, or switch to ConversionMode.LEGACY / GENERIC to allow "
        f"preset fallbacks."
    )


__all__ = [
    "compute_roi_scale_from_units",
    "raise_if_strict_unresolved",
    "read_environ_table",
    "read_roi_table",
    "resolve_energy_scale",
    "resolve_navigation_scale",
    "resolve_navigation_scale_calibration",
    "resolve_roi_limit_interpretation",
]
