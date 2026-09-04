"""Versioned, validated JSON adapter for mineral-match results (S3d).

Strict like the other analysis adapters: every document carries
``schema_version`` and ``kind``, both enforced on read; non-finite numbers are
rejected in both directions; the document is fully validated (candidate score
and coverage ranges, outcome vocabulary, field types) before a payload is
reconstructed, and writes validate first so a malformed result is never
persisted.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from axiomm.analysis.errors import OutputExistsError, PayloadSerializationError
from axiomm.analysis.mineralogy.match.models import (
    CANDIDATE_OUTCOMES,
    MineralCandidate,
    MineralMatchResult,
)
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

SCHEMA_VERSION = 1


def _reject_nonfinite(token: str):
    raise PayloadSerializationError(f"non-finite JSON value {token!r} is not allowed.")


def _load_doc(path: Path) -> dict:
    if not path.exists():
        raise PayloadSerializationError(f"{path} does not exist.")
    try:
        doc = json.loads(path.read_text(), parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        raise PayloadSerializationError(f"{path.name}: malformed JSON ({exc}).") from exc
    if not isinstance(doc, dict):
        raise PayloadSerializationError(f"{path.name}: document is not a JSON object.")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise PayloadSerializationError(
            f"{path.name}: unsupported schema_version {doc.get('schema_version')!r} "
            f"(expected {SCHEMA_VERSION})."
        )
    if doc.get("kind") != "match":
        raise PayloadSerializationError(
            f"{path.name}: expected payload kind 'match', got {doc.get('kind')!r}."
        )
    return doc


def _in_unit(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) \
        and math.isfinite(float(v)) and 0.0 <= float(v) <= 1.0


def _validate_candidate(d: dict, where: str) -> None:
    if not isinstance(d, dict):
        raise PayloadSerializationError(f"{where}: candidate is not an object.")
    for key in ("name", "family", "basis"):
        if not isinstance(d.get(key), str):
            raise PayloadSerializationError(f"{where}.{key}: missing or not a string.")
    if not _in_unit(d.get("score")):
        raise PayloadSerializationError(f"{where}.score: must be a number in [0, 1] ({d.get('score')!r}).")
    for key in ("dimension_coverage", "composition_coverage"):
        if not _in_unit(d.get(key)):
            raise PayloadSerializationError(f"{where}.{key}: must be a number in [0, 1] ({d.get(key)!r}).")
    if d.get("outcome") not in CANDIDATE_OUTCOMES:
        raise PayloadSerializationError(
            f"{where}.outcome: {d.get('outcome')!r} not in {sorted(CANDIDATE_OUTCOMES)}."
        )
    n = d.get("n_informative_dims")
    if not (isinstance(n, int) and not isinstance(n, bool) and n >= 0):
        raise PayloadSerializationError(f"{where}.n_informative_dims: non-negative integer ({n!r}).")
    for key in ("elements_used", "elements_censored", "elements_unavailable"):
        seq = d.get(key)
        if not (isinstance(seq, list) and all(isinstance(s, str) for s in seq)):
            raise PayloadSerializationError(f"{where}.{key}: must be a list of strings.")


def _validate_doc(doc: dict, where: str) -> None:
    if not (doc.get("cluster_id") is None
            or (isinstance(doc.get("cluster_id"), int) and not isinstance(doc.get("cluster_id"), bool))):
        raise PayloadSerializationError(f"{where}.cluster_id: must be an integer or null.")
    if not isinstance(doc.get("reliability_gated"), bool):
        raise PayloadSerializationError(f"{where}.reliability_gated: must be a boolean.")
    for key in ("library_name", "library_version"):
        if not isinstance(doc.get(key), str):
            raise PayloadSerializationError(f"{where}.{key}: missing or not a string.")
    ir = doc.get("input_reliability")
    if not (ir is None or isinstance(ir, str)):
        raise PayloadSerializationError(f"{where}.input_reliability: must be a string or null.")
    for key in ("candidates", "insufficient"):
        seq = doc.get(key, [])
        if not isinstance(seq, list):
            raise PayloadSerializationError(f"{where}.{key}: must be a list.")
        for i, cand in enumerate(seq):
            _validate_candidate(cand, f"{where}.{key}[{i}]")


def _cand_to_dict(c: MineralCandidate) -> dict:
    return {
        "name": c.name, "family": c.family, "score": c.score, "outcome": c.outcome,
        "elements_used": list(c.elements_used), "elements_censored": list(c.elements_censored),
        "elements_unavailable": list(c.elements_unavailable),
        "n_informative_dims": c.n_informative_dims,
        "dimension_coverage": c.dimension_coverage,
        "composition_coverage": c.composition_coverage, "basis": c.basis,
    }


def _cand_from_dict(d: dict) -> MineralCandidate:
    return MineralCandidate(
        name=d["name"], family=d["family"], score=d["score"], outcome=d["outcome"],
        elements_used=tuple(d["elements_used"]), elements_censored=tuple(d["elements_censored"]),
        elements_unavailable=tuple(d["elements_unavailable"]),
        n_informative_dims=d["n_informative_dims"],
        dimension_coverage=d["dimension_coverage"],
        composition_coverage=d["composition_coverage"], basis=d["basis"],
    )


def _prov_to_dict(p):
    if p is None:
        return None
    return {"tool": p.tool, "backend": p.backend, "tool_version": p.tool_version,
            "params": dict(p.params)}


def _prov_from_dict(d):
    if d is None:
        return None
    return AnalysisProvenance(tool=d["tool"], backend=d["backend"],
                              tool_version=d.get("tool_version"), params=d.get("params", {}))


def _diags_to_list(ds):
    return [{"severity": d.severity, "code": d.code, "message": d.message,
             "context": dict(d.context)} for d in ds]


def _diags_from_list(items):
    return [Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                       context=d.get("context", {})) for d in items]


def write_match(result: MineralMatchResult, directory, stem: str,
                *, overwrite: bool = False) -> Path:
    """Validate then write a MineralMatchResult to ``<stem>_match.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_match.json"
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
    doc = {
        "schema_version": SCHEMA_VERSION, "kind": "match",
        "cluster_id": result.cluster_id,
        "input_reliability": result.input_reliability,
        "reliability_gated": result.reliability_gated,
        "library_name": result.library_name, "library_version": result.library_version,
        "candidates": [_cand_to_dict(c) for c in result.candidates],
        "insufficient": [_cand_to_dict(c) for c in result.insufficient],
        "provenance": _prov_to_dict(result.provenance),
        "diagnostics": _diags_to_list(result.diagnostics),
    }
    _validate_doc(doc, f"{stem}_match (write)")
    path.write_text(json.dumps(doc, indent=2, allow_nan=False))
    return path


def read_match(directory, stem: str) -> MineralMatchResult:
    """Read and validate a MineralMatchResult written by :func:`write_match`."""
    path = Path(directory) / f"{stem}_match.json"
    doc = _load_doc(path)
    _validate_doc(doc, path.name)
    return MineralMatchResult(
        cluster_id=doc["cluster_id"],
        candidates=tuple(_cand_from_dict(c) for c in doc["candidates"]),
        insufficient=tuple(_cand_from_dict(c) for c in doc.get("insufficient", [])),
        input_reliability=doc["input_reliability"],
        reliability_gated=doc["reliability_gated"],
        library_name=doc["library_name"], library_version=doc["library_version"],
        provenance=_prov_from_dict(doc.get("provenance")),
        diagnostics=_diags_from_list(doc.get("diagnostics", [])),
    )


__all__ = ["SCHEMA_VERSION", "read_match", "write_match"]
