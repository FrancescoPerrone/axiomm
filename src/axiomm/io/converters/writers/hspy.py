"""HyperSpy ``.hspy`` writer for the AXIOMM converter (spec §9.4).

:class:`HSpyWriter` persists a HyperSpy signal object to disk as an
``.hspy`` file via HyperSpy's native ``signal.save()``. It is one of
(potentially many) writers — AXIOMM does not assume HyperSpy-native
output — and it enforces the converter's safety rule: never silently
overwrite existing scientific data.

The writer does not import HyperSpy itself; it relies on the caller to
pass an object whose ``save()`` method writes ``.hspy``. In practice
this is always a HyperSpy ``BaseSignal`` / ``Signal1D`` / ``Signal2D``
produced by :class:`~axiomm.io.converters.signals.hyperspy_builder.HyperSpyBuilder`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from axiomm.io.converters.errors import OutputExistsError


class HSpyWriter:
    """Writer that produces HyperSpy ``.hspy`` files (spec §9.4)."""

    name = "hspy"
    supported_extensions = (".hspy",)

    def write(
        self,
        signal: Any,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Write ``signal`` to ``output_path`` and return the resolved :class:`Path`.

        Raises
        ------
        OutputExistsError
            ``output_path`` already exists and ``overwrite`` is ``False``.
            The message names the path and the flag to pass for replacement.
        """
        path = Path(output_path)
        if path.exists() and not overwrite:
            raise OutputExistsError(
                f"Output path already exists: {path}. "
                f"Pass overwrite=True to replace it, or use "
                f"skip_existing=True at the workflow layer to leave it alone."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        # We already gatekept overwrite above; pass overwrite=True down to
        # HyperSpy so it does not re-prompt for an existing target after we
        # have decided it is safe to replace.
        signal.save(str(path), overwrite=True)
        return path


__all__ = ["HSpyWriter"]
