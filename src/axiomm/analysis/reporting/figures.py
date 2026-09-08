"""Headless figure helpers for reporting (stage two, S4).

matplotlib is imported lazily and isolated here (monkeypatchable in tests); its
absence raises :class:`AnalysisDependencyError`. Figures are built with the
object API (``Figure`` + ``FigureCanvasAgg``) — never pyplot, ``matplotlib.use``,
or a window — so the reporting core stays headless and import-light.
"""

from __future__ import annotations

from io import BytesIO

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


__all__ = ["figure_to_png", "import_matplotlib", "new_agg_figure"]
