"""Dimensionality-reduction tool (stage two, S1).

Backend-neutral by default (scikit-learn PCA on the neutral
``AxiommSignalPayload``). Backends are registered by stable string name
in the module-level :data:`decomposers` registry and resolved lazily, so
importing this package never imports scikit-learn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from axiomm.analysis.registry import Registry, load_into
from axiomm.analysis.decomposition.base import Decomposer
from axiomm.analysis.decomposition.models import DecompositionResult

if TYPE_CHECKING:
    from axiomm.io.converters.models import AxiommSignalPayload

#: Entry-point group third-party packages use to register decomposers.
ENTRY_POINT_DECOMPOSERS = "axiomm.decomposers"

#: Default decomposer registry. Built-in "pca" registered lazily.
decomposers: Registry = Registry("decomposer")
decomposers.register(
    "pca",
    "axiomm.analysis.decomposition.sklearn_pca:SklearnPCADecomposer",
)
load_into(decomposers, ENTRY_POINT_DECOMPOSERS)


def get_decomposer(name: str) -> Decomposer:
    """Return a fresh decomposer instance registered under ``name``."""
    return decomposers.get(name)


def decompose(
    payload: "AxiommSignalPayload",
    *,
    backend: str = "pca",
    n_components: int | None = None,
) -> DecompositionResult:
    """Decompose ``payload`` with the named ``backend``.

    ``n_components=None`` keeps ``min(n_pixels, n_channels)`` components;
    the user chooses any integer to reduce. No value is baked in.
    """
    return get_decomposer(backend).decompose(payload, n_components=n_components)


__all__ = [
    "ENTRY_POINT_DECOMPOSERS",
    "Decomposer",
    "DecompositionResult",
    "decompose",
    "decomposers",
    "get_decomposer",
]
