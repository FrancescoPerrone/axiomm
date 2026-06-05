"""Writer protocol for the AXIOMM converter.

A writer persists a backend-specific signal object (or any other artefact a
builder produces) to disk. Writers must never silently overwrite scientific
output: when the target path exists and ``overwrite=False``, they must raise
:class:`~axiomm.io.converters.errors.OutputExistsError`. See spec §9.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Writer(Protocol):
    """Structural protocol that every concrete AXIOMM writer implements."""

    #: Stable short identifier used by the registry and the CLI (e.g. ``"hspy"``).
    name: str

    #: Tuple of file extensions this writer produces, lowercase, including
    #: the leading dot (e.g. ``(".hspy",)``).
    supported_extensions: tuple[str, ...]

    def write(
        self,
        signal: Any,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Persist ``signal`` to ``output_path`` and return the written path.

        Implementations must raise
        :class:`~axiomm.io.converters.errors.OutputExistsError` when
        ``output_path`` already exists and ``overwrite`` is ``False``.
        """
        ...


__all__ = ["Writer"]
