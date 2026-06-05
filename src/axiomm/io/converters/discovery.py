"""Input discovery for the AXIOMM converter.

The discovery component resolves a user-supplied file or directory into a
deterministic list of input file paths. It does not open the files, it does
not parse their contents, and it never prompts the user or shows a GUI.

See spec §6.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from axiomm.io.converters.errors import InputDiscoveryError


def discover_inputs(
    input_path: str | Path,
    *,
    extensions: tuple[str, ...] | None = None,
    sample: str | None = None,
    recursive: bool = False,
    require_non_empty: bool = True,
) -> list[Path]:
    """Resolve ``input_path`` into a sorted list of concrete input file paths.

    Parameters
    ----------
    input_path
        A file or directory path.

        - If a file, the returned list contains that single path (after
          existence and type validation). Extension and sample filters are
          *not* applied to an explicitly given file: pointing at a file is
          treated as an explicit user choice that overrides filtering.
        - If a directory, files inside are filtered by ``extensions`` and
          ``sample`` and returned sorted.
    extensions
        Tuple of file extensions to keep, each including the leading dot
        (e.g. ``(".h5", ".hdf5")``). Matched case-insensitively against
        each candidate's suffix. ``None`` disables extension filtering.
    sample
        Substring required in each candidate's *file name* (not full path).
        ``None`` disables sample filtering. Matching is substring-based and
        case-sensitive for the MVP; the signature is intentionally shaped
        so that future regex matching can be added without breaking
        callers (spec §6.4).
    recursive
        If ``True`` and ``input_path`` is a directory, descend into
        subdirectories. Ignored when ``input_path`` is a file.
    require_non_empty
        If ``True`` (the default) and no files match, raise
        :class:`InputDiscoveryError`. If ``False``, return an empty list.

    Returns
    -------
    list[Path]
        Sorted list of resolved file paths.

    Raises
    ------
    InputDiscoveryError
        Raised when:

        - ``input_path`` does not exist;
        - ``input_path`` exists but is neither a file nor a directory;
        - no files match and ``require_non_empty`` is ``True``.
    """
    path = Path(input_path)

    if not path.exists():
        raise InputDiscoveryError(f"Input path does not exist: {path}")

    if path.is_file():
        return [path]

    if not path.is_dir():
        raise InputDiscoveryError(
            f"Input path is neither a file nor a directory: {path}"
        )

    candidates: Iterable[Path] = path.rglob("*") if recursive else path.iterdir()
    matched = sorted(
        p
        for p in candidates
        if p.is_file() and _matches(p, extensions=extensions, sample=sample)
    )

    if not matched and require_non_empty:
        raise InputDiscoveryError(_describe_no_match(path, extensions, sample, recursive))

    return matched


def _matches(
    candidate: Path,
    *,
    extensions: tuple[str, ...] | None,
    sample: str | None,
) -> bool:
    """Return ``True`` if ``candidate`` passes the extension and sample filters."""
    if extensions is not None:
        wanted = tuple(ext.lower() for ext in extensions)
        if candidate.suffix.lower() not in wanted:
            return False
    if sample is not None and sample not in candidate.name:
        return False
    return True


def _describe_no_match(
    directory: Path,
    extensions: tuple[str, ...] | None,
    sample: str | None,
    recursive: bool,
) -> str:
    parts = [f"directory={directory}{os.sep if not str(directory).endswith(os.sep) else ''}"]
    if extensions is not None:
        parts.append(f"extensions={extensions!r}")
    if sample is not None:
        parts.append(f"sample={sample!r}")
    parts.append(f"recursive={recursive}")
    return "No matching input files found (" + ", ".join(parts) + ")."


__all__ = ["discover_inputs"]
