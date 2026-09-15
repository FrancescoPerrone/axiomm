"""Native VTK embedding viewer — pure data-prep + dependency-error path.

The window itself needs VTK + a display, so it is verified on a desktop; here we
test the colour mapping (incl. HDBSCAN noise) and that a missing VTK is a clear
error, not a crash.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.analysis.reporting.embedding_vtk import cluster_rgb, show_embedding_vtk


def test_cluster_rgb_colours_by_cluster_with_noise_grey():
    labels = np.array([0, 0, 1, 2, -1])          # HDBSCAN-style, with noise
    rgb = cluster_rgb(labels)
    assert rgb.shape == (5, 3) and rgb.dtype == np.uint8
    # same cluster -> same colour; noise (-1) -> grey
    assert tuple(rgb[0]) == tuple(rgb[1])
    assert tuple(rgb[4]) == (138, 143, 152)
    # distinct clusters -> distinct colours
    assert tuple(rgb[0]) != tuple(rgb[2]) != tuple(rgb[3])


def test_show_embedding_vtk_missing_dependency_raises_clearly():
    try:
        import vtk  # noqa: F401
        pytest.skip("VTK is installed; the missing-dependency path is not exercised")
    except ImportError:
        pass
    pts = np.random.default_rng(0).normal(size=(20, 3))
    with pytest.raises(AnalysisDependencyError, match="VTK"):
        show_embedding_vtk(pts, np.zeros(20, int), block=False)


def test_native_viewer_runs_when_vtk_available():
    vtk = pytest.importorskip("vtk")  # noqa: F841
    pts = np.random.default_rng(0).normal(size=(50, 3))
    win = show_embedding_vtk(pts, np.array([0] * 25 + [1] * 25), block=False)  # no window shown
    assert win is not None
