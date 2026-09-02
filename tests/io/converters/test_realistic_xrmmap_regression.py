"""End-to-end regression tests against a realistic-shape XRM-map file (Chunk 11).

The synthetic fixture used by per-feature unit tests deliberately strips
away the structural complications of real instrument files (3-D ROI
limits, a populated environ table, larger counts shapes). This module
exercises the **full reader → builder → writer pipeline** against the
``realistic_xrmmap_h5`` fixture, which reproduces those complications.

If a future change silently breaks the real-file path, one of these
tests fails before any out-of-band smoke test catches it.
"""

from __future__ import annotations

import json

import pytest

hs = pytest.importorskip("hyperspy.api")
h5py = pytest.importorskip("h5py")

from axiomm.io.converters import convert_file
from axiomm.io.converters.writers.manifest import (
    MANIFEST_SCHEMA_VERSION,
    MANIFEST_SUFFIX,
)


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------

def test_realistic_round_trip_produces_loadable_hspy(
    realistic_xrmmap_h5, tmp_path,
):
    """The full pipeline accepts a realistic XRM file and produces a
    HyperSpy `.hspy` that loads back with the expected shape and axes."""
    src = realistic_xrmmap_h5("realistic.h5", shape=(8, 6, 1024))
    out = tmp_path / "out.hspy"

    result = convert_file(src, output_path=out, reader="xrmmap_h5")

    loaded = hs.load(str(out))
    assert loaded.data.shape == (8, 6, 1024)
    assert isinstance(loaded, hs.signals.Signal1D)

    # Axes labelled correctly after HyperSpy's reverse-order quirk.
    by_index = {
        ax.index_in_array: ax
        for ax in list(loaded.axes_manager.navigation_axes)
        + list(loaded.axes_manager.signal_axes)
    }
    assert by_index[0].name == "x" and by_index[0].size == 8
    assert by_index[1].name == "y" and by_index[1].size == 6
    assert by_index[2].name == "Energy" and by_index[2].size == 1024


def test_realistic_file_emits_no_unexpected_diagnostics(
    realistic_xrmmap_h5, tmp_path,
):
    """The realistic file must NOT trip the gotcha warnings the synthetic
    fixture would never exercise. Specifically: ROI shape, ROI variant
    index, beam-size missing, environ missing.
    """
    src = realistic_xrmmap_h5("realistic.h5")
    out = tmp_path / "out.hspy"

    result = convert_file(src, output_path=out, reader="xrmmap_h5")

    codes = {d.code for d in result.diagnostics}
    for unexpected in (
        "roi_limits_unexpected_shape",
        "roi_variant_out_of_bounds",
        "roi_names_limits_length_mismatch",
        "roi_missing",
        "beam_size_missing",
        "beam_size_unparseable",
        "environ_missing",
    ):
        assert unexpected not in codes, (
            f"Realistic-file regression: unexpected diagnostic {unexpected!r}"
        )


def test_realistic_file_extracts_rois_from_3d_limits(
    realistic_xrmmap_h5, tmp_path,
):
    """Real ROI limits are (n_rois, n_variants, 2); the reader must
    extract variant 0 by default and produce the full ROI list."""
    src = realistic_xrmmap_h5("realistic.h5")
    out = tmp_path / "out.hspy"

    convert_file(src, output_path=out, reader="xrmmap_h5")

    loaded = hs.load(str(out))
    om = loaded.original_metadata.as_dictionary()
    assert "rois" in om
    rois = om["rois"]
    # The fixture writes 15 ROI names.
    assert len(rois) == 15
    # ROI start/end are scaled by roi_limit_scale (default 0.01) from
    # the integer limits and end > start.
    for r in rois:
        assert r["end"] > r["start"]


def test_realistic_file_uses_beam_size_from_environ_as_nav_scale(
    realistic_xrmmap_h5, tmp_path,
):
    """``Experiment.Beam_Size__Nominal`` = "2um" in the realistic fixture;
    both nav axes must take 2.0 µm as their scale."""
    src = realistic_xrmmap_h5("realistic.h5")
    out = tmp_path / "out.hspy"

    convert_file(src, output_path=out, reader="xrmmap_h5")

    loaded = hs.load(str(out))
    for ax in loaded.axes_manager.navigation_axes:
        assert ax.scale == pytest.approx(2.0)
        assert ax.units == "µm"


def test_realistic_file_produces_v2_manifest_with_observed_environ_and_rois(
    realistic_xrmmap_h5, tmp_path,
):
    """The manifest sidecar must (a) carry schema v2, (b) classify the
    environ table and the ROI table as observed, and (c) classify the
    Energy axis scale and units as assumed."""
    src = realistic_xrmmap_h5("realistic.h5")
    out = tmp_path / "out.hspy"

    result = convert_file(src, output_path=out, reader="xrmmap_h5")

    expected_manifest = out.with_name(out.name + MANIFEST_SUFFIX)
    assert result.manifest_path == expected_manifest
    with expected_manifest.open() as f:
        manifest = json.load(f)

    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    classification = manifest["axiomm_metadata"]["provenance_classification"]

    joined_observed = "; ".join(classification["observed"])
    assert "environ" in joined_observed
    assert "rois" in joined_observed

    joined_assumed = "; ".join(classification["assumed"])
    assert "Energy.scale" in joined_assumed
    assert "Energy.units" in joined_assumed
