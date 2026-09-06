"""AXIOMM — Automated X-ray Intelligence for Organising Mineral Mapping.

A Python package for spectroscopy, applied to mineral-mapping workflows.
The broader scope of AXIOMM (analyses, automation, user-facing APIs) is
defined by Francesco Perrone and is intentionally left open at this stage
of development. The currently implemented portion of the package is one
utility tool — the converter — exposed under :mod:`axiomm.io.converters`.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

__all__ = ["Pipeline", "__version__"]


def __getattr__(name: str):
    # Lazily expose the front door so `from axiomm import Pipeline` works while
    # a bare `import axiomm` (or importing any submodule) stays minimal and free
    # of import side effects — the pipeline + analysis backends load only when
    # Pipeline is actually requested. See PEP 562.
    if name == "Pipeline":
        from axiomm.pipeline import Pipeline

        return Pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(__all__)
