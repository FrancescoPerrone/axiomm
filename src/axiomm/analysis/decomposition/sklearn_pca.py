"""scikit-learn PCA backend — the canonical default decomposer.

Operates on the neutral AxiommSignalPayload via the shared validating
reshape helper. scikit-learn is imported lazily inside ``decompose`` so
importing this module never requires it. No component count is baked in
(n_components=None keeps all); laziness is never forced — a lazy array is
materialized only with a diagnostic.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.decomposition.models import DecompositionResult
from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.reshape import pixels_by_channels


class SklearnPCADecomposer:
    """PCA via ``sklearn.decomposition.PCA`` on the neutral payload.

    ``random_state`` seeds scikit-learn's randomized SVD solver, which
    ``svd_solver="auto"`` selects for large matrices. It defaults to ``0`` so
    the decomposition — and therefore the whole downstream pipeline — is
    **reproducible by default**; pass ``random_state=None`` for run-to-run
    variability. It is ignored by the exact ("full") solver.
    """

    name = "pca"

    def __init__(self, random_state: int | None = 0) -> None:
        self.random_state = random_state

    def decompose(self, payload, *, n_components: int | None = None) -> DecompositionResult:
        diagnostics: list[Diagnostic] = []

        flat = pixels_by_channels(payload)
        if not isinstance(payload.data, np.ndarray):
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "lazy_materialized",
                    "Input data was materialized into memory for PCA "
                    "(this backend cannot consume lazy arrays).",
                )
            )

        X = flat.matrix
        n_pixels, n_channels = flat.n_pixels, flat.n_channels
        nav_shape = flat.nav_shape

        max_components = min(n_pixels, n_channels)
        if n_components is not None and n_components > max_components:
            raise PayloadValidationError(
                f"n_components={n_components} exceeds max {max_components} "
                f"(min of n_pixels={n_pixels}, n_channels={n_channels})."
            )

        from sklearn.decomposition import PCA

        pca = PCA(n_components=n_components, random_state=self.random_state)
        loadings = pca.fit_transform(X)
        factors = pca.components_.T
        evr = pca.explained_variance_ratio_
        resolved = int(pca.n_components_)

        diagnostics.append(
            Diagnostic(
                "info",
                "explained_variance_total",
                f"Total explained variance {float(evr.sum()):.4f} over {resolved} components.",
            )
        )

        return DecompositionResult(
            factors=factors,
            loadings=loadings,
            explained_variance_ratio=evr,
            nav_shape=nav_shape,
            n_components=resolved,
            provenance=AnalysisProvenance(
                tool="decomposition",
                backend=self.name,
                params={"n_components": n_components, "random_state": self.random_state},
            ),
            diagnostics=diagnostics,
        )


__all__ = ["SklearnPCADecomposer"]
