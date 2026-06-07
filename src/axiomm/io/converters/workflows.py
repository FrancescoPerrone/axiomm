"""Workflow orchestration for the AXIOMM converter (spec §11).

:func:`convert_file` is the single public entry point that drives the
four core components end-to-end: it resolves a reader, reads the source
file, builds a HyperSpy signal, writes it as ``.hspy``, and returns a
:class:`~axiomm.io.converters.models.ConversionResult`.

A full reader/writer plugin registry (spec §12) is a Phase 3 deliverable.
For now a tiny built-in mapping handles the named lookups (``"xrmmap_h5"``,
``"hspy"``) and the ``reader="auto"`` dispatch. Adding a new reader or
writer to the mapping is a single-line change and does not block adding
the real registry later.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from axiomm.io.converters.errors import (
    ReaderDetectionError,
    UnsupportedFormatError,
)
from axiomm.io.converters.models import (
    ConversionResult,
    Diagnostic,
)
from axiomm.io.converters.readers.base import Reader
from axiomm.io.converters.writers.base import Writer


logger = logging.getLogger(__name__)


# Name → "module:ClassName" pointer. Resolved lazily so the workflow
# module stays importable without h5py / hyperspy installed.
_BUILTIN_READERS: dict[str, str] = {
    "xrmmap_h5": "axiomm.io.converters.readers.xrmmap_h5:XRMMapH5Reader",
}

_BUILTIN_WRITERS: dict[str, str] = {
    "hspy": "axiomm.io.converters.writers.hspy:HSpyWriter",
}


def _import_string(spec: str) -> Any:
    module_name, attr = spec.split(":", 1)
    return getattr(importlib.import_module(module_name), attr)


def _instantiate_reader(name: str) -> Reader:
    return _import_string(_BUILTIN_READERS[name])()


def _resolve_reader(reader: str | Reader, path: Path) -> Reader:
    if not isinstance(reader, str):
        return reader
    if reader == "auto":
        return _auto_resolve_reader(path)
    if reader in _BUILTIN_READERS:
        return _instantiate_reader(reader)
    raise UnsupportedFormatError(
        f"Unknown reader name {reader!r}. Known readers: "
        f"{sorted(_BUILTIN_READERS)} (plus 'auto')."
    )


def _auto_resolve_reader(path: Path) -> Reader:
    """Iterate registered readers and pick the (single) one that accepts ``path``."""
    candidates: list[Reader] = []
    for name in _BUILTIN_READERS:
        instance = _instantiate_reader(name)
        try:
            accepts = instance.can_read(path)
        except Exception:  # noqa: BLE001 - workflow boundary: see spec §13
            accepts = False
        if accepts:
            candidates.append(instance)

    if not candidates:
        raise ReaderDetectionError(
            f"No registered reader can read {path}. "
            f"Pass reader=<name> explicitly. Known readers: "
            f"{sorted(_BUILTIN_READERS)}."
        )
    if len(candidates) > 1:
        names = [c.name for c in candidates]
        raise ReaderDetectionError(
            f"Multiple registered readers accept {path}: {names!r}. "
            f"Pass reader=<name> explicitly to disambiguate."
        )
    return candidates[0]


def _resolve_writer(writer: str | Writer) -> Writer:
    if not isinstance(writer, str):
        return writer
    if writer in _BUILTIN_WRITERS:
        return _import_string(_BUILTIN_WRITERS[writer])()
    raise UnsupportedFormatError(
        f"Unknown writer name {writer!r}. Known writers: "
        f"{sorted(_BUILTIN_WRITERS)}."
    )


def _resolve_output_path(
    input_path: Path,
    output_path: str | Path | None,
    output_dir: str | Path | None,
    writer: Writer,
) -> Path:
    """Apply the spec §11.2 output-resolution rules.

    Explicit ``output_path`` wins. Otherwise ``output_dir`` is combined
    with the input file stem and the writer's first supported extension.
    Otherwise the input path is rewritten with that extension in place.
    """
    if output_path is not None:
        return Path(output_path)
    default_ext = (
        writer.supported_extensions[0]
        if writer.supported_extensions
        else ".out"
    )
    if output_dir is not None:
        return Path(output_dir) / (input_path.stem + default_ext)
    return input_path.with_suffix(default_ext)


def convert_file(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    reader: str | Reader = "auto",
    writer: str | Writer = "hspy",
    overwrite: bool = False,
    skip_existing: bool = False,
    manifest: bool = True,
    lazy: bool = True,
) -> ConversionResult:
    """Convert a single source file end-to-end (spec §11.2).

    Parameters
    ----------
    input_path
        Path to the source file.
    output_path
        Explicit output path. Wins over ``output_dir``.
    output_dir
        If set (and ``output_path`` is ``None``), the output goes to
        ``output_dir / (input_path.stem + writer_extension)``.
    reader
        Either a reader instance, a registered reader name (e.g.
        ``"xrmmap_h5"``), or ``"auto"`` to dispatch by ``can_read``.
    writer
        Either a writer instance or a registered writer name (default
        ``"hspy"``).
    overwrite
        Replace an existing output file. AXIOMM never silently
        overwrites scientific data: by default an existing output
        raises :class:`OutputExistsError`.
    skip_existing
        Leave an existing output untouched and return a result pointing
        at it (no read, no build, no write). Useful for re-running a
        batch and skipping already-converted files. ``skip_existing``
        is checked *before* ``overwrite``, so if both are true the file
        is skipped.
    manifest
        If ``True`` (the default), write a JSON sidecar manifest at
        ``<output_path>.axiomm.json`` (spec §9.5) and populate
        ``ConversionResult.manifest_path`` with its path. The manifest
        records input/output paths, reader/writer used, the reader's
        configuration, the axes summary, the structured diagnostics,
        and the observed / inferred / assumed metadata classification
        (spec §15) — everything needed to reproduce or audit the
        conversion. If ``False``, no sidecar is written and
        ``manifest_path`` is ``None``.
    lazy
        Forwarded to the reader's ``read(..., lazy=...)``. Each reader
        documents its own lazy behaviour; the current
        :class:`XRMMapH5Reader` is eager and emits a diagnostic noting
        the downgrade.

    Returns
    -------
    ConversionResult
        A frozen result with the resolved input/output paths, the
        reader and writer names actually used, and the diagnostics
        collected along the way (reader diagnostics first, then any
        added by the workflow itself).

    Raises
    ------
    ReaderDetectionError
        ``reader="auto"`` and no (or multiple) registered readers
        accept the file.
    UnsupportedFormatError
        ``reader`` or ``writer`` is a string that does not name a
        registered component.
    OutputExistsError
        Output exists and neither ``overwrite`` nor ``skip_existing``
        was requested.
    """
    src = Path(input_path)
    resolved_reader = _resolve_reader(reader, src)
    resolved_writer = _resolve_writer(writer)
    out = _resolve_output_path(src, output_path, output_dir, resolved_writer)

    extra_diagnostics: list[Diagnostic] = []
    logger.info(
        "convert_file(%s) -> %s (reader=%s, writer=%s)",
        src, out, resolved_reader.name, resolved_writer.name,
    )

    if skip_existing and out.exists():
        extra_diagnostics.append(
            Diagnostic(
                severity="info",
                code="output_skipped_existing",
                message=f"Existing output left untouched: {out}",
            )
        )
        logger.info("Skipping existing output: %s", out)
        return ConversionResult(
            input_path=src,
            output_path=out,
            manifest_path=None,
            reader_name=resolved_reader.name,
            writer_name=resolved_writer.name,
            diagnostics=tuple(extra_diagnostics),
        )

    payload = resolved_reader.read(src, lazy=lazy)

    # Build the backend signal. The builder is hard-wired to HyperSpy in
    # Chunk 5; an explicit `builder` parameter and registry can be added
    # alongside the second concrete builder, per the generality rule.
    from axiomm.io.converters.signals.hyperspy_builder import (
        build_hyperspy_signal,
    )

    signal = build_hyperspy_signal(payload)
    written_path = resolved_writer.write(signal, out, overwrite=overwrite)

    manifest_path: Path | None = None
    if manifest:
        from axiomm.io.converters.writers.manifest import (
            ManifestWriter,
            build_manifest_dict,
            extract_reader_config,
            manifest_path_for,
        )

        manifest_dict = build_manifest_dict(
            input_path=src,
            output_path=written_path,
            reader_name=resolved_reader.name,
            writer_name=resolved_writer.name,
            payload=payload,
            config_used=extract_reader_config(resolved_reader),
            extra_diagnostics=extra_diagnostics,
        )
        manifest_path = ManifestWriter().write(
            manifest_dict,
            manifest_path_for(written_path),
            overwrite=overwrite,
        )

    return ConversionResult(
        input_path=src,
        output_path=written_path,
        manifest_path=manifest_path,
        reader_name=resolved_reader.name,
        writer_name=resolved_writer.name,
        diagnostics=tuple(payload.diagnostics) + tuple(extra_diagnostics),
    )


__all__ = ["convert_file"]
