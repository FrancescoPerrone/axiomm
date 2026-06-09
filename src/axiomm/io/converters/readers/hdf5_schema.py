"""Schema describing the structural layout of an HDF5 map file.

An :class:`HDF5MapSchema` names the HDF5 paths where a 3-D map file
keeps its counts dataset, its environ name/value table, its ROI
name/limits table, and (via a key into the environ table) its
nominal beam size. The schema is structural metadata only — what's
*where* in the file. Scientific defaults (per-channel energy width,
ROI integer-to-keV scale factor, fallback navigation width) live on
the separate :class:`~axiomm.io.converters.readers.hdf5_generic.HDF5MapConfig`,
so the same schema can be re-used across instruments that produce
the same file layout with different physical units.

Two consumers ship in the package today:

* :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Reader`
  uses a hard-coded XRM-Map / Larch layout via its
  :class:`~axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Config`
  defaults (paths + scientific defaults bundled together for
  back-compat).
* :class:`~axiomm.io.converters.readers.hdf5_generic.GenericHDF5MapReader`
  takes an :class:`HDF5MapSchema` explicitly so users can read any
  XRM-shaped file at non-standard paths without writing a new
  Reader class.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HDF5MapSchema:
    """Where to find each piece of an XRM-shaped 3-D HDF5 map file.

    The only required field is :attr:`counts_path`. Setting an
    optional path to ``None`` (or omitting it) tells the generic
    reader that piece of metadata is unavailable and a diagnostic
    is emitted instead of an exception.

    Attributes
    ----------
    counts_path
        HDF5 path to the 3-D counts dataset of shape
        ``(xdim, ydim, n_channels)``.
    environ_name_path, environ_value_path
        Parallel HDF5 paths for the environ name/value table.
        ``None`` for either disables environ extraction.
    roi_name_path, roi_limits_path
        Parallel HDF5 paths for the ROI name/limits table.
        ``None`` for either disables ROI extraction. The limits
        dataset can be either ``(n_rois, 2)`` or
        ``(n_rois, n_variants, 2)`` — see
        :class:`HDF5MapConfig.roi_variant_index`.
    beam_size_key
        Key into the environ table holding the nominal beam size
        used to set the navigation pixel scale (e.g. ``"2um"``).
        ``None`` disables beam-size lookup; the navigation scale
        then falls back to ``fallback_field_width_um / xdim`` (per
        :class:`HDF5MapConfig`).
    navigation_x_name, navigation_y_name
        Axis names assigned to the first two array dimensions in
        the produced :class:`AxiommSignalPayload`.
    navigation_units, energy_axis_name, energy_axis_units
        Default axis label strings. Don't change the physical
        meaning of the data — only the labels.
    """

    counts_path: str
    environ_name_path: str | None = None
    environ_value_path: str | None = None
    roi_name_path: str | None = None
    roi_limits_path: str | None = None
    beam_size_key: str | None = None

    navigation_x_name: str = "x"
    navigation_y_name: str = "y"
    navigation_units: str = "µm"
    energy_axis_name: str = "Energy"
    energy_axis_units: str = "keV"


#: Built-in schema matching the XRM-Map / Larch HDF5 convention. The
#: same paths the bespoke :class:`XRMMapH5Reader` uses, exposed as a
#: standalone constant so users of the generic reader can re-use the
#: layout (or copy and modify it) without retyping the path strings.
XRMMAP_H5_SCHEMA: HDF5MapSchema = HDF5MapSchema(
    counts_path="/xrmmap/mcasum/counts",
    environ_name_path="/xrmmap/config/environ/name",
    environ_value_path="/xrmmap/config/environ/value",
    roi_name_path="/xrmmap/config/rois/name",
    roi_limits_path="/xrmmap/config/rois/limits",
    beam_size_key="Experiment.Beam_Size__Nominal",
)


__all__ = [
    "HDF5MapSchema",
    "XRMMAP_H5_SCHEMA",
]
