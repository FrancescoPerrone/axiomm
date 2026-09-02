"""Tests for DecompositionResult (Stage two, S1)."""

from __future__ import annotations

import numpy as np

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.decomposition.models import DecompositionResult


def test_decomposition_result_holds_arrays_and_provenance():
    r = DecompositionResult(
        factors=np.zeros((8, 3)),
        loadings=np.zeros((12, 3)),
        explained_variance_ratio=np.array([0.5, 0.3, 0.2]),
        nav_shape=(4, 3),
        n_components=3,
        provenance=AnalysisProvenance(tool="decomposition", backend="pca"),
    )
    assert r.factors.shape == (8, 3)
    assert r.loadings.shape == (12, 3)
    assert r.explained_variance_ratio.shape == (3,)
    assert r.nav_shape == (4, 3)
    assert r.n_components == 3
    assert r.provenance.backend == "pca"
    assert r.diagnostics == []  # kw-only default from AnalysisResult
