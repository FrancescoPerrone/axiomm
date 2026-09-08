"""Headless figure helpers for reporting (stage two, S4).

matplotlib is imported lazily and isolated here (monkeypatchable in tests); its
absence raises :class:`AnalysisDependencyError`. Figures are built with the
object API (``Figure`` + ``FigureCanvasAgg``) — never pyplot, ``matplotlib.use``,
or a window — so the reporting core stays headless and import-light.
"""

from __future__ import annotations

from io import BytesIO

import numpy as np

from axiomm.analysis.errors import AnalysisDependencyError


def import_matplotlib():
    """Import matplotlib or raise a clear dependency error."""
    try:
        import matplotlib
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise AnalysisDependencyError(
            "matplotlib is required to render report figures; install the [viz] extra."
        ) from exc
    return matplotlib


def new_agg_figure(figsize=(6.0, 4.0)):
    """A fresh Agg-backed :class:`matplotlib.figure.Figure` (no pyplot state)."""
    import_matplotlib()
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=figsize)
    FigureCanvasAgg(fig)
    return fig


def figure_to_png(fig, *, dpi: int = 110) -> bytes:
    """Serialize a figure to PNG bytes for embedding as a data URI."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    return buf.getvalue()


def categorical_map_png(array, categories, *, labels=None, figsize=(5.0, 4.0)) -> bytes:
    """A categorical 2-D map (phase map, cluster label map, ...) with a legend.

    ``categories`` is the ordered list of distinct values in ``array``; ``labels``
    are their display strings (default ``str(category)``).
    """
    mpl = import_matplotlib()
    from matplotlib.patches import Patch

    labels = labels or [str(c) for c in categories]
    code = {c: i for i, c in enumerate(categories)}
    codes = np.vectorize(code.__getitem__)(np.asarray(array)).astype(int)
    cmap = mpl.colormaps["tab20"].resampled(max(len(categories), 1))

    fig = new_agg_figure(figsize=figsize)
    ax = fig.add_subplot(111)
    ax.imshow(codes, cmap=cmap, vmin=-0.5, vmax=len(categories) - 0.5, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    handles = [Patch(facecolor=cmap(i), label=str(lbl)) for i, lbl in enumerate(labels)]
    ax.legend(handles=handles, bbox_to_anchor=(1.02, 1.0), loc="upper left",
              fontsize=8, frameon=False)
    return figure_to_png(fig)


__all__ = ["categorical_map_png", "figure_to_png", "import_matplotlib", "new_agg_figure"]
