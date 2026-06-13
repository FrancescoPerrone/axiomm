"""Generic schema-driven HDF5 map reader (Chunk 14, spec §23 Phase 3).

:class:`GenericHDF5MapReader` consumes an :class:`HDF5MapSchema` to
read an XRM-shaped HDF5 file (3-D counts + optional environ / ROI
metadata) at *any* set of HDF5 paths. It is the alternative to
writing a bespoke `Reader` subclass when a new instrument format is
structurally identical to XRM-Map but stores the same pieces at
different paths.

For formats that diverge structurally — multiple counts datasets,
non-trailing signal axis, no environ table at all — a bespoke
Reader class remains the right choice.

The reader produces the same neutral :class:`AxiommSignalPayload`
and provenance-classification structure that :class:`XRMMapH5Reader`
does, so downstream code (builder, writer, manifest) doesn't care
which reader populated the payload.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from axiomm import __version__ as _axiomm_version
from axiomm.io.converters.calibration import (
    CalibrationSource,
    ConversionMode,
    ResolvedValue,
)
from axiomm.io.converters.errors import (
    CalibrationUnresolvedError,
    DatasetNotFoundError,
)
from axiomm.io.converters.presets import RoiLimitUnits
from axiomm.io.converters.metadata import (
    nest_classification,
    nest_converter_section,
)
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)
from axiomm.io.converters.readers.hdf5_helpers import (
    compute_roi_scale_from_units,
    raise_if_strict_unresolved,
    read_environ_table,
    read_roi_table,
    resolve_energy_scale,
    resolve_navigation_scale,
    resolve_navigation_scale_calibration,
    resolve_roi_limit_interpretation,
)
from axiomm.io.converters.readers.hdf5_schema import HDF5MapSchema

try:
    import h5py
except ImportError:  # pragma: no cover - exercised when h5py is absent
    h5py = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


_H5PY_INSTALL_HINT = (
    "h5py is required for GenericHDF5MapReader. "
    "Install with `pip install axiomm[hdf5]` or `pip install h5py`."
)


def _require_h5py() -> None:
    if h5py is None:
        raise ImportError(_H5PY_INSTALL_HINT)


# ---------------------------------------------------------------------------
# Scientific defaults
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HDF5MapCalibration:
    """Scientific calibration values for :class:`GenericHDF5MapReader`.

    Deliberately separate from :class:`HDF5MapSchema`:

    * Schema = *where* data lives in the file (HDF5 paths, axis names).
    * Calibration = *what each value means* (per-channel energy width,
      ROI unit interpretation, navigation pixel scale, which ROI
      variant to pick).

    Keeping the two apart lets the same schema describe several
    instrument generations whose calibration constants differ.

    Every field defaults to ``None`` (Phase 4, Chunk 18). The reader's
    resolution ladder treats ``None`` as "not user-supplied" — the
    generic reader has **no named preset** of its own, so unresolved
    fields in non-strict modes are flagged ``UNKNOWN`` with a
    diagnostic; strict mode raises
    :class:`~axiomm.io.converters.errors.CalibrationUnresolvedError`.

    Renamed from ``HDF5MapConfig`` in Chunk 18 for naming symmetry
    with :class:`~axiomm.io.converters.presets.XRMMapH5Calibration`.

    Attributes
    ----------
    energy_scale
        Per-MCA-channel energy width in keV.
    roi_limit_units
        Explicit unit interpretation of integer ROI limits. One of
        :data:`~axiomm.io.converters.presets.RoiLimitUnits`. Replaces
        the previous numeric ``roi_limit_scale`` field.
    field_width_um, field_height_um
        Total map extent in µm. When set, the reader uses
        ``field_width_um / xdim`` as the navigation pixel scale.
    pixel_size_um
        Direct navigation pixel scale in µm. Takes priority over
        ``field_width_um`` / ``field_height_um`` / environ ``beam_size``.
    legacy_field_width_um
        Legacy fallback width in µm. The generic reader doesn't ship
        a preset, so this is purely user-controlled.
    roi_variant_index
        Variant axis index for ROI limits stored as
        ``(n_rois, n_variants, 2)``.
    """

    energy_scale: float | None = None
    roi_limit_units: RoiLimitUnits | None = None
    field_width_um: float | None = None
    field_height_um: float | None = None
    pixel_size_um: float | None = None
    legacy_field_width_um: float | None = None
    roi_variant_index: int | None = None


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class GenericHDF5MapReader:
    """Schema-driven reader for XRM-shaped HDF5 map files.

    Parameters
    ----------
    schema
        :class:`HDF5MapSchema` naming the HDF5 paths.
    calibration
        :class:`HDF5MapCalibration` with scientific defaults. ``None``
        uses :class:`HDF5MapCalibration` field defaults (all
        ``None``). Renamed from ``config`` in Chunk 18.
    name
        Stable identifier for the registry / for the ``reader``
        argument to :func:`convert_file`. Defaults to
        ``"generic_hdf5_map"``; pass a more specific name if you
        plan to register several instances under different schemas.
    mode
        :class:`~axiomm.io.converters.calibration.ConversionMode`
        controlling the resolution ladder. **Defaults to**
        :attr:`~axiomm.io.converters.calibration.ConversionMode
        .GENERIC` since Chunk 18 — the generic reader is the
        public-release default and refuses silent legacy fallbacks
        out of the box.
    """

    supported_extensions = (".h5", ".hdf5")

    def __init__(
        self,
        *,
        schema: HDF5MapSchema,
        calibration: HDF5MapCalibration | None = None,
        name: str = "generic_hdf5_map",
        mode: ConversionMode = ConversionMode.GENERIC,
    ) -> None:
        self.schema = schema
        self.calibration = (
            calibration if calibration is not None else HDF5MapCalibration()
        )
        self.name = name
        self.mode = mode

    # Backwards-readable alias: some manifest tooling probes ``reader.config``.
    @property
    def config(self) -> HDF5MapCalibration:
        return self.calibration

    # -- Reader protocol ----------------------------------------------------

    def can_read(self, path: str | Path) -> bool:
        """Cheap probe: extension + signature peek at ``schema.counts_path``."""
        p = Path(path)
        if p.suffix.lower() not in self.supported_extensions:
            return False
        if not p.is_file():
            return False
        if h5py is None:
            return False
        try:
            with h5py.File(p, "r") as f:
                return self.schema.counts_path in f
        except (OSError, KeyError):
            return False

    def read(self, path: str | Path, *, lazy: bool = True) -> AxiommSignalPayload:
        """Read ``path`` and return a populated :class:`AxiommSignalPayload`."""
        _require_h5py()

        source_path = Path(path)
        diagnostics: list[Diagnostic] = []
        original_metadata: dict[str, Any] = {}
        classification: dict[str, list[str]] = {
            "observed": [],
            "inferred": [],
            "assumed": [],
        }

        logger.info(
            "GenericHDF5MapReader(name=%s).read(%s, lazy=%s)",
            self.name, source_path, lazy,
        )

        if lazy:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="lazy_downgraded_to_eager",
                    message=(
                        "lazy=True requested but the generic HDF5 map "
                        "reader materialises counts eagerly; lazy "
                        "support is tracked for a later chunk."
                    ),
                )
            )

        with h5py.File(source_path, "r") as f:
            if self.schema.counts_path not in f:
                raise DatasetNotFoundError(
                    f"Counts dataset not found at "
                    f"{self.schema.counts_path!r} in {source_path}. "
                    f"Pass GenericHDF5MapReader(schema=HDF5MapSchema("
                    f"counts_path=...)) with the correct path."
                )
            data = np.asarray(f[self.schema.counts_path][...])
            if data.ndim != 3:
                raise DatasetNotFoundError(
                    f"Counts dataset at {self.schema.counts_path!r} has "
                    f"unexpected shape {data.shape!r}; expected a 3-D "
                    f"array (xdim, ydim, n_channels)."
                )
            xdim, ydim, n_channels = data.shape

            classification["observed"].append(
                f"data (HDF5 dataset {self.schema.counts_path!r})"
            )
            classification["inferred"].extend([
                f"axes.{self.schema.navigation_x_name}.size (= data.shape[0])",
                f"axes.{self.schema.navigation_y_name}.size (= data.shape[1])",
                f"axes.{self.schema.energy_axis_name}.size (= data.shape[2])",
            ])

            environ, environ_diag = read_environ_table(
                f,
                name_path=self.schema.environ_name_path,
                value_path=self.schema.environ_value_path,
            )
            diagnostics.extend(environ_diag)
            if environ:
                original_metadata["environ"] = dict(environ)
                classification["observed"].append(
                    f"metadata.environ ({len(environ)} keys from HDF5)"
                )

        # Resolve calibration first so the ROI multiplier can come from
        # the resolved units + energy_scale (Phase 4, Chunk 18 unification).
        energy_scale_rv = resolve_energy_scale(
            user_value=self.calibration.energy_scale,
            preset_value=None,
            mode=self.mode,
        )
        roi_units_rv = resolve_roi_limit_interpretation(
            user_units=self.calibration.roi_limit_units,
            preset_units=None,
            mode=self.mode,
        )
        nav_scale_rv, scale_diag = resolve_navigation_scale_calibration(
            environ,
            beam_size_key=self.schema.beam_size_key,
            user_pixel_size_um=self.calibration.pixel_size_um,
            user_field_width_um=self.calibration.field_width_um,
            preset_legacy_field_width_um=self.calibration.legacy_field_width_um,
            xdim=xdim,
            mode=self.mode,
        )
        diagnostics.extend(scale_diag)

        # Effective scalars for the actual computation paths.
        effective_roi_scale = (
            compute_roi_scale_from_units(
                roi_units_rv.value,
                energy_scale_rv.value,
            )
            if roi_units_rv.source is not CalibrationSource.UNKNOWN
            else None
        )
        effective_roi_variant_index = (
            self.calibration.roi_variant_index
            if self.calibration.roi_variant_index is not None
            else 0
        )

        # ROI table reading still happens inside the file context above —
        # re-open the file for the second pass.
        with h5py.File(source_path, "r") as f:
            rois, roi_diag = read_roi_table(
                f,
                name_path=self.schema.roi_name_path,
                limits_path=self.schema.roi_limits_path,
                roi_variant_index=effective_roi_variant_index,
                roi_limit_scale=(
                    effective_roi_scale if effective_roi_scale is not None
                    else 1.0
                ),
            )
        diagnostics.extend(roi_diag)
        if rois:
            original_metadata["rois"] = rois
            classification["observed"].append(
                f"metadata.rois ({len(rois)} entries from HDF5; "
                f"limits scaled by resolved roi_limit_units="
                f"{roi_units_rv.value!r})"
            )
            classification["assumed"].append(
                f"metadata.rois.*.start/end (effective scale="
                f"{effective_roi_scale} applied to raw integer limits)"
            )

        # Map nav scale source onto the legacy provenance bucket.
        nav_scale_um = nav_scale_rv.value
        nav_scale_bucket = (
            "observed"
            if nav_scale_rv.source is CalibrationSource.SOURCE_METADATA
            else "assumed"
        )
        classification[nav_scale_bucket].append(
            f"axes.{self.schema.navigation_x_name}.scale, "
            f"axes.{self.schema.navigation_y_name}.scale "
            f"({nav_scale_rv.note})"
        )

        classification["assumed"].extend([
            f"axes.{self.schema.energy_axis_name}.scale "
            f"(= {energy_scale_rv.value}, "
            f"source={energy_scale_rv.source.value})",
            f"axes.{self.schema.energy_axis_name}.units "
            f"({self.schema.energy_axis_units!r}, schema default)",
            f"axes.{self.schema.navigation_x_name}.units, "
            f"axes.{self.schema.navigation_y_name}.units "
            f"({self.schema.navigation_units!r}, schema default)",
        ])

        axes: tuple[AxisSpec, ...] = (
            AxisSpec(
                name=self.schema.navigation_x_name,
                role="navigation",
                size=xdim,
                units=self.schema.navigation_units,
                scale=nav_scale_um,
                offset=0.0,
                index_in_array=0,
            ),
            AxisSpec(
                name=self.schema.navigation_y_name,
                role="navigation",
                size=ydim,
                units=self.schema.navigation_units,
                scale=nav_scale_um,
                offset=0.0,
                index_in_array=1,
            ),
            AxisSpec(
                name=self.schema.energy_axis_name,
                role="signal",
                size=n_channels,
                units=self.schema.energy_axis_units,
                scale=energy_scale_rv.value,
                offset=0.0,
                index_in_array=2,
            ),
        )

        # --- calibration provenance (Phase 4, Chunks 16–18) ---------------
        resolved_calibration: dict[str, ResolvedValue] = {
            "navigation_scale": nav_scale_rv,
            "energy_scale": energy_scale_rv,
            "roi_limit_units": roi_units_rv,
        }

        # Strict-mode enforcement: any UNKNOWN source raises.
        raise_if_strict_unresolved(self.mode, resolved_calibration)

        # Mode-driven diagnostic severity (info in legacy/diagnostic,
        # warning in generic — generic is the public default after
        # Chunk 18, and the geology-team policy says preset use should
        # be loud there).
        preset_severity: Any = (
            "warning" if self.mode is ConversionMode.GENERIC else "info"
        )
        for source, code, severity, descriptor in (
            (
                CalibrationSource.LEGACY_PRESET,
                "calibration_resolved_from_preset",
                preset_severity,
                "the active legacy preset",
            ),
            (
                CalibrationSource.USER_CONFIG,
                "calibration_resolved_from_user_config",
                "info",
                "explicit user-supplied calibration",
            ),
            (
                CalibrationSource.SOURCE_METADATA,
                "calibration_resolved_from_metadata",
                "info",
                "source-file metadata",
            ),
            (
                CalibrationSource.INFERRED,
                "calibration_inferred",
                "info",
                "heuristic inference from numeric values",
            ),
        ):
            names = sorted(
                n for n, rv in resolved_calibration.items()
                if rv.source is source
            )
            if names:
                diagnostics.append(
                    Diagnostic(
                        severity=severity,
                        code=code,
                        message=(
                            f"Resolved {', '.join(names)} from "
                            f"{descriptor} (mode={self.mode.value})."
                        ),
                        context={
                            "keys": names,
                            "mode": self.mode.value,
                        },
                    )
                )

        # Manifest / signal metadata carries the schema, calibration,
        # and mode together — the manifest writer doesn't need to know
        # which reader produced the payload.
        combined_config = {
            "schema": asdict(self.schema),
            "calibration": asdict(self.calibration),
            "mode": self.mode.value,
        }

        metadata: dict[str, Any] = {
            "AXIOMM": {
                "converter": nest_converter_section(
                    reader_name=self.name,
                    reader_version=_axiomm_version,
                    config=combined_config,
                ),
                "provenance_classification": nest_classification(classification),
            },
        }

        provenance = SourceProvenance(
            path=source_path,
            reader=self.name,
            reader_version=_axiomm_version,
        )

        return AxiommSignalPayload(
            data=data,
            axes=axes,
            signal_kind="signal1d",
            metadata=metadata,
            original_metadata=original_metadata,
            provenance=provenance,
            diagnostics=diagnostics,
            title=source_path.stem,
            resolved_calibration=resolved_calibration,
        )


__all__ = [
    "GenericHDF5MapReader",
    "HDF5MapCalibration",
]
