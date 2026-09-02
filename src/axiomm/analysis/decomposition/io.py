"""File adapters for DecompositionResult — the standalone/resume seam.

Writes numerics to ``<stem>_decomposition.npz`` and a human-readable
``<stem>_decomposition.json`` sidecar (params, provenance, diagnostics).
Refuses to silently overwrite (scientific-data safety).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.decomposition.models import DecompositionResult


def _paths(directory: Path, stem: str) -> tuple[Path, Path]:
    directory = Path(directory)
    return (
        directory / f"{stem}_decomposition.npz",
        directory / f"{stem}_decomposition.json",
    )


def write_decomposition(
    result: DecompositionResult,
    directory,
    stem: str,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write ``result`` to ``<stem>_decomposition.{npz,json}`` in ``directory``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    npz_path, json_path = _paths(directory, stem)

    if not overwrite:
        for path in (npz_path, json_path):
            if path.exists():
                raise OutputExistsError(
                    f"{path} already exists; pass overwrite=True to replace it."
                )

    np.savez(
        npz_path,
        factors=result.factors,
        loadings=result.loadings,
        explained_variance_ratio=result.explained_variance_ratio,
        nav_shape=np.asarray(result.nav_shape),
    )

    prov = result.provenance
    sidecar = {
        "n_components": result.n_components,
        "nav_shape": list(result.nav_shape),
        "provenance": None
        if prov is None
        else {
            "tool": prov.tool,
            "backend": prov.backend,
            "tool_version": prov.tool_version,
            "params": dict(prov.params),
        },
        "diagnostics": [
            {
                "severity": d.severity,
                "code": d.code,
                "message": d.message,
                "context": dict(d.context),
            }
            for d in result.diagnostics
        ],
    }
    json_path.write_text(json.dumps(sidecar, indent=2))
    return npz_path, json_path


def read_decomposition(directory, stem: str) -> DecompositionResult:
    """Read a DecompositionResult previously written by :func:`write_decomposition`."""
    npz_path, json_path = _paths(Path(directory), stem)
    npz = np.load(npz_path)
    sidecar = json.loads(json_path.read_text())

    prov = sidecar.get("provenance")
    provenance = (
        None
        if prov is None
        else AnalysisProvenance(
            tool=prov["tool"],
            backend=prov["backend"],
            tool_version=prov["tool_version"],
            params=prov["params"],
        )
    )
    diagnostics = [
        Diagnostic(
            severity=d["severity"],
            code=d["code"],
            message=d["message"],
            context=d["context"],
        )
        for d in sidecar["diagnostics"]
    ]
    return DecompositionResult(
        factors=npz["factors"],
        loadings=npz["loadings"],
        explained_variance_ratio=npz["explained_variance_ratio"],
        nav_shape=tuple(int(x) for x in npz["nav_shape"]),
        n_components=int(sidecar["n_components"]),
        provenance=provenance,
        diagnostics=diagnostics,
    )


__all__ = ["read_decomposition", "write_decomposition"]
