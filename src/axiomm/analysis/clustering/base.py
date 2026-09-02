"""The Clusterer protocol.

The operation takes only the feature seam (a DecompositionResult).
Backend parameters live on the instance (construction), so the protocol
stays backend-agnostic and HDBSCAN-compatible.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from axiomm.analysis.decomposition.models import DecompositionResult
    from axiomm.analysis.clustering.models import ClusteringResult


@runtime_checkable
class Clusterer(Protocol):
    name: str

    def cluster(self, features: "DecompositionResult") -> "ClusteringResult": ...


__all__ = ["Clusterer"]
