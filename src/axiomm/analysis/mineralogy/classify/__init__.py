"""S7 phase classification — a pluggable decision layer over matching evidence.

Policies turn S3d candidate matches into species / family / unresolved labels
under user-chosen, fully-recorded settings. The :data:`classifiers` registry
mirrors the S1/S2/S4 backend registries, so a new strategy plugs in by name
without touching the pipeline. Named presets are the "instantiations" a user
picks — ``family_aware`` is the honest default (species when clear, family on
ambiguity, unresolved when weak); ``permissive`` restores the pre-S7 behaviour;
``conservative`` only names strong, unambiguous species.
"""

from __future__ import annotations

from axiomm.analysis.mineralogy.classify.classify import classify_clusters
from axiomm.analysis.mineralogy.classify.models import (
    UNRESOLVED_NAME,
    ClusterLabel,
    LabelLevel,
)
from axiomm.analysis.mineralogy.classify.policy import (
    ClassificationPolicy,
    PermissivePolicy,
    ThresholdPolicy,
)
from axiomm.analysis.registry import Registry

#: Registry mapping a stable name to a fresh :class:`ClassificationPolicy`.
classifiers: Registry = Registry("classifier")
classifiers.register("threshold", lambda: ThresholdPolicy())
classifiers.register("permissive", lambda: PermissivePolicy())
# Named presets (configuration, not code branches).
classifiers.register("family_aware", lambda: ThresholdPolicy(
    species_floor=0.80, family_floor=0.50, family_margin=0.05, allow_family=True))
classifiers.register("conservative", lambda: ThresholdPolicy(
    species_floor=0.85, family_floor=0.85, family_margin=0.05, allow_family=False))


__all__ = [
    "UNRESOLVED_NAME",
    "ClassificationPolicy",
    "ClusterLabel",
    "LabelLevel",
    "PermissivePolicy",
    "ThresholdPolicy",
    "classifiers",
    "classify_clusters",
]
