"""Versioned JSON file adapter for KFactorSet.

Internal adapter (v1), not a stable public contract. Scalars only, so
JSON (no .npz). Refuses silent overwrite.
"""

from __future__ import annotations

import json
from pathlib import Path

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.models import KFactorSet

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


def write_kfactors(ks: KFactorSet, directory, stem: str,
                   *, overwrite: bool = False) -> Path:
    """Write ``ks`` to ``<stem>_kfactors.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_kfactors.json"
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "k_factors": dict(ks.k_factors),
        "sensitivities": dict(ks.sensitivities),
        "reference_element": ks.reference_element,
        "excitation_kev": ks.excitation_kev,
        "provenance": _prov_to_dict(ks.provenance),
        "diagnostics": [
            {"severity": d.severity, "code": d.code, "message": d.message,
             "context": dict(d.context)}
            for d in ks.diagnostics
        ],
    }
    path.write_text(json.dumps(doc, indent=2))
    return path


def read_kfactors(directory, stem: str) -> KFactorSet:
    """Read a KFactorSet written by :func:`write_kfactors`."""
    path = Path(directory) / f"{stem}_kfactors.json"
    doc = json.loads(path.read_text())
    diagnostics = [
        Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                   context=d["context"])
        for d in doc["diagnostics"]
    ]
    return KFactorSet(
        k_factors=doc["k_factors"],
        sensitivities=doc["sensitivities"],
        reference_element=doc["reference_element"],
        excitation_kev=doc["excitation_kev"],
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=diagnostics,
    )


def write_quant(qr, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Write a QuantResult to ``<stem>_quant.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_quant.json"
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "net_intensities": dict(qr.net_intensities),
        "wt_percent_element": dict(qr.wt_percent_element),
        "wt_percent_oxide": dict(qr.wt_percent_oxide),
        "reference_element": qr.reference_element,
        "provenance": _prov_to_dict(qr.provenance),
        "diagnostics": [
            {"severity": d.severity, "code": d.code, "message": d.message,
             "context": dict(d.context)}
            for d in qr.diagnostics
        ],
    }
    path.write_text(json.dumps(doc, indent=2))
    return path


def read_quant(directory, stem: str):
    """Read a QuantResult written by :func:`write_quant`."""
    from axiomm.analysis.quant.models import QuantResult
    path = Path(directory) / f"{stem}_quant.json"
    doc = json.loads(path.read_text())
    diagnostics = [
        Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                   context=d["context"])
        for d in doc["diagnostics"]
    ]
    return QuantResult(
        net_intensities=doc["net_intensities"],
        wt_percent_element=doc["wt_percent_element"],
        wt_percent_oxide=doc["wt_percent_oxide"],
        reference_element=doc["reference_element"],
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=diagnostics,
    )


def write_reliability(report, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Write a ReliabilityReport to ``<stem>_reliability.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_reliability.json"
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "cluster_status": report.cluster_status,
        "element_status": dict(report.element_status),
        "reasons": list(report.reasons),
        "provenance": _prov_to_dict(report.provenance),
        "diagnostics": [
            {"severity": d.severity, "code": d.code, "message": d.message,
             "context": dict(d.context)}
            for d in report.diagnostics
        ],
    }
    path.write_text(json.dumps(doc, indent=2))
    return path


def read_reliability(directory, stem: str):
    """Read a ReliabilityReport written by :func:`write_reliability`."""
    from axiomm.analysis.quant.reliability import ReliabilityReport
    path = Path(directory) / f"{stem}_reliability.json"
    doc = json.loads(path.read_text())
    diagnostics = [
        Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                   context=d["context"])
        for d in doc["diagnostics"]
    ]
    return ReliabilityReport(
        cluster_status=doc["cluster_status"],
        element_status=doc["element_status"],
        reasons=tuple(doc["reasons"]),
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=diagnostics,
    )


__all__ = ["SCHEMA_VERSION", "read_kfactors", "read_quant", "read_reliability",
           "write_kfactors", "write_quant", "write_reliability"]
