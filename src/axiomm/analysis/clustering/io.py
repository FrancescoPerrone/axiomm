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
from axiomm.analysis.errors import (
    OutputExistsError,
    PayloadSerializationError,
)
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

SCHEMA_VERSION = 2   # v2: cluster_means gained heterogeneity/total_counts (P1);
                     # bumped rather than silently reusing v1 for a new shape.


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_integer_ids(arr: np.ndarray, where: str) -> None:
    if not np.issubdtype(np.asarray(arr).dtype, np.integer):
        raise PayloadSerializationError(
            f"{where}: cluster_ids must be an integer array ({np.asarray(arr).dtype})."
        )
    if np.unique(arr).size != np.asarray(arr).size:
        raise PayloadSerializationError(f"{where}: cluster_ids contains duplicates.")


def _check_cluster_means_arrays(means, pixel_counts, cluster_ids,
                                heterogeneity, total_counts, where: str) -> None:
    """Shared array invariants for cluster-means, used on read AND before write."""
    means = np.asarray(means)
    pixel_counts = np.asarray(pixel_counts)
    cluster_ids = np.asarray(cluster_ids)
    if means.ndim != 2:
        raise PayloadSerializationError(f"{where}: means must be 2-D, got shape {means.shape}.")
    _check_integer_ids(cluster_ids, where)
    n = cluster_ids.size
    if means.shape[0] != n or pixel_counts.size != n:
        raise PayloadSerializationError(
            f"{where}: means/pixel_counts/cluster_ids lengths disagree "
            f"({means.shape[0]}, {pixel_counts.size}, {n})."
        )
    if not np.issubdtype(pixel_counts.dtype, np.integer):
        raise PayloadSerializationError(
            f"{where}: pixel_counts must be an integer array ({pixel_counts.dtype})."
        )
    if np.any(pixel_counts < 0):
        raise PayloadSerializationError(f"{where}: pixel_counts must be >= 0.")
    for name, arr in (("heterogeneity", heterogeneity), ("total_counts", total_counts)):
        if arr is not None and np.asarray(arr).size != n:
            raise PayloadSerializationError(
                f"{where}: {name} length {np.asarray(arr).size} != n_clusters {n}."
            )
    if total_counts is not None:
        tc = np.asarray(total_counts)
        if np.any(~np.isfinite(tc) & (pixel_counts > 0)):
            raise PayloadSerializationError(
                f"{where}: total_counts is non-finite for a non-empty cluster."
            )


def _load_sidecar(path: Path, expected_kind: str) -> dict:
    """Load a sidecar, enforcing schema version and payload kind."""
    if not path.exists():
        raise PayloadSerializationError(f"{path} does not exist.")
    try:
        sidecar = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PayloadSerializationError(f"{path.name}: malformed JSON ({exc}).") from exc
    if not isinstance(sidecar, dict):
        raise PayloadSerializationError(f"{path.name}: sidecar is not a JSON object.")
    version = sidecar.get("schema_version")
    if version != SCHEMA_VERSION:
        raise PayloadSerializationError(
            f"{path.name}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION})."
        )
    kind = sidecar.get("kind")
    if kind != expected_kind:
        raise PayloadSerializationError(
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


def _prov_from_dict(d, where: str = "clustering"):
    if d is None:
        return None
    if not isinstance(d, dict):
        raise PayloadSerializationError(f"{where}.provenance: must be an object or null.")
    for field_name in ("tool", "backend"):
        if not isinstance(d.get(field_name), str):
            raise PayloadSerializationError(
                f"{where}.provenance.{field_name}: missing or not a string."
            )
    params = d.get("params", {})
    if not isinstance(params, dict):
        raise PayloadSerializationError(f"{where}.provenance.params: must be an object.")
    return AnalysisProvenance(
        tool=d["tool"],
        backend=d["backend"],
        tool_version=d.get("tool_version"),
        params=params,
    )


def _diags_to_list(diagnostics):
    return [
        {"severity": d.severity, "code": d.code, "message": d.message,
         "context": dict(d.context)}
        for d in diagnostics
    ]


def _diags_from_list(items, where: str = "clustering"):
    if not isinstance(items, list):
        raise PayloadSerializationError(f"{where}.diagnostics: must be a list.")
    out = []
    for i, d in enumerate(items):
        if not isinstance(d, dict):
            raise PayloadSerializationError(f"{where}.diagnostics[{i}]: not an object.")
        for field_name in ("severity", "code", "message"):
            if not isinstance(d.get(field_name), str):
                raise PayloadSerializationError(
                    f"{where}.diagnostics[{i}].{field_name}: missing or not a string."
                )
        context = d.get("context", {})
        if not isinstance(context, dict):
            raise PayloadSerializationError(f"{where}.diagnostics[{i}].context: must be an object.")
        out.append(Diagnostic(severity=d["severity"], code=d["code"],
                              message=d["message"], context=context))
    return out


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

    # validate-before-write: never persist a malformed payload
    where = f"{stem}_clustering (write)"
    _check_integer_ids(np.asarray(result.cluster_ids), where)

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


def _require_npz(npz, key: str, where: str):
    if key not in npz.files:
        raise PayloadSerializationError(f"{where}: missing array {key!r}.")
    return npz[key]


def _require_int_field(sidecar: dict, key: str, where: str) -> int:
    value = sidecar.get(key)
    if not _is_int(value):
        raise PayloadSerializationError(f"{where}: {key!r} must be an integer ({value!r}).")
    return value


def read_clustering(directory, stem: str) -> ClusteringResult:
    """Read and validate a ClusteringResult written by :func:`write_clustering`."""
    directory = Path(directory)
    where = f"{stem}_clustering"
    npz = np.load(directory / f"{stem}_clustering.npz")
    sidecar = _load_sidecar(directory / f"{stem}_clustering.json", "clustering")
    labels = _require_npz(npz, "labels", where)
    label_map = _require_npz(npz, "label_map", where)
    cluster_ids = _require_npz(npz, "cluster_ids", where)
    _check_integer_ids(cluster_ids, where)
    n_clusters = _require_int_field(sidecar, "n_clusters", where)
    # advertised shape invariant: the sidecar's label_map_shape must match
    if "label_map_shape" in sidecar and list(label_map.shape) != list(sidecar["label_map_shape"]):
        raise PayloadSerializationError(
            f"{where}: label_map shape {list(label_map.shape)} != advertised "
            f"{sidecar['label_map_shape']}."
        )
    return ClusteringResult(
        labels=labels,
        label_map=label_map,
        cluster_ids=cluster_ids,
        n_clusters=n_clusters,
        provenance=_prov_from_dict(sidecar.get("provenance"), where),
        diagnostics=_diags_from_list(sidecar.get("diagnostics", []), where),
    )


def write_cluster_means(means: ClusterMeanSpectra, directory, stem: str,
                        *, overwrite: bool = False) -> tuple[Path, Path]:
    """Write ``means`` to ``<stem>_cluster_means.{npz,json}``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    npz_path = directory / f"{stem}_cluster_means.npz"
    json_path = directory / f"{stem}_cluster_means.json"
    _guard((npz_path, json_path), overwrite)

    # validate-before-write: never persist a malformed payload
    _check_cluster_means_arrays(
        means.means, means.pixel_counts, means.cluster_ids,
        means.heterogeneity, means.total_counts, f"{stem}_cluster_means (write)",
    )

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
    """Read and validate a ClusterMeanSpectra written by :func:`write_cluster_means`."""
    directory = Path(directory)
    where = f"{stem}_cluster_means"
    npz = np.load(directory / f"{stem}_cluster_means.npz")
    sidecar = _load_sidecar(directory / f"{stem}_cluster_means.json", "cluster_means")

    means = _require_npz(npz, "means", where)
    pixel_counts = _require_npz(npz, "pixel_counts", where)
    cluster_ids = _require_npz(npz, "cluster_ids", where)
    n_clusters = _require_int_field(sidecar, "n_clusters", where)
    heterogeneity = npz["heterogeneity"] if "heterogeneity" in npz.files else None
    total_counts = npz["total_counts"] if "total_counts" in npz.files else None

    _check_cluster_means_arrays(means, pixel_counts, cluster_ids,
                                heterogeneity, total_counts, where)
    # advertised shape invariant: the sidecar's means_shape must match
    if "means_shape" in sidecar and list(means.shape) != list(sidecar["means_shape"]):
        raise PayloadSerializationError(
            f"{where}: means shape {list(means.shape)} != advertised {sidecar['means_shape']}."
        )
    # the sidecar's has_* flags must match the arrays actually present
    if sidecar.get("has_heterogeneity") is True and heterogeneity is None:
        raise PayloadSerializationError(f"{where}: sidecar advertises heterogeneity but it is absent.")
    if sidecar.get("has_total_counts") is True and total_counts is None:
        raise PayloadSerializationError(f"{where}: sidecar advertises total_counts but it is absent.")

    return ClusterMeanSpectra(
        means=means,
        pixel_counts=pixel_counts,
        cluster_ids=cluster_ids,
        n_clusters=n_clusters,
        heterogeneity=heterogeneity,
        total_counts=total_counts,
        provenance=_prov_from_dict(sidecar.get("provenance"), where),
        diagnostics=_diags_from_list(sidecar.get("diagnostics", []), where),
    )


__all__ = [
    "SCHEMA_VERSION",
    "read_cluster_means",
    "read_clustering",
    "write_cluster_means",
    "write_clustering",
]
