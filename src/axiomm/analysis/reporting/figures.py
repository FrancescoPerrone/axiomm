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


def figure_to_png(fig, *, dpi: int = 168) -> bytes:
    """Serialize a figure to PNG bytes for embedding as a data URI.

    The default dpi carries resolution headroom on purpose: embedded figures are
    displayed at a CSS size well below their pixel size, so high-DPI / 4K monitors
    (and the report's click-to-enlarge view) render them crisply while ordinary
    displays downscale cleanly. True device-adaptive / infinite zoom is the planned
    SVG/PDF export, not this raster path.
    """
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    return buf.getvalue()


def categorical_map_png(array, categories, *, labels=None, palette=None, reserve=None,
                        figsize=(5.0, 4.0)) -> bytes:
    """A categorical 2-D map (phase map, cluster label map, ...) with a legend.

    ``categories`` is the ordered list of distinct values in ``array``; ``labels``
    are their display strings (default ``str(category)``). ``palette`` is the
    categorical colour map — a built-in name (default ``"batlowS"``), any
    Matplotlib colormap name, or an explicit list of colours (see
    :func:`~axiomm.analysis.reporting.palettes.resolve_palette`); ``reserve`` pins
    specific category indices to fixed colours (e.g. grey for "unresolved").
    """
    import_matplotlib()
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    from axiomm.analysis.reporting.palettes import resolve_palette

    labels = labels or [str(c) for c in categories]
    n = max(len(categories), 1)
    code = {c: i for i, c in enumerate(categories)}
    codes = np.vectorize(code.__getitem__)(np.asarray(array)).astype(int)
    colours = resolve_palette(palette, n, reserve=reserve)
    cmap = ListedColormap(colours)

    fig = new_agg_figure(figsize=figsize)
    ax = fig.add_subplot(111)
    ax.imshow(codes, cmap=cmap, vmin=-0.5, vmax=len(categories) - 0.5, interpolation="nearest")
    ax.set_xticks([])
    ax.set_yticks([])
    handles = [Patch(facecolor=colours[i], label=str(lbl)) for i, lbl in enumerate(labels)]
    ax.legend(handles=handles, bbox_to_anchor=(1.02, 1.0), loc="upper left",
              fontsize=8, frameon=False)
    return figure_to_png(fig)


__all__ = ["categorical_map_png", "figure_to_png", "import_matplotlib", "new_agg_figure"]
