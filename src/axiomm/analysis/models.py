"""Shared in-memory data model for the AXIOMM analysis suite.

Backend-agnostic dataclasses carried between tools. Mirrors the
converter's :mod:`axiomm.io.converters.models` (``Diagnostic`` and
provenance patterns). Tool-specific payloads (``DecompositionResult``,
``ClusteringResult``, ``MineralAssignment``) subclass
:class:`AnalysisResult` in their own packages (S1+).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

Severity = Literal["info", "warning", "error"]
"""Severity levels for :class:`Diagnostic`."""


@dataclass(frozen=True)
class Diagnostic:
    """A structured info / warning / error attached to an analysis result.

    Diagnostics travel with the payload so UX layers and pipeline
    manifests can surface them without lossy ``print`` calls.
    """

    severity: Severity
    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisProvenance:
    """Which tool + backend produced a result, and with what parameters."""

    tool: str
    backend: str
    tool_version: str | None = None
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """Base for every analysis-tool result payload.

    The two base fields are **keyword-only** so subclasses can declare
    their own positional required fields (e.g. ``label_map``) without
    tripping the dataclass "non-default argument follows default
    argument" rule.
    """

    provenance: AnalysisProvenance | None = field(default=None, kw_only=True)
    diagnostics: list[Diagnostic] = field(default_factory=list, kw_only=True)


__all__ = [
    "AnalysisProvenance",
    "AnalysisResult",
    "Diagnostic",
    "Severity",
]
