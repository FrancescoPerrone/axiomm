"""Manifest writer for the AXIOMM converter (spec §9.5).

The manifest is a JSON sidecar named ``<output>.axiomm.json`` placed
next to a converted output file. It records what went into the
conversion (input path, reader, config used) and what came out (output
path, axes summary), plus the scientific-metadata classification
(spec §15) and the structured diagnostics. Together with the converted
file, the manifest makes an AXIOMM conversion *reproducible*: a third
party can read the manifest and know exactly which assumptions and
fallbacks were applied.

The format intentionally uses a small, evolvable JSON schema. Each
manifest carries a ``manifest_schema_version`` so future readers can
gate behaviour on the schema they see.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from axiomm import __version__ as _axiomm_version
from axiomm.io.converters.errors import OutputExistsError
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    Diagnostic,
)


logger = logging.getLogger(__name__)


#: Sidecar suffix appended to the output file's name.
MANIFEST_SUFFIX = ".axiomm.json"

#: Schema version. Bump when the structure changes in a non-additive way.
MANIFEST_SCHEMA_VERSION = "1"


def manifest_path_for(output_path: str | Path) -> Path:
    """Return the canonical manifest sidecar path for ``output_path``.

    For ``A21_054.hspy`` this returns ``A21_054.hspy.axiomm.json`` —
    the full output file name is preserved so the link between
    artefact and manifest is always visually obvious.
    """
    p = Path(output_path)
    return p.with_name(p.name + MANIFEST_SUFFIX)


def build_manifest_dict(
    *,
    input_path: Path,
    output_path: Path,
    reader_name: str,
    writer_name: str,
    payload: AxiommSignalPayload,
    config_used: dict[str, Any] | None = None,
    extra_diagnostics: tuple[Diagnostic, ...] | list[Diagnostic] | None = None,
) -> dict[str, Any]:
    """Build the JSON-serialisable manifest dictionary (spec §9.5 + §15).

    The result is plain JSON-friendly types (str, int, float, None,
    list, dict) — no numpy or pathlib leakage — so it survives
    ``json.dumps`` without a custom encoder.
    """
    extras = tuple(extra_diagnostics or ())
    all_diagnostics: tuple[Diagnostic, ...] = tuple(payload.diagnostics) + extras
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "axiomm_version": _axiomm_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "reader_name": reader_name,
        "writer_name": writer_name,
        "source_shape": _shape_of(payload.data),
        "axes_summary": _axes_summary(payload.axes),
        "config_used": dict(config_used or {}),
        "provenance_classification": _provenance_classification(payload),
        "diagnostics": [_diagnostic_dict(d) for d in all_diagnostics],
    }


def extract_reader_config(reader: Any) -> dict[str, Any]:
    """Return ``reader.config`` as a JSON-friendly dict, if available.

    Generic over any reader that exposes a dataclass ``config``
    attribute. Returns ``{}`` for readers without one — keeping
    third-party readers compatible without forcing a config dataclass.
    """
    cfg = getattr(reader, "config", None)
    if cfg is None or not is_dataclass(cfg):
        return {}
    return asdict(cfg)


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------

def _shape_of(data: Any) -> list[int] | None:
    shape = getattr(data, "shape", None)
    if shape is None:
        return None
    return [int(x) for x in shape]


def _axes_summary(axes: tuple[AxisSpec, ...]) -> list[dict[str, Any]]:
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


def _diagnostic_dict(d: Diagnostic) -> dict[str, Any]:
    return {
        "severity": d.severity,
        "code": d.code,
        "message": d.message,
        "context": dict(d.context),
    }


def _provenance_classification(payload: AxiommSignalPayload) -> dict[str, list[str]]:
    """Pull the classification dict from the payload's AXIOMM namespace.

    Falls back to an empty three-bucket structure if no classification
    was recorded — keeps the manifest schema stable across readers.
    """
    axiomm_meta = payload.metadata.get("AXIOMM", {}) if payload.metadata else {}
    classification = axiomm_meta.get(
        "provenance_classification",
        {"observed": [], "inferred": [], "assumed": []},
    )
    # Defensive: always present all three buckets.
    return {
        "observed": list(classification.get("observed", [])),
        "inferred": list(classification.get("inferred", [])),
        "assumed": list(classification.get("assumed", [])),
    }


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class ManifestWriter:
    """Writes a JSON manifest sidecar to disk.

    Unlike :class:`HSpyWriter`, the writer's ``write`` method takes the
    already-built manifest dictionary (built by
    :func:`build_manifest_dict`) rather than a signal object. This
    keeps the writer narrowly responsible for serialisation; manifest
    composition lives in :func:`build_manifest_dict`.
    """

    name = "manifest"
    supported_extensions = (MANIFEST_SUFFIX,)

    def write(
        self,
        manifest: dict[str, Any],
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        path = Path(output_path)
        if path.exists() and not overwrite:
            raise OutputExistsError(
                f"Manifest output path already exists: {path}. "
                f"Pass overwrite=True to replace it."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
        logger.info("Wrote AXIOMM manifest to %s", path)
        return path


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "MANIFEST_SUFFIX",
    "ManifestWriter",
    "build_manifest_dict",
    "extract_reader_config",
    "manifest_path_for",
]
