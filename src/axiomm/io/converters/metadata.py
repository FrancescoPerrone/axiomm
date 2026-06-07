"""AXIOMM metadata namespace composition (spec §15).

The AXIOMM metadata namespace — the dict that sits at
``signal.metadata.AXIOMM`` after a conversion, and (mirror-image) inside
a manifest sidecar — is built from small composable transformers
defined here.

Each transformer does one job:

* :func:`nest_converter_section` — describe *which converter* ran.
* :func:`nest_axes_section` — list the axes.
* :func:`nest_source_section` — describe *where the data came from*.
* :func:`diagnostics_to_dicts` — turn :class:`Diagnostic` objects into
  JSON-friendly dicts.
* :func:`build_axiomm_namespace` — orchestrator that composes the four
  above into the nested layout suggested by spec §15.

The builder (`HyperSpyBuilder`) and the manifest writer
(`ManifestWriter`) both consume these helpers, so the canonical
"shape of an AXIOMM metadata namespace" lives in exactly one place.
"""

from __future__ import annotations

from typing import Any, Mapping

from axiomm.io.converters.models import (
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)


# ---------------------------------------------------------------------------
# Composable transformers — each does one thing, independently usable
# ---------------------------------------------------------------------------

def nest_converter_section(
    *,
    reader_name: str,
    reader_version: str | None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the ``"converter"`` subsection of the AXIOMM namespace.

    Captures *which converter ran* and *with what configuration*. Does
    not look at the data or the source file.
    """
    return {
        "reader": reader_name,
        "reader_version": reader_version,
        "config": dict(config or {}),
    }


def nest_axes_section(axes: tuple[AxisSpec, ...]) -> list[dict[str, Any]]:
    """Return the ``"axes"`` subsection — a list of plain-dict axis records.

    JSON-friendly (no numpy scalars, no dataclass instances) so the
    result can go straight into a manifest or any signal-backend
    metadata tree.
    """
    return [
        {
            "name": ax.name,
            "role": ax.role,
            "size": ax.size,
            "units": ax.units,
            "scale": ax.scale,
            "offset": ax.offset,
            "index_in_array": ax.index_in_array,
        }
        for ax in axes
    ]


def nest_source_section(
    provenance: SourceProvenance | None,
) -> dict[str, Any] | None:
    """Return the ``"source"`` subsection from a :class:`SourceProvenance`.

    Returns ``None`` when no provenance is available so the namespace
    can omit the key cleanly. Paths are stringified for JSON safety.
    """
    if provenance is None:
        return None
    return {
        "path": str(provenance.path),
        "reader": provenance.reader,
        "reader_version": provenance.reader_version,
        "input_hash": provenance.input_hash,
    }


def diagnostics_to_dicts(diagnostics) -> list[dict[str, Any]]:
    """Convert an iterable of :class:`Diagnostic` to plain JSON-friendly dicts.

    Used by the builder (to put diagnostics under the signal's metadata
    namespace) and by the manifest writer (to embed them in the
    sidecar). Single canonical serialisation.
    """
    return [
        {
            "severity": d.severity,
            "code": d.code,
            "message": d.message,
            "context": dict(d.context),
        }
        for d in diagnostics
    ]


def nest_classification(
    classification: Mapping[str, list[str]] | None,
) -> dict[str, list[str]]:
    """Normalise a provenance classification into the three-bucket schema.

    Always returns a dict with exactly the keys
    ``"observed"``, ``"inferred"``, ``"assumed"`` — even when the
    incoming dict is missing buckets or is ``None``. Keeps the
    AXIOMM namespace schema stable across readers that classify and
    readers that don't.
    """
    src = dict(classification or {})
    return {
        "observed": list(src.get("observed", [])),
        "inferred": list(src.get("inferred", [])),
        "assumed": list(src.get("assumed", [])),
    }


# ---------------------------------------------------------------------------
# Orchestrator — composes the four sections
# ---------------------------------------------------------------------------

def build_axiomm_namespace(
    *,
    reader_name: str,
    reader_version: str | None,
    config: Mapping[str, Any] | None,
    axes: tuple[AxisSpec, ...],
    provenance: SourceProvenance | None,
    classification: Mapping[str, list[str]] | None,
    diagnostics,
) -> dict[str, Any]:
    """Build the full nested AXIOMM metadata namespace (spec §15 layout).

    Returns a dict with the structure::

        {
          "converter": {reader, reader_version, config},
          "axes":      [axis_dict, axis_dict, ...],
          "source":    {path, reader, reader_version, input_hash} | None,
          "provenance_classification": {observed, inferred, assumed},
          "diagnostics": [diagnostic_dict, ...],
        }

    The orchestrator is pure composition; every leaf comes from a
    dedicated transformer above. Callers (the HyperSpy builder and the
    manifest writer) get the same canonical layout from a single
    function call.
    """
    namespace: dict[str, Any] = {
        "converter": nest_converter_section(
            reader_name=reader_name,
            reader_version=reader_version,
            config=config,
        ),
        "axes": nest_axes_section(axes),
        "provenance_classification": nest_classification(classification),
        "diagnostics": diagnostics_to_dicts(diagnostics),
    }
    source = nest_source_section(provenance)
    if source is not None:
        namespace["source"] = source
    return namespace


__all__ = [
    "build_axiomm_namespace",
    "diagnostics_to_dicts",
    "nest_axes_section",
    "nest_classification",
    "nest_converter_section",
    "nest_source_section",
]
