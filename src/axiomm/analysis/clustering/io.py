"""Versioned file adapters for clustering payloads.

Internal adapter (v1), **not** a stable public persistence contract. The
sidecar carries ``schema_version`` and records shapes, ``cluster_ids``
ordering, backend metadata, and provenance; the ``.npz`` preserves
numeric dtypes. Refuses to silently overwrite.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from axiomm.analysis.clustering.models import ClusteringResult, ClusterMeanSpectra
from axiomm.analysis.errors import OutputExistsError, PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

SCHEMA_VERSION = 1


def _load_sidecar(path: Path, expected_kind: str) -> dict:
    """Load a sidecar, enforcing schema version and payload kind (P10)."""
    if not path.exists():
        raise PayloadValidationError(f"{path} does not exist.")
    try:
        sidecar = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PayloadValidationError(f"{path.name}: malformed JSON ({exc}).") from exc
    if not isinstance(sidecar, dict):
        raise PayloadValidationError(f"{path.name}: sidecar is not a JSON object.")
    version = sidecar.get("schema_version")
    if version != SCHEMA_VERSION:
        raise PayloadValidationError(
            f"{path.name}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION})."
        )
    kind = sidecar.get("kind")
    if kind != expected_kind:
        raise PayloadValidationError(
            f"{path.name}: expected payload kind {expected_kind!r}, got {kind!r}."
        )
    return sidecar


def _prov_to_dict(prov: AnalysisProvenance | None):
    if prov is None:
        return None
    return {
        "tool": prov.tool,
        "backend": prov.backend,
        "tool_version": prov.tool_version,
        "params": dict(prov.params),
    }


def _prov_from_dict(d):
    if d is None:
        return None
    return AnalysisProvenance(
        tool=d["tool"],
        backend=d["backend"],
        tool_version=d["tool_version"],
        params=d["params"],
    )


def _diags_to_list(diagnostics):
    return [
        {"severity": d.severity, "code": d.code, "message": d.message,
         "context": dict(d.context)}
        for d in diagnostics
    ]


def _diags_from_list(items):
    return [
        Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                   context=d["context"])
        for d in items
    ]


def _guard(paths, overwrite):
    if overwrite:
        return
    for path in paths:
        if path.exists():
            raise OutputExistsError(
                f"{path} already exists; pass overwrite=True to replace it."
            )


def write_clustering(result: ClusteringResult, directory, stem: str,
                     *, overwrite: bool = False) -> tuple[Path, Path]:
    """Write ``result`` to ``<stem>_clustering.{npz,json}``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    npz_path = directory / f"{stem}_clustering.npz"
    json_path = directory / f"{stem}_clustering.json"
    _guard((npz_path, json_path), overwrite)

    np.savez(npz_path, labels=result.labels, label_map=result.label_map,
             cluster_ids=result.cluster_ids)
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "kind": "clustering",
        "n_clusters": result.n_clusters,
        "label_map_shape": list(result.label_map.shape),
        "provenance": _prov_to_dict(result.provenance),
        "diagnostics": _diags_to_list(result.diagnostics),
    }
    json_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False))
    return npz_path, json_path


def read_clustering(directory, stem: str) -> ClusteringResult:
    """Read a ClusteringResult written by :func:`write_clustering`."""
    directory = Path(directory)
    npz = np.load(directory / f"{stem}_clustering.npz")
    sidecar = _load_sidecar(directory / f"{stem}_clustering.json", "clustering")
    return ClusteringResult(
        labels=npz["labels"],
        label_map=npz["label_map"],
        cluster_ids=npz["cluster_ids"],
        n_clusters=int(sidecar["n_clusters"]),
        provenance=_prov_from_dict(sidecar["provenance"]),
        diagnostics=_diags_from_list(sidecar["diagnostics"]),
    )


def write_cluster_means(means: ClusterMeanSpectra, directory, stem: str,
                        *, overwrite: bool = False) -> tuple[Path, Path]:
    """Write ``means`` to ``<stem>_cluster_means.{npz,json}``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    npz_path = directory / f"{stem}_cluster_means.npz"
    json_path = directory / f"{stem}_cluster_means.json"
    _guard((npz_path, json_path), overwrite)

    # Persist the enrichment arrays too (P1): heterogeneity / total_counts are
    # what the reliability gate consumes; dropping them makes a round-tripped
    # means object un-assessable. NaN entries (empty/degenerate clusters) are
    # numeric and live in the .npz, never in the strict-JSON sidecar.
    payload = {
        "means": means.means,
        "pixel_counts": means.pixel_counts,
        "cluster_ids": means.cluster_ids,
    }
    if means.heterogeneity is not None:
        payload["heterogeneity"] = np.asarray(means.heterogeneity, dtype=float)
    if means.total_counts is not None:
        payload["total_counts"] = np.asarray(means.total_counts, dtype=float)
    np.savez(npz_path, **payload)
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "kind": "cluster_means",
        "n_clusters": means.n_clusters,
        "means_shape": list(means.means.shape),
        "has_heterogeneity": means.heterogeneity is not None,
        "has_total_counts": means.total_counts is not None,
        "provenance": _prov_to_dict(means.provenance),
        "diagnostics": _diags_to_list(means.diagnostics),
    }
    json_path.write_text(json.dumps(sidecar, indent=2, allow_nan=False))
    return npz_path, json_path


def read_cluster_means(directory, stem: str) -> ClusterMeanSpectra:
    """Read a ClusterMeanSpectra written by :func:`write_cluster_means`."""
    directory = Path(directory)
    npz = np.load(directory / f"{stem}_cluster_means.npz")
    sidecar = _load_sidecar(directory / f"{stem}_cluster_means.json", "cluster_means")
    heterogeneity = npz["heterogeneity"] if "heterogeneity" in npz.files else None
    total_counts = npz["total_counts"] if "total_counts" in npz.files else None
    return ClusterMeanSpectra(
        means=npz["means"],
        pixel_counts=npz["pixel_counts"],
        cluster_ids=npz["cluster_ids"],
        n_clusters=int(sidecar["n_clusters"]),
        heterogeneity=heterogeneity,
        total_counts=total_counts,
        provenance=_prov_from_dict(sidecar["provenance"]),
        diagnostics=_diags_from_list(sidecar["diagnostics"]),
    )


__all__ = [
    "SCHEMA_VERSION",
    "read_cluster_means",
    "read_clustering",
    "write_cluster_means",
    "write_clustering",
]
