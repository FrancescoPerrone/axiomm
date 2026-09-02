"""The Decomposer protocol.

Backends implement this structurally (runtime-checkable). Input is the
converter's neutral payload; output is a DecompositionResult. Both are
referenced only in annotations, imported under TYPE_CHECKING so this
module stays import-light and free of cycles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from axiomm.io.converters.models import AxiommSignalPayload
    from axiomm.analysis.decomposition.models import DecompositionResult


@runtime_checkable
class Decomposer(Protocol):
    """A dimensionality-reduction backend.

    ``n_components=None`` means "no forced reduction" — keep
    ``min(n_pixels, n_channels)`` components. The user chooses any
    integer to reduce further; no value is baked in.
    """

    name: str

    def decompose(
        self,
        payload: "AxiommSignalPayload",
        *,
        n_components: int | None = None,
    ) -> "DecompositionResult": ...


__all__ = ["Decomposer"]
