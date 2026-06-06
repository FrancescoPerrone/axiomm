"""XRM-map HDF5 reader for the AXIOMM converter.

:class:`XRMMapH5Reader` is the first concrete reader inside AXIOMM. It opens
XRM-map style HDF5 files — the format produced by the prototype's original
target instrument — and returns a populated
:class:`~axiomm.io.converters.models.AxiommSignalPayload`.

Every HDF5 path the reader touches is a field of :class:`XRMMapH5Config`
(spec §7.5), so XRM files that share the conceptual layout but use different
paths can be read by passing a configured reader, without subclassing.
Optional metadata that is missing becomes a structured
:class:`~axiomm.io.converters.models.Diagnostic` on the payload rather than
crashing the conversion (spec §7.8). Only a missing primary counts dataset
is fatal: that raises
:class:`~axiomm.io.converters.errors.DatasetNotFoundError`, with an error
message that names the path and the config field to override.

See spec §7, §17, §20.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from axiomm import __version__ as _axiomm_version
from axiomm.io.converters.errors import (
    DatasetNotFoundError,
    MetadataParseError,
)
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)

try:
    import h5py
except ImportError:  # pragma: no cover - exercised in environments without h5py
    h5py = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import h5py as _h5py_typing  # noqa: F401


_H5PY_INSTALL_HINT = (
    "h5py is required for XRMMapH5Reader. "
    "Install with `pip install axiomm[hdf5]` or `pip install h5py`."
)


def _require_h5py() -> None:
    if h5py is None:
        raise ImportError(_H5PY_INSTALL_HINT)


# ---------------------------------------------------------------------------
# Configuration (spec §7.5, §17)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class XRMMapH5Config:
    """All structural and scientific defaults used by :class:`XRMMapH5Reader`.

    Defaults follow spec §17 and reproduce the prototype's behaviour. Override
    any field to read a similar-but-not-identical XRM-style file without
    subclassing the reader.
    """

    # HDF5 paths (the converter's first line of generality)
    counts_path: str = "/xrmmap/mcasum/counts"
    environ_name_path: str = "/xrmmap/config/environ/name"
    environ_value_path: str = "/xrmmap/config/environ/value"
    roi_name_path: str = "/xrmmap/config/rois/name"
    roi_limits_path: str = "/xrmmap/config/rois/limits"

    # Configuration-table key for the beam-size value used as nav scale.
    beam_size_key: str = "Experiment.Beam_Size__Nominal"

    # Fallback navigation scale: assumed field of view in µm divided by xdim.
    # Set to ``None`` to disable the fallback and fall through to a unit scale
    # with a "navigation_scale_unknown" diagnostic.
    fallback_field_width_um: float | None = 500.0

    # Axis defaults
    navigation_x_name: str = "x"
    navigation_y_name: str = "y"
    navigation_units: str = "µm"  # µ (U+00B5)
    energy_axis_name: str = "Energy"
    energy_axis_units: str = "keV"
    energy_scale: float = 40.96 / 4096
    roi_limit_scale: float = 0.01


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
    """
    if not isinstance(value, str):
        raise MetadataParseError(
            f"Expected string for micrometre value, got "
            f"{type(value).__name__}: {value!r}"
        )
    match = _MICROMETRE_PATTERN.match(value)
    if match is None:
        raise MetadataParseError(f"Cannot parse micrometre value: {value!r}")
    return float(match.group("value"))


# ---------------------------------------------------------------------------
# Reader (spec §7)
# ---------------------------------------------------------------------------

class XRMMapH5Reader:
    """Reader for XRM-map style HDF5 files.

    Parameters
    ----------
    config
        Override the default HDF5 paths and scientific defaults. ``None``
        uses :class:`XRMMapH5Config` defaults (spec §17).
    """

    name = "xrmmap_h5"
    supported_extensions = (".h5", ".hdf5")

    def __init__(self, config: XRMMapH5Config | None = None) -> None:
        self.config = config or XRMMapH5Config()

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
                return self.config.counts_path in f
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
            message names the path and the config field to override.
        """
        _require_h5py()

        source_path = Path(path)
        diagnostics: list[Diagnostic] = []
        original_metadata: dict[str, Any] = {}

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

        with h5py.File(source_path, "r") as f:
            # --- counts (required) ----------------------------------------
            if self.config.counts_path not in f:
                raise DatasetNotFoundError(
                    f"Counts dataset not found at "
                    f"{self.config.counts_path!r} in {source_path}. "
                    f"If this XRM file stores counts elsewhere, pass "
                    f"XRMMapH5Reader(config=XRMMapH5Config("
                    f"counts_path=...)) with the correct path."
                )
            data = np.asarray(f[self.config.counts_path][...])
            if data.ndim != 3:
                raise DatasetNotFoundError(
                    f"Counts dataset at {self.config.counts_path!r} has "
                    f"unexpected shape {data.shape!r}; expected a 3-D "
                    f"array (xdim, ydim, n_channels)."
                )
            xdim, ydim, n_channels = data.shape

            # --- environ / configuration table (optional) -----------------
            environ, environ_diag = self._read_environ_table(f)
            diagnostics.extend(environ_diag)
            if environ:
                original_metadata["environ"] = dict(environ)

            # --- ROI table (optional) -------------------------------------
            rois, roi_diag = self._read_roi_table(f)
            diagnostics.extend(roi_diag)
            if rois:
                original_metadata["rois"] = rois

        # --- navigation scale ---------------------------------------------
        nav_scale_um, scale_diag = self._resolve_navigation_scale(
            environ, xdim=xdim
        )
        diagnostics.extend(scale_diag)

        # --- axes ----------------------------------------------------------
        axes: tuple[AxisSpec, ...] = (
            AxisSpec(
                name=self.config.navigation_x_name,
                role="navigation",
                size=xdim,
                units=self.config.navigation_units,
                scale=nav_scale_um,
                offset=0.0,
                index_in_array=0,
            ),
            AxisSpec(
                name=self.config.navigation_y_name,
                role="navigation",
                size=ydim,
                units=self.config.navigation_units,
                scale=nav_scale_um,
                offset=0.0,
                index_in_array=1,
            ),
            AxisSpec(
                name=self.config.energy_axis_name,
                role="signal",
                size=n_channels,
                units=self.config.energy_axis_units,
                scale=self.config.energy_scale,
                offset=0.0,
                index_in_array=2,
            ),
        )

        metadata: dict[str, Any] = {
            "AXIOMM": {
                "reader": self.name,
                "reader_version": _axiomm_version,
                "config": {
                    "counts_path": self.config.counts_path,
                    "energy_scale": self.config.energy_scale,
                    "roi_limit_scale": self.config.roi_limit_scale,
                    "fallback_field_width_um": (
                        self.config.fallback_field_width_um
                    ),
                },
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
        )

    # -- internal helpers ---------------------------------------------------

    def _read_environ_table(
        self, f: Any
    ) -> tuple[dict[str, str], list[Diagnostic]]:
        diagnostics: list[Diagnostic] = []
        if (
            self.config.environ_name_path not in f
            or self.config.environ_value_path not in f
        ):
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="environ_missing",
                    message=(
                        f"Configuration table not found at "
                        f"{self.config.environ_name_path!r} and "
                        f"{self.config.environ_value_path!r}; "
                        f"beam-size resolution will fall back to "
                        f"fallback_field_width_um if configured."
                    ),
                )
            )
            return {}, diagnostics
        try:
            names = decode_hdf5_string_array(
                f[self.config.environ_name_path][...]
            )
            values = decode_hdf5_string_array(
                f[self.config.environ_value_path][...]
            )
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

    def _read_roi_table(
        self, f: Any
    ) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
        diagnostics: list[Diagnostic] = []
        if (
            self.config.roi_name_path not in f
            or self.config.roi_limits_path not in f
        ):
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="roi_missing",
                    message=(
                        f"ROI metadata not found at "
                        f"{self.config.roi_name_path!r} and "
                        f"{self.config.roi_limits_path!r}; "
                        f"continuing without ROI info."
                    ),
                )
            )
            return [], diagnostics
        try:
            names = decode_hdf5_string_array(
                f[self.config.roi_name_path][...]
            )
            limits = np.asarray(f[self.config.roi_limits_path][...])
        except (TypeError, OSError, KeyError) as exc:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="roi_unreadable",
                    message=f"Could not decode ROI metadata: {exc}",
                )
            )
            return [], diagnostics
        if limits.ndim != 2 or limits.shape[1] < 2:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="roi_limits_unexpected_shape",
                    message=(
                        f"ROI limits array has unexpected shape "
                        f"{limits.shape!r}; expected (n_rois, 2)."
                    ),
                )
            )
            return [], diagnostics
        n = min(len(names), len(limits))
        scale = self.config.roi_limit_scale
        return [
            {
                "name": names[i],
                "start": float(limits[i, 0]) * scale,
                "end": float(limits[i, 1]) * scale,
            }
            for i in range(n)
        ], diagnostics

    def _resolve_navigation_scale(
        self,
        environ: dict[str, str],
        *,
        xdim: int,
    ) -> tuple[float, list[Diagnostic]]:
        diagnostics: list[Diagnostic] = []
        beam_size_str = environ.get(self.config.beam_size_key)
        if beam_size_str is not None:
            try:
                return parse_micrometre_value(beam_size_str), diagnostics
            except MetadataParseError as exc:
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="beam_size_unparseable",
                        message=(
                            f"Could not parse beam size "
                            f"{beam_size_str!r}: {exc}. Falling back to "
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
                        f"Beam-size key {self.config.beam_size_key!r} not "
                        f"found in the configuration table; falling back "
                        f"to fallback_field_width_um / xdim."
                    ),
                )
            )
        if self.config.fallback_field_width_um is None:
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
            return 1.0, diagnostics
        return float(self.config.fallback_field_width_um) / xdim, diagnostics


__all__ = [
    "XRMMapH5Config",
    "XRMMapH5Reader",
    "decode_hdf5_string",
    "decode_hdf5_string_array",
    "parse_micrometre_value",
]
