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


@dataclass(frozen=True)
class XRMMapH5Calibration:
    """Scientific calibration values consumed by
    :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Reader`.

    Every field defaults to ``None``. The reader's resolution ladder
    treats ``None`` as **"not user-supplied"** and falls back to the
    active preset (legacy mode), emits a warning (generic mode), or
    raises :class:`~axiomm.io.converters.errors
    .CalibrationUnresolvedError` (strict mode). A non-``None`` value
    is treated as ``CalibrationSource.USER_CONFIG`` and always wins
    over the preset.

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
        dataset stores `0.01 keV/channel` at
        ``/xrmmap/config/mca_calib/slope``; the preset reproduces
        that value as ``40.96 / 4096``. Chunk 18 reads this directly
        from the source HDF5 metadata when available.
    roi_limit_scale
        Multiplier applied to integer ROI limits at
        ``/xrmmap/config/rois/limits``. For the legacy dataset this
        is ``0.01`` and converts MCA channel indices to keV (it
        numerically coincides with ``mca_calib/slope``).
    fallback_field_width_um
        Total map field width in µm used when no beam-size value is
        present in the environ table. Audit-confirmed as scan-field
        extent, **not** beam size; ``500.0`` is the legacy fallback
        for the inherited ``ISE_500sqaures_…`` files. Chunk 18
        replaces this with an explicit ``field_width_um`` /
        ``pixel_size_um`` pair.
    roi_variant_index
        Variant axis index for ROI limits stored as
        ``(n_rois, n_variants, 2)`` (per-detector or per-fit-pass).
        Defaults to ``0`` on the legacy preset.
    """

    energy_scale: float | None = None
    roi_limit_scale: float | None = None
    fallback_field_width_um: float | None = None
    roi_variant_index: int | None = None


#: Calibration preset for the AXIOMM-inherited APS / GSECARS
#: 13-ID-E XRM-Map dataset. Confirmed by the 2026-06-12 metadata
#: audit on ``~/Desktop/research/melts/data/Maps-HDF5/`` —
#: ``/xrmmap`` attribute ``Beamline = 'GSECARS, 13-IDE / APS'``,
#: ``mca_calib/slope = 0.01`` per channel, 4096-channel MCA,
#: scan-field width 500 µm for the ``500sqaures`` family.
#:
#: This preset is consulted by
#: :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Reader`
#: only when :class:`~axiomm.io.converters.calibration
#: .ConversionMode` is ``LEGACY`` / ``GENERIC`` / ``DIAGNOSTIC``;
#: ``STRICT`` mode refuses to apply it. The preset value still
#: shows up under ``signal.metadata.AXIOMM.calibration.*.value``
#: with ``source = "legacy_preset"`` so post-hoc inspection can
#: tell every preset-derived value apart from user-supplied ones.
XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1: XRMMapH5Calibration = XRMMapH5Calibration(
    energy_scale=40.96 / 4096,
    roi_limit_scale=0.01,
    fallback_field_width_um=500.0,
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
    "XRMMapH5Calibration",
    "XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1",
    "get_preset",
    "iter_presets",
    "register_preset",
]
