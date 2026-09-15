"""Native (desktop) 3-D embedding viewer via VTK.

A local GUI window — no browser, no HTML — for exploring the reduction embedding
(>=3 components) coloured by cluster. VTK is an **optional** dependency (the ``[vtk]``
extra); its absence raises :class:`AnalysisDependencyError`. This is a UX adapter: it
opens an OS window and must never be imported by the headless core.

Interaction is VTK's standard trackball camera — **no auto-spin**: drag to rotate,
scroll to zoom, middle/shift-drag to pan, ``r`` re-fits the camera, ``s``/``w`` toggle
surface/points. An orientation axes gizmo sits in the corner. It plots the output of
*any* clustering (GMM, HDBSCAN, …); HDBSCAN noise (label ``-1``) is shown grey.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.analysis.reporting.embedding_3d import _PALETTE, embedding_3d_from_result


def _import_vtk():
    """Import VTK or raise a clear dependency error (isolated for tests)."""
    try:
        import vtk
    except ImportError as exc:  # pragma: no cover - exercised when the extra is absent
        raise AnalysisDependencyError(
            "VTK is required for the native 3-D viewer; install the [vtk] extra "
            "(pip install 'axiomm[vtk]' or pip install vtk)."
        ) from exc
    return vtk


def _hex_rgb(h: str) -> tuple[int, int, int]:
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def cluster_rgb(labels, categories=None) -> np.ndarray:
    """Per-point ``uint8`` RGB from cluster labels (noise, label ``-1``, is grey)."""
    labels = np.asarray(labels)
    if categories is None:
        categories = [int(c) for c in np.unique(labels)]
    cmap = {int(c): ((138, 143, 152) if c == -1 else _hex_rgb(_PALETTE[i % len(_PALETTE)]))
            for i, c in enumerate(categories)}
    out = np.zeros((labels.shape[0], 3), dtype=np.uint8)
    for i, lab in enumerate(labels):
        out[i] = cmap[int(lab)]
    return out


def show_embedding_vtk(points, labels, *, title: str = "AXIOMM — embedding",
                       point_size: float = 4.0, block: bool = True):
    """Open a native VTK window: a 3-D point cloud coloured by cluster.

    ``block=True`` starts the interactor (call blocks until the window closes).
    Returns the ``vtkRenderWindow`` so a host GUI can embed or drive it instead.
    """
    vtk = _import_vtk()
    from vtk.util import numpy_support

    pts = np.ascontiguousarray(np.asarray(points, dtype=np.float32))
    if pts.ndim != 2 or pts.shape[1] != 3:
        from axiomm.analysis.errors import PayloadValidationError
        raise PayloadValidationError(f"points must be (n, 3); got shape {pts.shape}.")
    rgb = np.ascontiguousarray(cluster_rgb(labels))

    vpoints = vtk.vtkPoints()
    vpoints.SetData(numpy_support.numpy_to_vtk(pts, deep=True))
    poly = vtk.vtkPolyData()
    poly.SetPoints(vpoints)
    colors = numpy_support.numpy_to_vtk(rgb, deep=True, array_type=vtk.VTK_UNSIGNED_CHAR)
    colors.SetName("cluster")
    poly.GetPointData().SetScalars(colors)

    glyph = vtk.vtkVertexGlyphFilter()
    glyph.SetInputData(poly)
    glyph.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    mapper.SetScalarModeToUsePointData()
    mapper.SetColorModeToDirectScalars()

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetPointSize(point_size)

    renderer = vtk.vtkRenderer()
    renderer.AddActor(actor)
    renderer.SetBackground(0.07, 0.08, 0.10)

    win = vtk.vtkRenderWindow()
    win.AddRenderer(renderer)
    win.SetSize(960, 720)
    win.SetWindowName(title)

    iren = vtk.vtkRenderWindowInteractor()
    iren.SetRenderWindow(win)
    iren.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())  # trackball, never auto-spins

    axes = vtk.vtkAxesActor()
    marker = vtk.vtkOrientationMarkerWidget()
    marker.SetOrientationMarker(axes)
    marker.SetInteractor(iren)
    marker.SetViewport(0.0, 0.0, 0.2, 0.2)
    marker.SetEnabled(1)
    marker.InteractiveOff()

    renderer.ResetCamera()
    if block:  # pragma: no cover - opens an OS window, verified on a display
        win.Render()
        iren.Initialize()
        iren.Start()
    return win


def show_embedding_vtk_from_result(result, *, max_points: int = 200000, **kwargs):
    """Open the native viewer for a pipeline/analysis result (first 3 components,
    coloured by its clustering — GMM, HDBSCAN, …)."""
    points, labels = embedding_3d_from_result(result, max_points=max_points)
    return show_embedding_vtk(points, labels, **kwargs)


__all__ = ["cluster_rgb", "show_embedding_vtk", "show_embedding_vtk_from_result"]
