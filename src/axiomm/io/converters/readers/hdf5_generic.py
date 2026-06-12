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
from axiomm.io.converters.errors import DatasetNotFoundError
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
class HDF5MapConfig:
    """Scientific defaults for :class:`GenericHDF5MapReader`.

    Deliberately separate from :class:`HDF5MapSchema`:

    * Schema = *where* data lives in the file (HDF5 paths, axis names).
    * Config = *what it means* (per-channel energy width, ROI scale,
      fallback for missing beam size, which ROI variant to pick).

    Keeping the two apart lets the same schema describe several
    instrument generations whose calibration constants differ.

    The defaults here are deliberately bland (``energy_scale=1.0``,
    ``roi_limit_scale=1.0``, ``fallback_field_width_um=None``) — the
    generic reader has no domain knowledge to lean on. Override every
    field you care about. The XRM-Map-flavoured defaults live on
    :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Config`
    and are the *historical* values from the prototype, themselves
    still pending domain confirmation (see ``docs/user/converter.md``
    -> "Scientific assumptions still requiring owner confirmation").
    """

    energy_scale: float = 1.0
    roi_limit_scale: float = 1.0
    fallback_field_width_um: float | None = None
    roi_variant_index: int = 0


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class GenericHDF5MapReader:
    """Schema-driven reader for XRM-shaped HDF5 map files.

    Parameters
    ----------
    schema
        :class:`HDF5MapSchema` naming the HDF5 paths.
    config
        :class:`HDF5MapConfig` with scientific defaults. ``None``
        uses :class:`HDF5MapConfig` field defaults.
    name
        Stable identifier for the registry / for the ``reader``
        argument to :func:`convert_file`. Defaults to
        ``"generic_hdf5_map"``; pass a more specific name if you
        plan to register several instances under different schemas.
    """

    supported_extensions = (".h5", ".hdf5")

    def __init__(
        self,
        *,
        schema: HDF5MapSchema,
        config: HDF5MapConfig | None = None,
        name: str = "generic_hdf5_map",
        mode: ConversionMode = ConversionMode.LEGACY,
    ) -> None:
        self.schema = schema
        self.config = config or HDF5MapConfig()
        self.name = name
        self.mode = mode

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

            rois, roi_diag = read_roi_table(
                f,
                name_path=self.schema.roi_name_path,
                limits_path=self.schema.roi_limits_path,
                roi_variant_index=self.config.roi_variant_index,
                roi_limit_scale=self.config.roi_limit_scale,
            )
            diagnostics.extend(roi_diag)
            if rois:
                original_metadata["rois"] = rois
                classification["observed"].append(
                    f"metadata.rois ({len(rois)} entries from HDF5; "
                    f"limits scaled by configured roi_limit_scale)"
                )
                classification["assumed"].append(
                    f"metadata.rois.*.start/end (roi_limit_scale="
                    f"{self.config.roi_limit_scale} applied to raw integer limits)"
                )

        # GenericHDF5MapReader has no named legacy preset (it's meant for
        # users to configure per-instrument). Every HDF5MapConfig field
        # the user supplied therefore enters the resolution ladder as
        # USER_CONFIG; preset_value is left None. Chunk 18 splits
        # HDF5MapConfig into a schema/calibration pair to match this
        # reader's role more precisely.
        nav_scale_resolved, scale_diag = resolve_navigation_scale_calibration(
            environ,
            beam_size_key=self.schema.beam_size_key,
            user_fallback_um=self.config.fallback_field_width_um,
            preset_fallback_um=None,
            xdim=xdim,
            mode=self.mode,
        )
        nav_scale_um = nav_scale_resolved.value
        scale_source = {
            CalibrationSource.SOURCE_METADATA: "beam_size",
            CalibrationSource.USER_CONFIG: "fallback",
            CalibrationSource.LEGACY_PRESET: "fallback",
            CalibrationSource.UNKNOWN: "unit",
        }[nav_scale_resolved.source]
        diagnostics.extend(scale_diag)
        nav_scale_bucket = {
            "beam_size": "observed",
            "fallback": "assumed",
            "unit": "assumed",
        }[scale_source]
        nav_scale_descriptor = {
            "beam_size": (
                f"axes.{self.schema.navigation_x_name}.scale, "
                f"axes.{self.schema.navigation_y_name}.scale "
                f"(parsed from environ {self.schema.beam_size_key!r})"
            ),
            "fallback": (
                f"axes.{self.schema.navigation_x_name}.scale, "
                f"axes.{self.schema.navigation_y_name}.scale "
                f"(fallback: fallback_field_width_um="
                f"{self.config.fallback_field_width_um} / xdim={xdim})"
            ),
            "unit": (
                f"axes.{self.schema.navigation_x_name}.scale, "
                f"axes.{self.schema.navigation_y_name}.scale "
                f"(no beam size, no fallback: defaulted to 1.0)"
            ),
        }[scale_source]
        classification[nav_scale_bucket].append(nav_scale_descriptor)

        classification["assumed"].extend([
            f"axes.{self.schema.energy_axis_name}.scale "
            f"(= {self.config.energy_scale}, config default)",
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
                scale=self.config.energy_scale,
                offset=0.0,
                index_in_array=2,
            ),
        )

        # --- calibration provenance (Phase 4, Chunks 16–17) ---------------
        resolved_calibration: dict[str, ResolvedValue] = {
            "navigation_scale": nav_scale_resolved,
            "energy_scale": resolve_energy_scale(
                user_value=self.config.energy_scale,
                preset_value=None,
                mode=self.mode,
            ),
            "roi_limit_units": resolve_roi_limit_interpretation(
                user_value=self.config.roi_limit_scale,
                preset_value=None,
                mode=self.mode,
            ),
        }
        user_config_names = sorted(
            name for name, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.USER_CONFIG
        )
        if user_config_names:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="calibration_resolved_from_user_config",
                    message=(
                        f"Resolved {', '.join(user_config_names)} from "
                        f"the HDF5MapConfig values supplied to "
                        f"GenericHDF5MapReader (mode={self.mode.value})."
                    ),
                    context={
                        "keys": user_config_names,
                        "mode": self.mode.value,
                    },
                )
            )
        metadata_resolved_names = sorted(
            name for name, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.SOURCE_METADATA
        )
        if metadata_resolved_names:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="calibration_resolved_from_metadata",
                    message=(
                        f"Resolved {', '.join(metadata_resolved_names)} "
                        f"from source-file metadata (mode={self.mode.value})."
                    ),
                    context={
                        "keys": metadata_resolved_names,
                        "mode": self.mode.value,
                    },
                )
            )
        inferred_names = sorted(
            name for name, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.INFERRED
        )
        if inferred_names:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="calibration_inferred",
                    message=(
                        f"Inferred {', '.join(inferred_names)} from numeric "
                        f"config values (mode={self.mode.value}); see each "
                        f"resolved_calibration entry's note for the rule. "
                        f"Supply explicit calibration to override."
                    ),
                    context={"keys": inferred_names, "mode": self.mode.value},
                )
            )

        # Manifest / signal metadata carries the schema and the
        # scientific config together — the manifest writer doesn't need
        # to know which reader produced the payload; it just serialises
        # whatever is under metadata['AXIOMM']['converter']['config'].
        combined_config = {
            "schema": asdict(self.schema),
            "config": asdict(self.config),
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
    "HDF5MapConfig",
]
