"""Tests for decomposition file adapters (Stage two, S1)."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.decomposition.models import DecompositionResult
from axiomm.analysis.decomposition.io import read_decomposition, write_decomposition


def _result():
    return DecompositionResult(
        factors=np.arange(24, dtype=float).reshape(8, 3),
        loadings=np.arange(36, dtype=float).reshape(12, 3),
        explained_variance_ratio=np.array([0.5, 0.3, 0.2]),
        nav_shape=(4, 3),
        n_components=3,
        provenance=AnalysisProvenance(
            tool="decomposition", backend="pca", params={"n_components": 3}
        ),
        diagnostics=[Diagnostic("info", "explained_variance_total", "x")],
    )


def test_write_then_read_roundtrips(tmp_path):
    write_decomposition(_result(), tmp_path, "sample")
    back = read_decomposition(tmp_path, "sample")
    assert np.array_equal(back.factors, _result().factors)
    assert np.array_equal(back.loadings, _result().loadings)
    assert np.array_equal(
        back.explained_variance_ratio, _result().explained_variance_ratio
    )
    assert back.nav_shape == (4, 3)
    assert back.n_components == 3
    assert back.provenance.backend == "pca"
    assert back.provenance.params == {"n_components": 3}
    assert back.diagnostics[0].code == "explained_variance_total"


def test_write_refuses_silent_overwrite(tmp_path):
    write_decomposition(_result(), tmp_path, "sample")
    with pytest.raises(OutputExistsError):
        write_decomposition(_result(), tmp_path, "sample")
    # explicit overwrite is allowed
    write_decomposition(_result(), tmp_path, "sample", overwrite=True)
