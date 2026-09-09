"""Built-in per-stage section renderers (stage two, S4).

Each renderer is registered lazily in
:mod:`axiomm.analysis.reporting.registry`, so importing the reporting package
does not import these modules (and thus not numpy/matplotlib) until a report is
actually rendered. Renderers duck-type the result they are given, so they work
on a ``PipelineResult`` or a compatible stage payload without importing the
pipeline (no import cycle).
"""

from __future__ import annotations

__all__: list[str] = []
