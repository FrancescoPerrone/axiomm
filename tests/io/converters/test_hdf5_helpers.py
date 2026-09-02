"""Tests for :mod:`axiomm.io.converters.readers.hdf5_helpers` (Chunk 14).

Per the modularity "tests prove reuse" rule, each extracted helper
gets exercised directly here — not just through the readers that
consume them. The reader-level tests in
``test_xrmmap_h5_reader.py`` and ``test_hdf5_generic.py`` still
cover the integration story.
"""

from __future__ import annotations

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from axiomm.io.converters.readers.hdf5_helpers import (
    read_environ_table,
    read_roi_table,
    resolve_navigation_scale,
)


# ---------------------------------------------------------------------------
# read_environ_table
# ---------------------------------------------------------------------------

def _write_environ(h5, name_path, value_path, mapping):
    names = np.array(list(mapping), dtype="S128")
    values = np.array(list(mapping.values()), dtype="S128")
    h5.create_dataset(name_path, data=names)
    h5.create_dataset(value_path, data=values)


def test_read_environ_table_happy_path(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        _write_environ(h5, "/cfg/name", "/cfg/value", {"a": "1", "b": "2"})
    with h5py.File(p, "r") as h5:
        environ, diags = read_environ_table(
            h5, name_path="/cfg/name", value_path="/cfg/value",
        )
    assert environ == {"a": "1", "b": "2"}
    assert diags == []


def test_read_environ_table_missing_name_path_returns_empty_with_diagnostic(tmp_path):
    p = tmp_path / "x.h5"
    p.touch()  # empty file
    with h5py.File(p, "w") as h5:
        pass  # no datasets
    with h5py.File(p, "r") as h5:
        environ, diags = read_environ_table(
            h5, name_path="/missing/name", value_path="/missing/value",
        )
    assert environ == {}
    codes = {d.code for d in diags}
    assert codes == {"environ_missing"}


def test_read_environ_table_none_path_returns_empty_with_diagnostic(tmp_path):
    """Passing name_path=None or value_path=None also yields environ_missing."""
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        pass
    with h5py.File(p, "r") as h5:
        environ, diags = read_environ_table(
            h5, name_path=None, value_path="/cfg/value",
        )
    assert environ == {}
    assert {d.code for d in diags} == {"environ_missing"}


def test_read_environ_table_length_mismatch_emits_warning(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        h5.create_dataset(
            "/cfg/name", data=np.array(["a", "b", "c"], dtype="S16"),
        )
        h5.create_dataset(
            "/cfg/value", data=np.array(["1", "2"], dtype="S16"),
        )
    with h5py.File(p, "r") as h5:
        environ, diags = read_environ_table(
            h5, name_path="/cfg/name", value_path="/cfg/value",
        )
    # The result is the shorter pair (zip truncates), but the
    # diagnostic surfaces the mismatch.
    assert environ == {"a": "1", "b": "2"}
    assert "environ_length_mismatch" in {d.code for d in diags}


# ---------------------------------------------------------------------------
# read_roi_table
# ---------------------------------------------------------------------------

def test_read_roi_table_handles_2d_shape(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        h5.create_dataset(
            "/rois/name", data=np.array(["Fe Ka"], dtype="S16"),
        )
        h5.create_dataset(
            "/rois/limits", data=np.array([[640, 670]], dtype=np.int32),
        )
    with h5py.File(p, "r") as h5:
        rois, diags = read_roi_table(
            h5, name_path="/rois/name", limits_path="/rois/limits",
            roi_limit_scale=0.01,
        )
    assert rois == [{"name": "Fe Ka", "start": 6.40, "end": 6.70}]
    assert diags == []


def test_read_roi_table_picks_variant_from_3d_shape(tmp_path):
    p = tmp_path / "x.h5"
    limits = np.zeros((2, 5, 2), dtype=np.int32)
    limits[:, 0, :] = [[640, 670], [800, 830]]
    limits[:, 3, :] = [[640, 671], [800, 831]]
    with h5py.File(p, "w") as h5:
        h5.create_dataset(
            "/rois/name", data=np.array(["Fe Ka", "Cu Ka"], dtype="S16"),
        )
        h5.create_dataset("/rois/limits", data=limits)
    with h5py.File(p, "r") as h5:
        rois_v0, _ = read_roi_table(
            h5, name_path="/rois/name", limits_path="/rois/limits",
            roi_limit_scale=0.01, roi_variant_index=0,
        )
        rois_v3, _ = read_roi_table(
            h5, name_path="/rois/name", limits_path="/rois/limits",
            roi_limit_scale=0.01, roi_variant_index=3,
        )
    assert rois_v0[0]["end"] == pytest.approx(6.70)
    assert rois_v3[0]["end"] == pytest.approx(6.71)


def test_read_roi_table_out_of_bounds_variant_yields_diagnostic(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        h5.create_dataset(
            "/rois/name", data=np.array(["Fe Ka"], dtype="S16"),
        )
        h5.create_dataset(
            "/rois/limits", data=np.zeros((1, 3, 2), dtype=np.int32),
        )
    with h5py.File(p, "r") as h5:
        rois, diags = read_roi_table(
            h5, name_path="/rois/name", limits_path="/rois/limits",
            roi_variant_index=99,
        )
    assert rois == []
    assert "roi_variant_out_of_bounds" in {d.code for d in diags}


def test_read_roi_table_rejects_wide_2d_shape(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        h5.create_dataset(
            "/rois/name", data=np.array(["Fe Ka"], dtype="S16"),
        )
        h5.create_dataset(
            "/rois/limits", data=np.zeros((1, 3), dtype=np.int32),
        )
    with h5py.File(p, "r") as h5:
        rois, diags = read_roi_table(
            h5, name_path="/rois/name", limits_path="/rois/limits",
        )
    assert rois == []
    assert "roi_limits_unexpected_shape" in {d.code for d in diags}


def test_read_roi_table_names_limits_length_mismatch(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        h5.create_dataset(
            "/rois/name", data=np.array(["Fe Ka"], dtype="S16"),
        )
        h5.create_dataset(
            "/rois/limits",
            data=np.array([[640, 670], [800, 830]], dtype=np.int32),
        )
    with h5py.File(p, "r") as h5:
        rois, diags = read_roi_table(
            h5, name_path="/rois/name", limits_path="/rois/limits",
        )
    assert rois == []
    assert "roi_names_limits_length_mismatch" in {d.code for d in diags}


def test_read_roi_table_missing_path_returns_empty_with_diagnostic(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as h5:
        pass
    with h5py.File(p, "r") as h5:
        rois, diags = read_roi_table(
            h5, name_path=None, limits_path=None,
        )
    assert rois == []
    assert "roi_missing" in {d.code for d in diags}


# ---------------------------------------------------------------------------
# resolve_navigation_scale
# ---------------------------------------------------------------------------

def test_resolve_navigation_scale_from_beam_size_returns_observed_tag():
    scale, diags, tag = resolve_navigation_scale(
        {"Experiment.Beam_Size__Nominal": "2um"},
        beam_size_key="Experiment.Beam_Size__Nominal",
        fallback_field_width_um=500.0,
        xdim=10,
    )
    assert scale == pytest.approx(2.0)
    assert tag == "beam_size"
    assert diags == []  # no warning when the beam size is present + valid


def test_resolve_navigation_scale_falls_back_when_beam_size_missing():
    scale, diags, tag = resolve_navigation_scale(
        {"Other.Key": "value"},
        beam_size_key="Experiment.Beam_Size__Nominal",
        fallback_field_width_um=500.0,
        xdim=10,
    )
    assert scale == pytest.approx(50.0)  # 500 / 10
    assert tag == "fallback"
    assert "beam_size_missing" in {d.code for d in diags}


def test_resolve_navigation_scale_falls_back_when_beam_size_unparseable():
    scale, diags, tag = resolve_navigation_scale(
        {"Experiment.Beam_Size__Nominal": "garbage"},
        beam_size_key="Experiment.Beam_Size__Nominal",
        fallback_field_width_um=500.0,
        xdim=10,
    )
    assert scale == pytest.approx(50.0)
    assert tag == "fallback"
    assert "beam_size_unparseable" in {d.code for d in diags}


def test_resolve_navigation_scale_unit_when_no_beam_size_and_no_fallback():
    scale, diags, tag = resolve_navigation_scale(
        {},
        beam_size_key="Experiment.Beam_Size__Nominal",
        fallback_field_width_um=None,
        xdim=10,
    )
    assert scale == 1.0
    assert tag == "unit"
    assert "navigation_scale_unknown" in {d.code for d in diags}


def test_resolve_navigation_scale_none_key_skips_beam_lookup_entirely():
    """When the schema has no beam_size_key, the function must not try to
    look anything up — it falls back directly."""
    scale, diags, tag = resolve_navigation_scale(
        {"Experiment.Beam_Size__Nominal": "2um"},
        beam_size_key=None,
        fallback_field_width_um=500.0,
        xdim=10,
    )
    # The beam-size entry exists in the dict, but the schema doesn't
    # name it, so we fall back rather than reading it.
    assert tag == "fallback"
    assert scale == pytest.approx(50.0)
