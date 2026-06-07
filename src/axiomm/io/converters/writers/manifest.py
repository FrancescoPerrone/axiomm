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

Schema v2 (Chunk 10) groups AXIOMM-specific fields under
``"axiomm_metadata"`` so they mirror the ``signal.metadata.AXIOMM``
namespace exactly. v1 had them flat at the manifest root.
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
from axiomm.io.converters.metadata import build_axiomm_namespace
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    Diagnostic,
)


logger = logging.getLogger(__name__)


#: Sidecar suffix appended to the output file's name.
MANIFEST_SUFFIX = ".axiomm.json"

#: Schema version. Bump when the structure changes in a non-additive way.
MANIFEST_SCHEMA_VERSION = "2"


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
    extra_diagnostics: tuple[Diagnostic, ...] | list[Diagnostic] | None = None,
) -> dict[str, Any]:
    """Build the JSON-serialisable manifest dictionary (spec §9.5 + §15).

    Schema v2 layout::

        {
          "manifest_schema_version": "2",
          "axiomm_version":  "...",
          "created_at":      "<ISO 8601 UTC>",
          "input_path":      "...",
          "output_path":     "...",
          "reader_name":     "...",
          "writer_name":     "...",
          "source_shape":    [d0, d1, ...],
          "axiomm_metadata": {
              "converter": {reader, reader_version, config},
              "axes":      [...],
              "source":    {...},
              "provenance_classification": {observed, inferred, assumed},
              "diagnostics": [...]
          }
        }

    The top-level fields are the "manifest about the manifest" plus
    at-a-glance pointers (input/output paths, reader/writer names,
    shape). The ``axiomm_metadata`` subkey mirrors
    ``signal.metadata.AXIOMM`` exactly — both are built by
    :func:`~axiomm.io.converters.metadata.build_axiomm_namespace` so
    they cannot drift.
    """
    payload_axiomm = (
        payload.metadata.get("AXIOMM", {}) if payload.metadata else {}
    )
    converter_section = payload_axiomm.get("converter", {})
    classification = payload_axiomm.get("provenance_classification")

    extras = tuple(extra_diagnostics or ())
    all_diagnostics: tuple[Diagnostic, ...] = tuple(payload.diagnostics) + extras

    axiomm_metadata = build_axiomm_namespace(
        reader_name=converter_section.get("reader", reader_name),
        reader_version=converter_section.get("reader_version"),
        config=converter_section.get("config", {}),
        axes=payload.axes,
        provenance=payload.provenance,
        classification=classification,
        diagnostics=all_diagnostics,
    )

    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "axiomm_version": _axiomm_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "reader_name": reader_name,
        "writer_name": writer_name,
        "source_shape": _shape_of(payload.data),
        "axiomm_metadata": axiomm_metadata,
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
