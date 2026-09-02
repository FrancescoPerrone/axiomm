"""Versioned JSON file adapter for PeakMeasurementSet.

Internal adapter (v1), not a stable public contract. Peaks are small
per-line scalars, so JSON alone (no .npz). Refuses silent overwrite.
"""

from __future__ import annotations

import json
from pathlib import Path

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet

SCHEMA_VERSION = 1


def _prov_to_dict(prov):
    if prov is None:
        return None
    return {"tool": prov.tool, "backend": prov.backend,
            "tool_version": prov.tool_version, "params": dict(prov.params)}


def _prov_from_dict(d):
    if d is None:
        return None
    return AnalysisProvenance(tool=d["tool"], backend=d["backend"],
                              tool_version=d["tool_version"], params=d["params"])


def write_peaks(pset: PeakMeasurementSet, directory, stem: str,
                *, overwrite: bool = False) -> Path:
    """Write ``pset`` to ``<stem>_peaks.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_peaks.json"
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "measurements": [
            {"label": m.label, "center_kev": m.center_kev, "net": m.net,
             "gross": m.gross, "background": m.background,
             "n_channels": m.n_channels, "in_range": m.in_range}
            for m in pset.measurements
        ],
        "provenance": _prov_to_dict(pset.provenance),
        "diagnostics": [
            {"severity": d.severity, "code": d.code, "message": d.message,
             "context": dict(d.context)}
            for d in pset.diagnostics
        ],
    }
    path.write_text(json.dumps(doc, indent=2))
    return path


def read_peaks(directory, stem: str) -> PeakMeasurementSet:
    """Read a PeakMeasurementSet written by :func:`write_peaks`."""
    path = Path(directory) / f"{stem}_peaks.json"
    doc = json.loads(path.read_text())
    measurements = tuple(
        PeakMeasurement(
            label=m["label"], center_kev=m["center_kev"], net=m["net"],
            gross=m["gross"], background=m["background"],
            n_channels=m["n_channels"], in_range=m["in_range"],
        )
        for m in doc["measurements"]
    )
    diagnostics = [
        Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                   context=d["context"])
        for d in doc["diagnostics"]
    ]
    return PeakMeasurementSet(
        measurements=measurements,
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=diagnostics,
    )


__all__ = ["SCHEMA_VERSION", "read_peaks", "write_peaks"]
