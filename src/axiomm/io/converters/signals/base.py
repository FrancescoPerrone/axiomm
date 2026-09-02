"""SignalBuilder protocol for the AXIOMM converter.

The spec (§8) describes the first concrete builder as a HyperSpy adapter, but
AXIOMM is designed to allow alternative backends (xarray, RosettaSciIO dicts,
plain numpy, etc.). This protocol is the seam that future backends plug into,
so core code never depends on HyperSpy directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from axiomm.io.converters.models import AxiommSignalPayload


@runtime_checkable
class SignalBuilder(Protocol):
    """Structural protocol that every concrete signal builder implements."""

    #: Stable short identifier (e.g. ``"hyperspy"``, ``"xarray"``).
    name: str

    def build(self, payload: AxiommSignalPayload) -> Any:
        """Construct a backend-specific signal object from ``payload``.

        Implementations should:

        * resolve ``payload.signal_kind`` deterministically (no silent
          fallback to ``"base"`` when the user asked for ``"signal1d"``);
        * validate axes against ``payload.data`` shape where possible
          before building, raising
          :class:`~axiomm.io.converters.errors.SignalValidationError` on
          mismatch;
        * copy ``payload.metadata``, ``payload.original_metadata``,
          ``payload.provenance`` and ``payload.diagnostics`` into the
          backend object under an ``AXIOMM`` namespace.

        Returns
        -------
        Any
            The backend-specific signal object. The concrete return type is
            backend-dependent; the protocol stays generic on purpose.
        """
        ...


__all__ = ["SignalBuilder"]
