"""Tests for :mod:`axiomm.analysis.errors` (Stage two, Chunk S0)."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import (
    AxiommAnalysisError,
    BackendNotFoundError,
    PayloadValidationError,
    ReferenceLibraryError,
)


@pytest.mark.parametrize(
    "subclass",
    [BackendNotFoundError, PayloadValidationError, ReferenceLibraryError],
)
def test_subclasses_derive_from_base(subclass):
    assert issubclass(subclass, AxiommAnalysisError)


def test_base_derives_from_exception():
    assert issubclass(AxiommAnalysisError, Exception)


def test_raised_error_carries_message():
    with pytest.raises(BackendNotFoundError, match="pca"):
        raise BackendNotFoundError("unknown backend 'pca'")
