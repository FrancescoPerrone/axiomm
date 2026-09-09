"""UMAP decomposition backend (stage two, S6).

Non-linear dimensionality reduction via ``umap-learn`` (an optional dependency —
the ``[umap]`` extra; absence raises :class:`AnalysisDependencyError`). UMAP
produces an embedding used as clustering features. It is not a variance
decomposition, so ``factors`` and ``explained_variance_ratio`` are empty — a
:class:`DecompositionResult` consumer must tolerate that (the pipeline's
clustering only uses ``loadings``; the report's decomposition section notes it).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from axiomm.analysis.decomposition.models import DecompositionResult
from axiomm.analysis.errors import AnalysisDependencyError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.reshape import pixels_by_channels


@dataclass(frozen=True)
class UMAPConfig:
    """Tuning parameters for :class:`UMAPDecomposer` (umap-learn defaults)."""

    n_neighbors: int = 15
    min_dist: float = 0.1
    metric: str = "euclidean"
    random_state: int | None = None


def _import_umap():
    """Import umap-learn (isolated so tests can monkeypatch it)."""
    try:
        import umap
    except ImportError as exc:  # pragma: no cover - exercised when the extra is absent
        raise AnalysisDependencyError(
            "umap-learn is required for the UMAP decomposer; install the [umap] extra."
        ) from exc
    return umap


class UMAPDecomposer:
    """Embed a spectrum image with UMAP for clustering.

    ``random_state`` mirrors the PCA backend's constructor arg (the pipeline
    threads its seed here); it makes UMAP deterministic at some speed cost.
    """

    name = "umap"

    def __init__(self, random_state: int | None = None, config: UMAPConfig | None = None) -> None:
        config = config or UMAPConfig()
        if random_state is not None and config.random_state is None:
            config = replace(config, random_state=random_state)
        self.config = config

    def decompose(self, payload, *, n_components: int | None = None) -> DecompositionResult:
        diagnostics: list[Diagnostic] = []
        flat = pixels_by_channels(payload)
        if not isinstance(payload.data, np.ndarray):
            diagnostics.append(Diagnostic(
                "warning", "lazy_materialized",
                "Input data was materialized into memory for UMAP."))

        n_comp = 2 if n_components is None else int(n_components)
        umap = _import_umap()
        cfg = self.config
        reducer = umap.UMAP(
            n_components=n_comp, n_neighbors=cfg.n_neighbors,
            min_dist=cfg.min_dist, metric=cfg.metric, random_state=cfg.random_state)
        embedding = np.asarray(reducer.fit_transform(flat.matrix))
        diagnostics.append(Diagnostic(
            "info", "umap_embedding",
            f"UMAP embedding into {n_comp} dimensions; explained variance is not "
            "defined for this backend."))

        return DecompositionResult(
            factors=np.zeros((flat.n_channels, 0)),
            loadings=embedding,
            explained_variance_ratio=np.zeros((0,)),
            nav_shape=flat.nav_shape,
            n_components=n_comp,
            provenance=AnalysisProvenance(
                tool="decomposition", backend=self.name,
                params={"n_components": n_comp, "n_neighbors": cfg.n_neighbors,
                        "min_dist": cfg.min_dist, "random_state": cfg.random_state}),
            diagnostics=diagnostics,
        )


__all__ = ["UMAPConfig", "UMAPDecomposer"]
