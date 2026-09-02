"""Tests for :mod:`axiomm.analysis.models` (Stage two, Chunk S0)."""

from __future__ import annotations

from dataclasses import dataclass

from axiomm.analysis.models import (
    AnalysisProvenance,
    AnalysisResult,
    Diagnostic,
)


def test_diagnostic_is_frozen_and_defaults_context():
    d = Diagnostic(severity="warning", code="low_variance", message="only 2%")
    assert d.severity == "warning"
    assert d.code == "low_variance"
    assert d.context == {}


def test_provenance_records_tool_and_backend():
    p = AnalysisProvenance(tool="clustering", backend="gmm", params={"k": 7})
    assert p.tool == "clustering"
    assert p.backend == "gmm"
    assert p.params["k"] == 7
    assert p.tool_version is None


def test_analysis_result_defaults_are_independent():
    a = AnalysisResult()
    b = AnalysisResult()
    a.diagnostics.append(Diagnostic("info", "c", "m"))
    assert a.diagnostics != b.diagnostics  # no shared mutable default
    assert b.provenance is None


def test_analysis_result_base_fields_are_keyword_only():
    """Subclasses must be able to add positional required fields without a
    dataclass field-ordering error — so base fields are keyword-only."""

    @dataclass
    class DummyResult(AnalysisResult):
        label_count: int  # positional, required

    r = DummyResult(3, provenance=AnalysisProvenance(tool="t", backend="b"))
    assert r.label_count == 3
    assert r.provenance.backend == "b"
