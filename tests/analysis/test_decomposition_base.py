"""Tests for the Decomposer protocol (Stage two, S1)."""

from __future__ import annotations

from axiomm.analysis.decomposition.base import Decomposer


def test_conforming_object_satisfies_protocol():
    class Dummy:
        name = "dummy"

        def decompose(self, payload, *, n_components=None):
            return None

    assert isinstance(Dummy(), Decomposer)


def test_missing_decompose_fails_protocol():
    class NoDecompose:
        name = "x"

    assert not isinstance(NoDecompose(), Decomposer)
