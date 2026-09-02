"""Result payload for the decomposition tool."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiomm.analysis.models import AnalysisResult


@dataclass
class DecompositionResult(AnalysisResult):
    """Outcome of a decomposition.

    ``factors`` are the component spectra ``(n_channels, n_components)``;
    ``loadings`` are the per-pixel scores ``(n_pixels, n_components)``;
    ``nav_shape`` lets a consumer reshape loadings back into maps. The
    ``provenance`` / ``diagnostics`` fields come from
    :class:`~axiomm.analysis.models.AnalysisResult` (keyword-only).
    """

    factors: np.ndarray
    loadings: np.ndarray
    explained_variance_ratio: np.ndarray
    nav_shape: tuple[int, ...]
    n_components: int


__all__ = ["DecompositionResult"]
