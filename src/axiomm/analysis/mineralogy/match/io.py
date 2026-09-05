"""Versioned, deeply-validated JSON adapter for mineral-match results (S3d).

Every document carries ``schema_version`` and ``kind``, both enforced on read;
non-finite numbers are rejected in both directions; and the document is fully
validated before a payload is reconstructed — schema/kind/version, candidate
ordering and name uniqueness, outcome vocabulary, ``n_informative_dims``
consistency with ``elements_used``, finite scores and coverage within bounds,
raw-vs-rank score semantics, provenance and diagnostics structure, and
consistency between ``library_name`` and the provenance. Any malformed field
raises :class:`PayloadSerializationError` with a field path — never a raw
``KeyError`` / ``TypeError`` / ``ValueError``. Writes validate first, so a
malformed result is never persisted.
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
KIND = "match"


def _reject_nonfinite(token: str):
    raise PayloadSerializationError(f"non-finite JSON value {token!r} is not allowed.")


def _req(doc: dict, key: str, types, where: str):
    if not isinstance(doc, dict):
        raise PayloadSerializationError(f"{where}: expected an object.")
    if key not in doc:
        raise PayloadSerializationError(f"{where}.{key}: missing required field.")
    value = doc[key]
    if not isinstance(value, types):
        raise PayloadSerializationError(
            f"{where}.{key}: wrong type {type(value).__name__}."
        )
    return value


def _finite(value, where: str) -> float:
    if not (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))):
        raise PayloadSerializationError(f"{where}: must be a finite number ({value!r}).")
    return float(value)


def _unit(value, where: str) -> float:
    v = _finite(value, where)
    if v < -1e-9 or v > 1 + 1e-9:
        raise PayloadSerializationError(f"{where}: must lie in [0, 1] ({value!r}).")
    return v


def _str_list(value, where: str) -> list[str]:
    if not (isinstance(value, list) and all(isinstance(s, str) for s in value)):
        raise PayloadSerializationError(f"{where}: must be a list of strings.")
    return value


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
            f"(expected {SCHEMA_VERSION}); no migration path."
        )
    if doc.get("kind") != KIND:
        raise PayloadSerializationError(
            f"{path.name}: expected payload kind {KIND!r}, got {doc.get('kind')!r}."
        )
    return doc


# --------------------------------------------------------------------------
# provenance / diagnostics — validated, never raw KeyError
# --------------------------------------------------------------------------

def _prov_to_dict(p):
    if p is None:
        return None
    return {"tool": p.tool, "backend": p.backend, "tool_version": p.tool_version,
            "params": dict(p.params)}


def _prov_from_dict(d, where: str):
    if d is None:
        return None
    if not isinstance(d, dict):
        raise PayloadSerializationError(f"{where}: provenance must be an object or null.")
    tool = _req(d, "tool", str, where)
    backend = _req(d, "backend", str, where)
    params = d.get("params", {})
    if not isinstance(params, dict):
        raise PayloadSerializationError(f"{where}.params: must be an object.")
    return AnalysisProvenance(tool=tool, backend=backend,
                              tool_version=d.get("tool_version"), params=params)


def _diags_to_list(ds):
    return [{"severity": d.severity, "code": d.code, "message": d.message,
             "context": dict(d.context)} for d in ds]


def _diags_from_list(items, where: str):
    if not isinstance(items, list):
        raise PayloadSerializationError(f"{where}: diagnostics must be a list.")
    out = []
    for i, d in enumerate(items):
        w = f"{where}[{i}]"
        out.append(Diagnostic(
            severity=_req(d, "severity", str, w), code=_req(d, "code", str, w),
            message=_req(d, "message", str, w),
            context=d.get("context", {}) if isinstance(d.get("context", {}), dict)
            else _raise_ctx(w)))
    return out


def _raise_ctx(where: str):
    raise PayloadSerializationError(f"{where}.context: must be an object.")


# --------------------------------------------------------------------------
# candidates
# --------------------------------------------------------------------------

def _cand_to_dict(c: MineralCandidate) -> dict:
    return {
        "name": c.name, "family": c.family, "score": c.score, "raw_score": c.raw_score,
        "outcome": c.outcome, "elements_used": list(c.elements_used),
        "elements_censored": list(c.elements_censored),
        "elements_unavailable": list(c.elements_unavailable),
        "n_informative_dims": c.n_informative_dims,
        "dimension_coverage": c.dimension_coverage,
        "composition_coverage": c.composition_coverage, "basis": c.basis,
    }


def _validate_candidate(d: dict, where: str) -> MineralCandidate:
    name = _req(d, "name", str, where)
    family = _req(d, "family", str, where)
    basis = _req(d, "basis", str, where)
    score = _unit(_req(d, "score", (int, float), where), f"{where}.score")
    raw = _finite(_req(d, "raw_score", (int, float), where), f"{where}.raw_score")
    outcome = _req(d, "outcome", str, where)
    if outcome not in CANDIDATE_OUTCOMES:
        raise PayloadSerializationError(
            f"{where}.outcome: {outcome!r} not in {sorted(CANDIDATE_OUTCOMES)}.")
    used = _str_list(_req(d, "elements_used", list, where), f"{where}.elements_used")
    censored = _str_list(_req(d, "elements_censored", list, where), f"{where}.elements_censored")
    unavail = _str_list(_req(d, "elements_unavailable", list, where), f"{where}.elements_unavailable")
    n = _req(d, "n_informative_dims", int, where)
    if isinstance(n, bool) or n < 0:
        raise PayloadSerializationError(f"{where}.n_informative_dims: non-negative integer required.")
    if n != len(used):
        raise PayloadSerializationError(
            f"{where}: n_informative_dims ({n}) != len(elements_used) ({len(used)}).")
    dim_cov = _unit(_req(d, "dimension_coverage", (int, float), where), f"{where}.dimension_coverage")
    comp_cov = _unit(_req(d, "composition_coverage", (int, float), where), f"{where}.composition_coverage")
    return MineralCandidate(
        name=name, family=family, score=score, raw_score=raw, outcome=outcome,
        elements_used=tuple(used), elements_censored=tuple(censored),
        elements_unavailable=tuple(unavail), n_informative_dims=n,
        dimension_coverage=dim_cov, composition_coverage=comp_cov, basis=basis)


def _validate_candidate_list(items, where: str, *, ordered: bool) -> tuple[MineralCandidate, ...]:
    if not isinstance(items, list):
        raise PayloadSerializationError(f"{where}: must be a list.")
    cands = [_validate_candidate(c, f"{where}[{i}]") for i, c in enumerate(items)]
    names = [c.name for c in cands]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise PayloadSerializationError(f"{where}: duplicate candidate names {dupes}.")
    if ordered:
        scores = [c.score for c in cands]
        if scores != sorted(scores, reverse=True):
            raise PayloadSerializationError(f"{where}: candidates are not ordered by descending score.")
        for i, c in enumerate(cands):
            if c.outcome != "scored":
                raise PayloadSerializationError(
                    f"{where}[{i}]: rank-eligible candidate must have outcome 'scored'.")
    return tuple(cands)


def _validate_doc(doc: dict, where: str):
    cluster_id = doc.get("cluster_id")
    if not (cluster_id is None or (isinstance(cluster_id, int) and not isinstance(cluster_id, bool))):
        raise PayloadSerializationError(f"{where}.cluster_id: must be an integer or null.")
    if not isinstance(doc.get("reliability_gated"), bool):
        raise PayloadSerializationError(f"{where}.reliability_gated: must be a boolean.")
    lib_name = _req(doc, "library_name", str, where)
    _req(doc, "library_version", str, where)
    ir = doc.get("input_reliability")
    if not (ir is None or isinstance(ir, str)):
        raise PayloadSerializationError(f"{where}.input_reliability: must be a string or null.")
    candidates = _validate_candidate_list(doc.get("candidates", []), f"{where}.candidates", ordered=True)
    insufficient = _validate_candidate_list(doc.get("insufficient", []), f"{where}.insufficient", ordered=False)
    prov = _prov_from_dict(doc.get("provenance"), f"{where}.provenance")
    diags = _diags_from_list(doc.get("diagnostics", []), f"{where}.diagnostics")
    # cross-object consistency: result library_name must match provenance
    if prov is not None and "library_name" in prov.params and prov.params["library_name"] != lib_name:
        raise PayloadSerializationError(
            f"{where}: library_name {lib_name!r} disagrees with provenance "
            f"library_name {prov.params['library_name']!r}.")
    return candidates, insufficient, prov, diags


def write_match(result: MineralMatchResult, directory, stem: str,
                *, overwrite: bool = False) -> Path:
    """Validate then write a MineralMatchResult to ``<stem>_match.json``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}_match.json"
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
    doc = {
        "schema_version": SCHEMA_VERSION, "kind": KIND,
        "cluster_id": result.cluster_id,
        "input_reliability": result.input_reliability,
        "reliability_gated": result.reliability_gated,
        "library_name": result.library_name, "library_version": result.library_version,
        "candidates": [_cand_to_dict(c) for c in result.candidates],
        "insufficient": [_cand_to_dict(c) for c in result.insufficient],
        "provenance": _prov_to_dict(result.provenance),
        "diagnostics": _diags_to_list(result.diagnostics),
    }
    _validate_doc(doc, f"{stem}_match (write)")   # validate-before-write
    path.write_text(json.dumps(doc, indent=2, allow_nan=False))
    return path


def read_match(directory, stem: str) -> MineralMatchResult:
    """Read and deeply validate a MineralMatchResult written by :func:`write_match`."""
    path = Path(directory) / f"{stem}_match.json"
    doc = _load_doc(path)
    candidates, insufficient, prov, diags = _validate_doc(doc, path.name)
    return MineralMatchResult(
        cluster_id=doc["cluster_id"], candidates=candidates, insufficient=insufficient,
        input_reliability=doc["input_reliability"], reliability_gated=doc["reliability_gated"],
        library_name=doc["library_name"], library_version=doc["library_version"],
        provenance=prov, diagnostics=diags)


__all__ = ["KIND", "SCHEMA_VERSION", "read_match", "write_match"]
