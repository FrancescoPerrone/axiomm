"""Versioned JSON file adapters for quant payloads.

Internal adapter (v1), not a stable public contract. Scalars only, so
JSON (no .npz). Refuses silent overwrite. Reads and writes are strict:
every document carries ``schema_version`` and ``kind``, both enforced on
read; non-finite numbers (NaN / Infinity) are rejected in both directions
so a corrupted or hand-edited file cannot smuggle a non-finite value into
a reconstructed payload (P10).
"""

from __future__ import annotations

import json
from pathlib import Path

from axiomm.analysis.errors import OutputExistsError, PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

SCHEMA_VERSION = 1


def _reject_nonfinite(token: str):
    raise PayloadValidationError(f"non-finite JSON value {token!r} is not allowed.")


def _load_doc(path: Path, expected_kind: str) -> dict:
    """Load a quant JSON doc, enforcing finiteness, schema version and kind."""
    if not path.exists():
        raise PayloadValidationError(f"{path} does not exist.")
    try:
        doc = json.loads(path.read_text(), parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        raise PayloadValidationError(f"{path.name}: malformed JSON ({exc}).") from exc
    if not isinstance(doc, dict):
        raise PayloadValidationError(f"{path.name}: document is not a JSON object.")
    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise PayloadValidationError(
            f"{path.name}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION})."
        )
    kind = doc.get("kind")
    if kind != expected_kind:
        raise PayloadValidationError(
            f"{path.name}: expected payload kind {expected_kind!r}, got {kind!r}."
        )
    return doc


def _dump(doc: dict, path: Path) -> None:
    path.write_text(json.dumps(doc, indent=2, allow_nan=False))


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


def _guard(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")


def write_kfactors(ks, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Write ``ks`` to ``<stem>_kfactors.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_kfactors.json"
    _guard(path, overwrite)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "kfactors",
        "k_factors": dict(ks.k_factors),
        "sensitivities": dict(ks.sensitivities),
        "reference_element": ks.reference_element,
        "excitation_kev": ks.excitation_kev,
        "provenance": _prov_to_dict(ks.provenance),
        "diagnostics": _diags_to_list(ks.diagnostics),
    }
    _dump(doc, path)
    return path


def read_kfactors(directory, stem: str):
    """Read a KFactorSet written by :func:`write_kfactors`."""
    from axiomm.analysis.quant.models import KFactorSet
    path = Path(directory) / f"{stem}_kfactors.json"
    doc = _load_doc(path, "kfactors")
    return KFactorSet(
        k_factors=doc["k_factors"],
        sensitivities=doc["sensitivities"],
        reference_element=doc["reference_element"],
        excitation_kev=doc["excitation_kev"],
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=_diags_from_list(doc["diagnostics"]),
    )


def write_quant(qr, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Write a QuantResult to ``<stem>_quant.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_quant.json"
    _guard(path, overwrite)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "quant",
        "net_intensities": dict(qr.net_intensities),
        "wt_percent_element": dict(qr.wt_percent_element),
        "wt_percent_oxide": dict(qr.wt_percent_oxide),
        "reference_element": qr.reference_element,
        "gross_intensities": dict(qr.gross_intensities),
        "background_per_channel": dict(qr.background_per_channel),
        "window_channels": dict(qr.window_channels),
        "cluster_id": qr.cluster_id,
        "provenance": _prov_to_dict(qr.provenance),
        "diagnostics": _diags_to_list(qr.diagnostics),
    }
    _dump(doc, path)
    return path


def read_quant(directory, stem: str):
    """Read a QuantResult written by :func:`write_quant`."""
    from axiomm.analysis.quant.models import QuantResult
    path = Path(directory) / f"{stem}_quant.json"
    doc = _load_doc(path, "quant")
    return QuantResult(
        net_intensities=doc["net_intensities"],
        wt_percent_element=doc["wt_percent_element"],
        wt_percent_oxide=doc["wt_percent_oxide"],
        reference_element=doc["reference_element"],
        gross_intensities=doc.get("gross_intensities", {}),
        background_per_channel=doc.get("background_per_channel", {}),
        window_channels=doc.get("window_channels", {}),
        cluster_id=doc.get("cluster_id"),
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=_diags_from_list(doc["diagnostics"]),
    )


def write_reliability(report, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Write a ReliabilityReport to ``<stem>_reliability.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_reliability.json"
    _guard(path, overwrite)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "kind": "reliability",
        "cluster_status": report.cluster_status,
        "element_status": dict(report.element_status),
        "reasons": list(report.reasons),
        "cluster_id": report.cluster_id,
        "provenance": _prov_to_dict(report.provenance),
        "diagnostics": _diags_to_list(report.diagnostics),
    }
    _dump(doc, path)
    return path


def read_reliability(directory, stem: str):
    """Read a ReliabilityReport written by :func:`write_reliability`."""
    from axiomm.analysis.quant.reliability import ReliabilityReport
    path = Path(directory) / f"{stem}_reliability.json"
    doc = _load_doc(path, "reliability")
    return ReliabilityReport(
        cluster_status=doc["cluster_status"],
        element_status=doc["element_status"],
        reasons=tuple(doc["reasons"]),
        cluster_id=doc.get("cluster_id"),
        provenance=_prov_from_dict(doc["provenance"]),
        diagnostics=_diags_from_list(doc["diagnostics"]),
    )


__all__ = ["SCHEMA_VERSION", "read_kfactors", "read_quant", "read_reliability",
           "write_kfactors", "write_quant", "write_reliability"]
