"""Named calibration presets for AXIOMM readers (Phase 4, Chunk 17).

A **preset** is a recognised calibration configuration for a known
legacy dataset / beamline. Presets are *named* and *importable* so a
user inspecting a converted artefact can tell which preset was applied
just from the manifest sidecar's ``calibration.*.note`` field. Per the
locked Phase-4 plan, presets stay as code constants here rather than
external YAML — the user-facing UX for calibration is the
``calibration=`` keyword on :class:`~axiomm.io.converters.readers
.xrmmap_h5.XRMMapH5Reader`, not preset-name lookup.

The first concrete preset, :data:`XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1`,
captures the historic constants from the AXIOMM author's inherited
XRM-Map samples. The 2026-06-12 metadata audit on
``~/Desktop/research/melts/data/Maps-HDF5/`` confirmed the
beamline identifier as ``"GSECARS, 13-IDE / APS"`` and showed each
constant has a direct source-metadata equivalent in the HDF5 files
themselves; the preset preserves backwards-compatibility while
Chunks 18+ migrate to reading those source paths directly.

Presets are not the headline UX. **Prefer user-supplied calibration
via ``calibration=XRMMapH5Calibration(...)``** when working with new
instruments or experiments; presets are the *backstop* for the one
named legacy dataset they were derived from.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Literal


#: Token type for the ``roi_limit_units`` field. Three documented
#: tokens disambiguate how integer ROI limits at
#: ``/xrmmap/config/rois/limits`` should be interpreted:
#:
#: * ``"centi_keV"`` — limits are integers in centi-keV; multiply
#:   by ``0.01`` to recover keV.
#: * ``"keV"`` — limits are already in keV; no conversion.
#: * ``"channel_index"`` — limits are MCA channel indices; multiply
#:   by the resolved ``energy_scale`` to recover keV.
#:
#: The 2026-06-12 metadata audit on the inherited APS 13-ID-E
#: dataset confirmed ``channel_index`` for that data — see
#: :data:`XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1`.
RoiLimitUnits = Literal["centi_keV", "keV", "channel_index"]


@dataclass(frozen=True)
class XRMMapH5Calibration:
    """Scientific calibration values consumed by
    :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Reader`.

    Every field defaults to ``None``. The reader's resolution ladder
    treats ``None`` as **"not user-supplied"** and falls back to the
    active preset (legacy / generic / diagnostic modes), or raises
    :class:`~axiomm.io.converters.errors.CalibrationUnresolvedError`
    (strict mode). A non-``None`` value is treated as
    :attr:`CalibrationSource.USER_CONFIG` and always wins over the
    preset.

    The class is intentionally separate from
    :class:`~axiomm.io.converters.readers.hdf5_schema.HDF5MapSchema`,
    which carries *where* things live in the file. Schema = paths.
    Calibration = numbers and unit conventions. The split lets a
    single schema serve several instrument generations whose
    calibration constants differ.

    Attributes
    ----------
    energy_scale
        Per-MCA-channel energy width in keV. The AXIOMM legacy
        dataset stores ``0.01 keV/channel`` at
        ``/xrmmap/config/mca_calib/slope``; the preset reproduces
        that value as ``40.96 / 4096``.
    roi_limit_units
        Explicit unit interpretation of the integer ROI limits at
        ``/xrmmap/config/rois/limits``. One of
        :data:`RoiLimitUnits`. Replaces the previous numeric
        ``roi_limit_scale`` field — the scale is now derived from
        the resolved ``energy_scale`` when units are
        ``"channel_index"``, fixed at ``0.01`` for ``"centi_keV"``,
        and identity for ``"keV"``.
    field_width_um, field_height_um
        Total map extent in µm along the navigation X / Y axes.
        When set, the reader uses ``field_width_um / xdim`` as the
        navigation pixel scale rather than consulting the environ
        beam-size key. Either may be omitted independently.
    pixel_size_um
        Direct navigation pixel scale in µm. If set, takes priority
        over ``field_width_um`` / ``field_height_um`` / environ-table
        ``beam_size`` for the reported axis scale.
    legacy_field_width_um
        Total map width in µm used as the legacy fallback when no
        beam size is in the environ table and no explicit
        ``field_width_um`` / ``pixel_size_um`` is supplied. Audit-
        confirmed as **scan-field extent**, not beam size; ``500.0``
        is the legacy value for the inherited ``ISE_500sqaures_…``
        files. Renamed in Chunk 18 from the misleading
        ``fallback_field_width_um``.
    roi_variant_index
        Variant axis index for ROI limits stored as
        ``(n_rois, n_variants, 2)`` (per-detector or per-fit-pass).
        Defaults to ``0`` on the legacy preset.
    """

    energy_scale: float | None = None
    roi_limit_units: RoiLimitUnits | None = None
    field_width_um: float | None = None
    field_height_um: float | None = None
    pixel_size_um: float | None = None
    legacy_field_width_um: float | None = None
    roi_variant_index: int | None = None


#: Calibration preset for the AXIOMM-inherited APS / GSECARS
#: 13-ID-E XRM-Map dataset. Confirmed by the 2026-06-12 metadata
#: audit on ``~/Desktop/research/melts/data/Maps-HDF5/`` —
#: ``/xrmmap`` attribute ``Beamline = 'GSECARS, 13-IDE / APS'``,
#: ``mca_calib/slope = 0.01`` per channel, 4096-channel MCA,
#: integer ROI limits at ``/xrmmap/config/rois/limits`` are
#: channel indices (so ``roi_limit_units = "channel_index"``), and
#: scan-field width 500 µm for the ``500sqaures`` family.
#:
#: This preset is consulted by
#: :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Reader`
#: only when :class:`~axiomm.io.converters.calibration
#: .ConversionMode` is ``LEGACY`` / ``GENERIC`` / ``DIAGNOSTIC``;
#: ``STRICT`` mode refuses to apply it. Every preset-derived value
#: shows up under ``signal.metadata.AXIOMM.calibration.*`` with
#: ``source = "legacy_preset"`` so post-hoc inspection can tell
#: every preset-derived value apart from user-supplied ones.
XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1: XRMMapH5Calibration = XRMMapH5Calibration(
    energy_scale=40.96 / 4096,
    roi_limit_units="channel_index",
    legacy_field_width_um=500.0,
    roi_variant_index=0,
)


# ---------------------------------------------------------------------------
# Minimal preset registry (lazy ``"module:attr"`` factories)
# ---------------------------------------------------------------------------
#
# Future presets (e.g. other beamlines, instrument generations) plug
# in here. The registry mirrors the reader/writer registry pattern
# from Chunk 12: register a ``"module:attr"`` lookup string rather
# than the value itself, so adding a preset doesn't force importing
# every preset on package startup.

_PRESETS: dict[str, str] = {
    "xrmmap_legacy_aps_13_id_e_v1":
        "axiomm.io.converters.presets:XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1",
}


def get_preset(name: str) -> XRMMapH5Calibration:
    """Return the registered calibration preset by name.

    Raises ``KeyError`` if ``name`` is not registered. Names are
    case-sensitive and follow the short-kebab-snake hybrid the
    reader/writer registries use.
    """
    if name not in _PRESETS:
        raise KeyError(
            f"Unknown calibration preset {name!r}. "
            f"Registered presets: {sorted(_PRESETS)}."
        )
    target = _PRESETS[name]
    module_name, attr = target.split(":", 1)
    return getattr(importlib.import_module(module_name), attr)


def iter_presets() -> list[str]:
    """Return the names of all registered calibration presets."""
    return sorted(_PRESETS)


def register_preset(name: str, target: str) -> None:
    """Register a new calibration preset under ``name``.

    ``target`` is a ``"module.path:attr"`` string pointing at a
    :class:`XRMMapH5Calibration` instance — the same lazy-import
    convention the reader registry uses.
    """
    _PRESETS[name] = target


__all__ = [
    "RoiLimitUnits",
    "XRMMapH5Calibration",
    "XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1",
    "get_preset",
    "iter_presets",
    "register_preset",
]
