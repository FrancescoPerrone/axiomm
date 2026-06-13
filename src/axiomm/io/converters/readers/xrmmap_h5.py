"""XRM-map HDF5 reader for the AXIOMM converter.

:class:`XRMMapH5Reader` is the first concrete reader inside AXIOMM. It opens
XRM-map style HDF5 files — the format produced by the prototype's original
target instrument — and returns a populated
:class:`~axiomm.io.converters.models.AxiommSignalPayload`.

Reader configuration is split in two (Phase 4, Chunk 17):

* **Schema** — :class:`~axiomm.io.converters.readers.hdf5_schema
  .HDF5MapSchema` — names *where* each piece of metadata lives in the
  HDF5 file. The package-level :data:`~axiomm.io.converters.readers
  .hdf5_schema.XRMMAP_H5_SCHEMA` constant carries the canonical
  XRM-Map / Larch paths and is the reader's default.
* **Calibration** — :class:`~axiomm.io.converters.presets
  .XRMMapH5Calibration` — names *what each value means*: the
  per-channel energy width, the ROI-limit scale, the spatial
  fallback. Every field defaults to ``None`` so the resolution
  ladder can distinguish user-supplied calibration from
  preset/inferred values. The named preset
  :data:`~axiomm.io.converters.presets
  .XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1` carries the historic AXIOMM
  values and is consulted by the reader only when the active
  :class:`~axiomm.io.converters.calibration.ConversionMode` allows
  it.

Optional metadata that is missing becomes a structured
:class:`~axiomm.io.converters.models.Diagnostic` on the payload rather than
crashing the conversion (spec §7.8). Only a missing primary counts dataset
is fatal: that raises
:class:`~axiomm.io.converters.errors.DatasetNotFoundError`, with an error
message that names the path and the schema field to override. In
:class:`~axiomm.io.converters.calibration.ConversionMode.STRICT` a
calibration value that cannot be resolved raises
:class:`~axiomm.io.converters.errors.CalibrationUnresolvedError`.

See spec §7, §17, §20.1 (the spec's combined ``XRMMapH5Config`` was
split per Phase-4 Chunk 17; the schema / calibration concepts live on
in the two new dataclasses).
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
    MetadataParseError,
)
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
from axiomm.io.converters.presets import (
    XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1,
    XRMMapH5Calibration,
)
from axiomm.io.converters.readers.hdf5_schema import (
    HDF5MapSchema,
    XRMMAP_H5_SCHEMA,
)

try:
    import h5py
except ImportError:  # pragma: no cover - exercised in environments without h5py
    h5py = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import h5py as _h5py_typing  # noqa: F401


logger = logging.getLogger(__name__)


_H5PY_INSTALL_HINT = (
    "h5py is required for XRMMapH5Reader. "
    "Install with `pip install axiomm[hdf5]` or `pip install h5py`."
)


def _require_h5py() -> None:
    if h5py is None:
        raise ImportError(_H5PY_INSTALL_HINT)


# ---------------------------------------------------------------------------
# String decoding helpers (spec §7.6)
# ---------------------------------------------------------------------------

def decode_hdf5_string(value: object) -> str:
    """Decode a single HDF5 string value to a Python ``str``.

    Accepts: raw ``bytes`` (fixed-width or variable-length), null-padded byte
    strings, NumPy bytes scalars (``np.bytes_``), 0-dimensional NumPy bytes
    arrays, and already-decoded ``str``.

    Any other type raises :class:`TypeError`.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, np.bytes_)):
        return bytes(value).rstrip(b"\x00").decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray) and value.shape == ():
        return decode_hdf5_string(value.item())
    raise TypeError(
        f"Cannot decode HDF5 string from {type(value).__name__}: {value!r}"
    )


def decode_hdf5_string_array(values: object) -> list[str]:
    """Decode an HDF5 string dataset into a list of Python ``str``s.

    Accepts NumPy arrays, h5py datasets read as arrays (``ds[:]``), lists, or
    tuples whose elements are decodable by :func:`decode_hdf5_string`.
    """
    if hasattr(values, "tolist") and not isinstance(values, (bytes, bytearray, str)):
        values = values.tolist()
    if not isinstance(values, (list, tuple)):
        raise TypeError(
            f"Cannot decode HDF5 string array from {type(values).__name__}"
        )
    return [decode_hdf5_string(v) for v in values]


# ---------------------------------------------------------------------------
# Beam-size parsing (spec §7.7)
# ---------------------------------------------------------------------------

# Optional sign, a number, optional whitespace, optional micrometre unit
# (um, µm with U+00B5, μm with Greek mu U+03BC, micrometre, micrometer).
_MICROMETRE_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<value>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
    \s*
    (?:um|µm|μm|micrometre|micrometer)?
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)


def parse_micrometre_value(value: str) -> float:
    """Parse a beam-size / scale string in micrometres into a ``float``.

    Accepts the variants documented in spec §7.7: ``"1um"``, ``"1 um"``,
    ``"1 µm"``, ``"1 μm"``, ``"1.0um"``, ``"1.0 micrometre"``,
    ``"1.0 micrometer"``. A bare numeric string (``"1"``) is also accepted,
    interpreted as already in micrometres.

    The result is required to be **strictly positive** — a physical
    micrometre length cannot be zero or negative. Zero/negative values
    raise :class:`MetadataParseError`, so they flow through the same
    fall-back path as malformed inputs at the call site (the
    ``beam_size_unparseable`` diagnostic in the reader).
    """
    if not isinstance(value, str):
        raise MetadataParseError(
            f"Expected string for micrometre value, got "
            f"{type(value).__name__}: {value!r}"
        )
    match = _MICROMETRE_PATTERN.match(value)
    if match is None:
        raise MetadataParseError(f"Cannot parse micrometre value: {value!r}")
    parsed = float(match.group("value"))
    if not parsed > 0:
        raise MetadataParseError(
            f"Micrometre value must be strictly positive; got "
            f"{value!r} -> {parsed}."
        )
    return parsed


# ---------------------------------------------------------------------------
# Reader (spec §7)
# ---------------------------------------------------------------------------

_LEGACY_PRESET: XRMMapH5Calibration = XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1


class XRMMapH5Reader:
    """Reader for XRM-map style HDF5 files.

    Parameters
    ----------
    schema
        :class:`~axiomm.io.converters.readers.hdf5_schema.HDF5MapSchema`
        naming the HDF5 paths to read. ``None`` uses
        :data:`~axiomm.io.converters.readers.hdf5_schema.XRMMAP_H5_SCHEMA`
        — the canonical XRM-Map / Larch layout.
    calibration
        :class:`~axiomm.io.converters.presets.XRMMapH5Calibration`
        with explicit scientific values. ``None`` (and every
        ``None`` field) is treated as "not user-supplied" so the
        resolution ladder can distinguish user intent from absent
        config. The defaults of an explicit
        ``XRMMapH5Calibration()`` are all ``None``.
    mode
        :class:`~axiomm.io.converters.calibration.ConversionMode`
        controlling the resolution ladder. **Defaults to**
        :attr:`~axiomm.io.converters.calibration.ConversionMode.GENERIC`
        since Phase 4, Chunk 18 — the public-release default. Preset
        fallback still applies but at warning severity. Switch to
        ``LEGACY`` to silence the warnings on inherited files, or
        ``STRICT`` to refuse preset fallbacks entirely.

    The ladder, per field:

    1. **USER_CONFIG** — non-``None`` field on ``calibration``.
    2. **LEGACY_PRESET** — the named preset (legacy / generic /
       diagnostic modes only).
    3. **UNKNOWN** — raises
       :class:`~axiomm.io.converters.errors
       .CalibrationUnresolvedError` in strict mode; otherwise marks
       the value unresolved with a diagnostic.

    For ROI limits the calibration carries a ``roi_limit_units``
    token (Chunk 18; one of ``"centi_keV"`` / ``"keV"`` /
    ``"channel_index"``); the numeric scale is derived from the
    resolved unit + ``energy_scale``. For spatial calibration the
    Chunk-18 ladder consults, in order: environ ``beam_size``
    (source metadata) → ``pixel_size_um`` (user config) →
    ``field_width_um / xdim`` (user config) →
    ``legacy_field_width_um / xdim`` (legacy preset).
    """

    name = "xrmmap_h5"
    supported_extensions = (".h5", ".hdf5")

    def __init__(
        self,
        *,
        schema: HDF5MapSchema | None = None,
        calibration: XRMMapH5Calibration | None = None,
        mode: ConversionMode = ConversionMode.GENERIC,
    ) -> None:
        self.schema = schema if schema is not None else XRMMAP_H5_SCHEMA
        self.calibration = (
            calibration if calibration is not None else XRMMapH5Calibration()
        )
        self.mode = mode

    # -- Reader protocol ----------------------------------------------------

    def can_read(self, path: str | Path) -> bool:
        """Return ``True`` if this reader can read ``path``.

        Cheap two-stage check: file extension match, then a signature peek
        confirming the configured counts dataset exists. Returns ``False``
        (without raising) on any failure so auto-detection callers can fall
        back to other readers.
        """
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
        """Read ``path`` and return a populated :class:`AxiommSignalPayload`.

        The MVP materialises the counts dataset into a NumPy array
        regardless of ``lazy``; a ``lazy_downgraded_to_eager`` diagnostic
        records that the lazy request was downgraded (spec §16). True lazy
        support is a future chunk.

        Raises
        ------
        DatasetNotFoundError
            The configured counts dataset is missing from the file. The
            message names the path and the schema field to override.
        CalibrationUnresolvedError
            ``mode=ConversionMode.STRICT`` and one or more calibration
            values could not be resolved from explicit user config. The
            message lists the unresolved fields and how to provide them.
        """
        _require_h5py()

        source_path = Path(path)
        diagnostics: list[Diagnostic] = []
        original_metadata: dict[str, Any] = {}
        # Spec §15: classify every recorded scientific-metadata field as
        # observed (read directly from the file), inferred (computed from
        # observed values, e.g. axis sizes from the data shape), or
        # assumed (config defaults / fallbacks with no source in the file).
        classification: dict[str, list[str]] = {
            "observed": [],
            "inferred": [],
            "assumed": [],
        }

        logger.info(
            "XRMMapH5Reader.read(%s, lazy=%s, mode=%s)",
            source_path, lazy, self.mode.value,
        )

        if lazy:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="lazy_downgraded_to_eager",
                    message=(
                        "lazy=True requested but XRMMapH5Reader's MVP "
                        "materialises counts eagerly; lazy support is "
                        "tracked for a later chunk."
                    ),
                )
            )

        # Resolve the underlying scalar values via the ladder *before*
        # touching the HDF5 file, so we can pass the effective
        # roi_limit_scale into read_roi_table.
        from axiomm.io.converters.readers.hdf5_helpers import (
            compute_roi_scale_from_units,
            raise_if_strict_unresolved,
            read_environ_table,
            read_roi_table,
            resolve_energy_scale,
            resolve_navigation_scale_calibration,
            resolve_roi_limit_interpretation,
        )

        energy_scale_resolved = resolve_energy_scale(
            user_value=self.calibration.energy_scale,
            preset_value=_LEGACY_PRESET.energy_scale,
            mode=self.mode,
        )
        roi_units_resolved = resolve_roi_limit_interpretation(
            user_units=self.calibration.roi_limit_units,
            preset_units=_LEGACY_PRESET.roi_limit_units,
            mode=self.mode,
        )
        # Effective scale for the integer→keV multiplication; derived
        # from the resolved unit token + energy_scale.
        effective_roi_scale = (
            compute_roi_scale_from_units(
                roi_units_resolved.value,
                energy_scale_resolved.value,
            )
            if roi_units_resolved.source is not CalibrationSource.UNKNOWN
            else None
        )
        effective_roi_variant_index = self._effective_scalar(
            user_value=self.calibration.roi_variant_index,
            preset_value=_LEGACY_PRESET.roi_variant_index,
            default=0,
        )

        with h5py.File(source_path, "r") as f:
            # --- counts (required) ----------------------------------------
            if self.schema.counts_path not in f:
                raise DatasetNotFoundError(
                    f"Counts dataset not found at "
                    f"{self.schema.counts_path!r} in {source_path}. "
                    f"If this XRM file stores counts elsewhere, pass "
                    f"XRMMapH5Reader(schema=replace(XRMMAP_H5_SCHEMA, "
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

            # Counts come directly from the file.
            classification["observed"].append(
                f"data (HDF5 dataset {self.schema.counts_path!r})"
            )
            # Axis sizes are inferred from the data shape.
            classification["inferred"].extend([
                f"axes.{self.schema.navigation_x_name}.size (= data.shape[0])",
                f"axes.{self.schema.navigation_y_name}.size (= data.shape[1])",
                f"axes.{self.schema.energy_axis_name}.size (= data.shape[2])",
            ])

            # --- environ / configuration table (optional) -----------------
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

            # --- ROI table (optional) -------------------------------------
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
                    f"limits scaled per resolved roi_limit_units="
                    f"{roi_units_resolved.value!r})"
                )
                classification["assumed"].append(
                    f"metadata.rois.*.start/end (effective scale="
                    f"{effective_roi_scale} applied to raw integer limits)"
                )

        # --- navigation scale (after the file is closed) -----------------
        nav_scale_resolved, scale_diag = resolve_navigation_scale_calibration(
            environ,
            beam_size_key=self.schema.beam_size_key,
            user_pixel_size_um=self.calibration.pixel_size_um,
            user_field_width_um=self.calibration.field_width_um,
            preset_legacy_field_width_um=(
                _LEGACY_PRESET.legacy_field_width_um
            ),
            xdim=xdim,
            mode=self.mode,
        )
        nav_scale_um = nav_scale_resolved.value
        diagnostics.extend(scale_diag)

        # Map nav scale source to the legacy provenance-classification bucket.
        nav_scale_bucket = (
            "observed"
            if nav_scale_resolved.source is CalibrationSource.SOURCE_METADATA
            else "assumed"
        )
        classification[nav_scale_bucket].append(
            f"axes.{self.schema.navigation_x_name}.scale, "
            f"axes.{self.schema.navigation_y_name}.scale "
            f"({nav_scale_resolved.note})"
        )

        # The energy axis scale / units are config/preset-driven (no source
        # metadata extraction yet — that lands in Chunk 18).
        classification["assumed"].extend([
            f"axes.{self.schema.energy_axis_name}.scale "
            f"(= {energy_scale_resolved.value}, "
            f"source={energy_scale_resolved.source.value})",
            f"axes.{self.schema.energy_axis_name}.units "
            f"({self.schema.energy_axis_units!r}, schema default)",
            f"axes.{self.schema.navigation_x_name}.units, "
            f"axes.{self.schema.navigation_y_name}.units "
            f"({self.schema.navigation_units!r}, schema default)",
        ])

        # --- calibration provenance (Phase 4, Chunks 15–17) ---------------
        resolved_calibration: dict[str, ResolvedValue] = {
            "navigation_scale": nav_scale_resolved,
            "energy_scale": energy_scale_resolved,
            "roi_limit_units": roi_units_resolved,
        }

        # Strict-mode enforcement: any UNKNOWN means we couldn't resolve
        # the value from user config or source metadata. Raise with a
        # message that names what's missing and how to supply it.
        raise_if_strict_unresolved(self.mode, resolved_calibration)

        # Mode-driven diagnostic emission. Severity escalates from info
        # (legacy / diagnostic) to warning (generic) because generic mode
        # represents the public-release default where preset fallbacks
        # *should* be loud.
        preset_severity: Any = (
            "warning" if self.mode is ConversionMode.GENERIC else "info"
        )
        preset_names = sorted(
            n for n, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.LEGACY_PRESET
        )
        if preset_names:
            diagnostics.append(
                Diagnostic(
                    severity=preset_severity,
                    code="calibration_resolved_from_preset",
                    message=(
                        f"Resolved {', '.join(preset_names)} from the "
                        f"named legacy preset "
                        f"XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1 "
                        f"(mode={self.mode.value}). Pass an explicit "
                        f"XRMMapH5Calibration(...) to override."
                    ),
                    context={
                        "keys": preset_names,
                        "mode": self.mode.value,
                        "preset": "xrmmap_legacy_aps_13_id_e_v1",
                    },
                )
            )
        user_config_names = sorted(
            n for n, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.USER_CONFIG
        )
        if user_config_names:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="calibration_resolved_from_user_config",
                    message=(
                        f"Resolved {', '.join(user_config_names)} from "
                        f"explicit user-supplied calibration "
                        f"(mode={self.mode.value})."
                    ),
                    context={
                        "keys": user_config_names,
                        "mode": self.mode.value,
                    },
                )
            )
        metadata_names = sorted(
            n for n, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.SOURCE_METADATA
        )
        if metadata_names:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="calibration_resolved_from_metadata",
                    message=(
                        f"Resolved {', '.join(metadata_names)} from "
                        f"source-file metadata (mode={self.mode.value})."
                    ),
                    context={
                        "keys": metadata_names,
                        "mode": self.mode.value,
                    },
                )
            )
        inferred_names = sorted(
            n for n, rv in resolved_calibration.items()
            if rv.source is CalibrationSource.INFERRED
        )
        if inferred_names:
            diagnostics.append(
                Diagnostic(
                    severity="info",
                    code="calibration_inferred",
                    message=(
                        f"Inferred {', '.join(inferred_names)} from "
                        f"resolved numeric values (mode={self.mode.value}); "
                        f"see each resolved_calibration entry's note for "
                        f"the rule."
                    ),
                    context={
                        "keys": inferred_names,
                        "mode": self.mode.value,
                    },
                )
            )

        # --- axes ----------------------------------------------------------
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
                scale=energy_scale_resolved.value,
                offset=0.0,
                index_in_array=2,
            ),
        )

        # The reader populates the parts of the AXIOMM namespace it owns:
        # the "converter" subsection (reader name/version + the combined
        # schema/calibration dump) and the provenance classification.
        # The builder composes the full nested namespace.
        combined_config: dict[str, Any] = {
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

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _effective_scalar(
        *,
        user_value: Any,
        preset_value: Any,
        default: Any,
    ) -> Any:
        """Return the value to *apply* (not just record) for a calibration
        scalar: user > preset > default. ``default`` is used when nothing
        else resolves — provenance is still flagged ``UNKNOWN`` separately
        by the dedicated resolve_* helper."""
        if user_value is not None:
            return user_value
        if preset_value is not None:
            return preset_value
        return default





__all__ = [
    "XRMMapH5Reader",
    "decode_hdf5_string",
    "decode_hdf5_string_array",
    "parse_micrometre_value",
]
