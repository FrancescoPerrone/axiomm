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

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.clustering.models import ClusterMeanSpectra, ClusteringResult

SCHEMA_VERSION = 1


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
    json_path.write_text(json.dumps(sidecar, indent=2))
    return npz_path, json_path


def read_clustering(directory, stem: str) -> ClusteringResult:
    """Read a ClusteringResult written by :func:`write_clustering`."""
    directory = Path(directory)
    npz = np.load(directory / f"{stem}_clustering.npz")
    sidecar = json.loads((directory / f"{stem}_clustering.json").read_text())
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

    np.savez(npz_path, means=means.means, pixel_counts=means.pixel_counts,
             cluster_ids=means.cluster_ids)
    sidecar = {
        "schema_version": SCHEMA_VERSION,
        "kind": "cluster_means",
        "n_clusters": means.n_clusters,
        "means_shape": list(means.means.shape),
        "provenance": _prov_to_dict(means.provenance),
        "diagnostics": _diags_to_list(means.diagnostics),
    }
    json_path.write_text(json.dumps(sidecar, indent=2))
    return npz_path, json_path


def read_cluster_means(directory, stem: str) -> ClusterMeanSpectra:
    """Read a ClusterMeanSpectra written by :func:`write_cluster_means`."""
    directory = Path(directory)
    npz = np.load(directory / f"{stem}_cluster_means.npz")
    sidecar = json.loads((directory / f"{stem}_cluster_means.json").read_text())
    return ClusterMeanSpectra(
        means=npz["means"],
        pixel_counts=npz["pixel_counts"],
        cluster_ids=npz["cluster_ids"],
        n_clusters=int(sidecar["n_clusters"]),
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
