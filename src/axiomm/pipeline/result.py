"""The one bundle a :class:`Pipeline` run hands back.

Carries every stage's output plus aggregated provenance and diagnostics, with
plainly-named accessors (``clusters``, ``phase_map``, ``minerals``, ``summary``)
and a ``save`` that reuses the existing strict, versioned adapters. ``repr``
prints a short, self-explaining account.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from axiomm.analysis.clustering.io import read_cluster_means, write_cluster_means
from axiomm.analysis.mineralogy.match.io import read_match, write_match
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.quant.io import (
    read_quant,
    read_reliability,
    write_quant,
    write_reliability,
)

SCHEMA_VERSION = 1
UNRESOLVED = "unresolved"


@dataclass
class PipelineResult:
    """Everything one pipeline run produced."""

    label_map: np.ndarray                        # per-pixel cluster id (nav shape)
    cluster_means: Any                           # ClusterMeanSpectra
    clustering: Any = None                        # ClusteringResult (raw)
    decomposition: Any = None                     # DecompositionResult (raw)
    payload: Any = None                           # source AxiommSignalPayload
    peaks: tuple | None = None
    quantification: tuple | None = None           # per-cluster QuantResult
    reliability: tuple | None = None              # per-cluster ReliabilityReport
    minerals: tuple | None = None                 # per-cluster MineralMatchResult
    phase_map: np.ndarray | None = None           # per-pixel mineral name / UNRESOLVED
    config: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    # --- plain-English views ------------------------------------------------
    @property
    def clusters(self) -> list[dict]:
        """A plain list of 'what it found', one row per cluster."""
        ids = [int(c) for c in np.asarray(self.cluster_means.cluster_ids)]
        pix = [int(p) for p in np.asarray(self.cluster_means.pixel_counts)]
        rows = []
        rel_by = {int(r.cluster_id): r for r in (self.reliability or ()) if r.cluster_id is not None}
        for cid, n in zip(ids, pix, strict=True):
            best = self.best_match(cid)
            rows.append({
                "cluster_id": cid, "pixels": n,
                "best_match": best.name if best else UNRESOLVED,
                "score": round(best.score, 3) if best else None,
                "reliability": rel_by[cid].cluster_status if cid in rel_by else None,
            })
        return rows

    def best_match(self, cluster_id: int):
        """Top mineral candidate for a cluster, or ``None`` (unresolved / not run)."""
        for m in (self.minerals or ()):
            if m.cluster_id == cluster_id:
                return m.best()
        return None

    def summary(self) -> str:
        lines = [f"AXIOMM pipeline result — {len(self.clusters)} clusters, "
                 f"map {tuple(int(d) for d in np.asarray(self.label_map).shape)}"]
        if self.minerals is None:
            lines.append("  minerals: not run (set beam_energy_kev + a reference to enable)")
        for row in self.clusters:
            m = f"{row['best_match']}" + (f" ({row['score']})" if row['score'] is not None else "")
            lines.append(f"  cluster {row['cluster_id']:>2}: {row['pixels']:>7} px -> {m}"
                         + (f"  [{row['reliability']}]" if row['reliability'] else ""))
        if self.diagnostics:
            lines.append(f"  diagnostics: {len(self.diagnostics)} "
                         f"({', '.join(sorted({d.code for d in self.diagnostics}))})")
        return "\n".join(lines)

    def __repr__(self) -> str:
        run = "clusters+minerals" if self.minerals is not None else "clusters only"
        return f"<PipelineResult {run}, {len(self.clusters)} clusters>"

    # --- persistence --------------------------------------------------------
    def save(self, directory, *, overwrite: bool = False) -> Path:
        """Write a self-describing directory (manifest + arrays + stage payloads)."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        write_cluster_means(self.cluster_means, directory, "pipeline", overwrite=overwrite)
        np.save(directory / "label_map.npy", np.asarray(self.label_map))
        cluster_ids = [int(c) for c in np.asarray(self.cluster_means.cluster_ids)]
        for i, cid in enumerate(cluster_ids):
            if self.quantification is not None:
                write_quant(self.quantification[i], directory, f"cluster{cid}", overwrite=overwrite)
            if self.reliability is not None:
                write_reliability(self.reliability[i], directory, f"cluster{cid}", overwrite=overwrite)
            if self.minerals is not None:
                write_match(self.minerals[i], directory, f"cluster{cid}", overwrite=overwrite)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "config": self.config,
            "provenance": self.provenance,
            "cluster_ids": cluster_ids,
            "clusters": self.clusters,
            "has_minerals": self.minerals is not None,
            "phase_map": (np.asarray(self.phase_map).tolist() if self.phase_map is not None else None),
            "diagnostics": [{"severity": d.severity, "code": d.code, "message": d.message}
                            for d in self.diagnostics],
        }
        (directory / "pipeline.json").write_text(json.dumps(manifest, indent=2, allow_nan=False))
        return directory / "pipeline.json"


def load_result(directory) -> PipelineResult:
    """Reconstruct a :class:`PipelineResult` written by :meth:`PipelineResult.save`."""
    directory = Path(directory)
    manifest = json.loads((directory / "pipeline.json").read_text())
    cluster_means = read_cluster_means(directory, "pipeline")
    label_map = np.load(directory / "label_map.npy", allow_pickle=False)
    cluster_ids = manifest["cluster_ids"]
    quant = rel = mins = None
    if manifest.get("has_minerals"):
        quant = tuple(read_quant(directory, f"cluster{cid}") for cid in cluster_ids)
        rel = tuple(read_reliability(directory, f"cluster{cid}") for cid in cluster_ids)
        mins = tuple(read_match(directory, f"cluster{cid}") for cid in cluster_ids)
    phase_map = (np.array(manifest["phase_map"], dtype=object)
                 if manifest.get("phase_map") is not None else None)
    return PipelineResult(
        label_map=label_map, cluster_means=cluster_means,
        quantification=quant, reliability=rel, minerals=mins, phase_map=phase_map,
        config=manifest.get("config", {}), provenance=manifest.get("provenance", {}),
        diagnostics=[Diagnostic(d["severity"], d["code"], d["message"])
                     for d in manifest.get("diagnostics", [])],
    )


__all__ = ["SCHEMA_VERSION", "UNRESOLVED", "PipelineResult", "load_result"]
