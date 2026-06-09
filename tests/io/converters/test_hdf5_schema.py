"""Tests for :mod:`axiomm.io.converters.readers.hdf5_schema` (Chunk 14)."""

from __future__ import annotations

import pytest

from axiomm.io.converters.readers.hdf5_schema import (
    HDF5MapSchema,
    XRMMAP_H5_SCHEMA,
)


def test_hdf5_map_schema_requires_counts_path():
    """The only required field is counts_path; everything else has a default."""
    s = HDF5MapSchema(counts_path="/somewhere/counts")
    assert s.counts_path == "/somewhere/counts"
    assert s.environ_name_path is None
    assert s.environ_value_path is None
    assert s.roi_name_path is None
    assert s.roi_limits_path is None
    assert s.beam_size_key is None


def test_hdf5_map_schema_default_axis_labels_match_xrm_convention():
    s = HDF5MapSchema(counts_path="/x")
    assert s.navigation_x_name == "x"
    assert s.navigation_y_name == "y"
    assert s.navigation_units == "µm"
    assert s.energy_axis_name == "Energy"
    assert s.energy_axis_units == "keV"


def test_hdf5_map_schema_is_frozen():
    s = HDF5MapSchema(counts_path="/x")
    with pytest.raises(Exception):
        s.counts_path = "/different"  # type: ignore[misc]


def test_xrmmap_h5_schema_constant_matches_xrm_paths():
    """The built-in schema constant uses the canonical XRM-Map / Larch paths."""
    assert XRMMAP_H5_SCHEMA.counts_path == "/xrmmap/mcasum/counts"
    assert XRMMAP_H5_SCHEMA.environ_name_path == "/xrmmap/config/environ/name"
    assert XRMMAP_H5_SCHEMA.environ_value_path == "/xrmmap/config/environ/value"
    assert XRMMAP_H5_SCHEMA.roi_name_path == "/xrmmap/config/rois/name"
    assert XRMMAP_H5_SCHEMA.roi_limits_path == "/xrmmap/config/rois/limits"
    assert XRMMAP_H5_SCHEMA.beam_size_key == "Experiment.Beam_Size__Nominal"
