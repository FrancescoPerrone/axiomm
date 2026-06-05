"""Reader protocol for the AXIOMM converter.

A reader converts a source file into an :class:`AxiommSignalPayload`. It knows
file-format details (e.g. HDF5 paths, vendor binary layouts) but must not know
about UX, CLI, GUI, or output-directory policy. See spec §7.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from axiomm.io.converters.models import AxiommSignalPayload


@runtime_checkable
class Reader(Protocol):
    """Structural protocol that every concrete AXIOMM reader implements."""

    #: Stable short identifier used by the registry and the CLI (e.g. ``"xrmmap_h5"``).
    name: str

    #: Tuple of file extensions this reader claims to support, lowercase,
    #: including the leading dot (e.g. ``(".h5", ".hdf5")``).
    supported_extensions: tuple[str, ...]

    def can_read(self, path: str | Path) -> bool:
        """Return ``True`` if this reader believes it can read ``path``.

        Implementations should be cheap — typically an extension check plus a
        lightweight signature peek. Heavy validation belongs in :meth:`read`.
        """
        ...

    def read(self, path: str | Path, *, lazy: bool = True) -> AxiommSignalPayload:
        """Read ``path`` and return a populated :class:`AxiommSignalPayload`.

        Parameters
        ----------
        path
            Source file path.
        lazy
            Whether to keep large datasets file-backed where possible. Readers
            that do not yet support lazy access must still accept the keyword
            and document their actual behaviour in diagnostics.
        """
        ...


__all__ = ["Reader"]
