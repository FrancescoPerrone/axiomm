"""Versioned JSON file adapters for quant payloads.

Internal adapter, not a stable public contract. Scalars only, so JSON (no
.npz). Refuses silent overwrite. Reads and writes are strict: every
document carries ``schema_version`` and ``kind``, both enforced on read;
non-finite numbers (NaN / Infinity) are rejected in both directions; and a
deserialized document is *fully validated* — required fields, mapping
types, numeric ranges, status vocabularies, element-key consistency and
provenance/diagnostics structure — before a payload is reconstructed
(findings 3, 6). Malformed persisted data raises
:class:`PayloadSerializationError`.

Schema history:

* **v1** — original kfactors adapter (no ``kind`` field).
* **v2** — added the ``kind`` tag; ``quant`` gained ``gross_intensities`` /
  ``background_per_channel`` / ``window_channels`` / ``cluster_id``;
  ``reliability`` gained ``cluster_id`` and the honest status vocabulary.

v2 is a breaking structural change, so ``SCHEMA_VERSION`` was incremented
rather than reused. v1 files are rejected with a clear message; there is no
in-place migration.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from axiomm.analysis.errors import (
    OutputExistsError,
    PayloadSerializationError,
)
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.reliability import CLUSTER_STATUSES, ELEMENT_STATUSES

SCHEMA_VERSION = 2


# --------------------------------------------------------------------------
# strict loading + structural validation
# --------------------------------------------------------------------------

def _reject_nonfinite(token: str):
    raise PayloadSerializationError(f"non-finite JSON value {token!r} is not allowed.")


def _load_doc(path: Path, expected_kind: str) -> dict:
    """Load a quant JSON doc, enforcing finiteness, schema version and kind."""
    if not path.exists():
        raise PayloadSerializationError(f"{path} does not exist.")
    try:
        doc = json.loads(path.read_text(), parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        raise PayloadSerializationError(f"{path.name}: malformed JSON ({exc}).") from exc
    if not isinstance(doc, dict):
        raise PayloadSerializationError(f"{path.name}: document is not a JSON object.")
    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise PayloadSerializationError(
            f"{path.name}: unsupported schema_version {version!r} (expected {SCHEMA_VERSION}); "
            "no migration path — rewrite the file with the current writer."
        )
    kind = doc.get("kind")
    if kind != expected_kind:
        raise PayloadSerializationError(
            f"{path.name}: expected payload kind {expected_kind!r}, got {kind!r}."
        )
    return doc


def _req(doc: dict, key: str, types: type | tuple[type, ...], where: str):
    if key not in doc:
        raise PayloadSerializationError(f"{where}: missing required field {key!r}.")
    value = doc[key]
    if not isinstance(value, types):
        raise PayloadSerializationError(
            f"{where}: field {key!r} has wrong type {type(value).__name__}."
        )
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(float(value))


def _num_mapping(doc: dict, key: str, where: str, *, non_negative: bool = False) -> dict:
    """Validate a ``str -> finite number`` mapping."""
    raw = _req(doc, key, dict, where)
    for k, v in raw.items():
        if not isinstance(k, str):
            raise PayloadSerializationError(f"{where}.{key}: non-string key {k!r}.")
        if not _finite_number(v):
            raise PayloadSerializationError(
                f"{where}.{key}[{k!r}]: not a finite number ({v!r})."
            )
        if non_negative and float(v) < 0:
            raise PayloadSerializationError(
                f"{where}.{key}[{k!r}]: must be >= 0 ({v!r})."
            )
    return raw


def _int_mapping(doc: dict, key: str, where: str) -> dict:
    """Validate a ``str -> non-negative integer`` mapping."""
    raw = _req(doc, key, dict, where)
    for k, v in raw.items():
        if not isinstance(k, str):
            raise PayloadSerializationError(f"{where}.{key}: non-string key {k!r}.")
        if not _is_int(v) or v < 0:
            raise PayloadSerializationError(
                f"{where}.{key}[{k!r}]: must be a non-negative integer ({v!r})."
            )
    return raw


def _validate_cluster_id(doc: dict, where: str):
    cid = doc.get("cluster_id")
    if cid is not None and not _is_int(cid):
        raise PayloadSerializationError(f"{where}: cluster_id must be an integer or null ({cid!r}).")
    return cid


def _validate_provenance(doc: dict, where: str):
    prov = doc.get("provenance")
    if prov is None:
        return None
    if not isinstance(prov, dict):
        raise PayloadSerializationError(f"{where}.provenance: must be an object or null.")
    for field_name in ("tool", "backend"):
        if not isinstance(prov.get(field_name), str):
            raise PayloadSerializationError(
                f"{where}.provenance.{field_name}: missing or not a string."
            )
    if "params" in prov and not isinstance(prov["params"], dict):
        raise PayloadSerializationError(f"{where}.provenance.params: must be an object.")
    return _prov_from_dict(prov)


def _validate_diagnostics(doc: dict, where: str):
    items = doc.get("diagnostics", [])
    if not isinstance(items, list):
        raise PayloadSerializationError(f"{where}.diagnostics: must be a list.")
    for i, d in enumerate(items):
        if not isinstance(d, dict):
            raise PayloadSerializationError(f"{where}.diagnostics[{i}]: not an object.")
        for field_name in ("severity", "code", "message"):
            if not isinstance(d.get(field_name), str):
                raise PayloadSerializationError(
                    f"{where}.diagnostics[{i}].{field_name}: missing or not a string."
                )
        if "context" in d and not isinstance(d["context"], dict):
            raise PayloadSerializationError(f"{where}.diagnostics[{i}].context: must be an object.")
    return _diags_from_list(items)


# --------------------------------------------------------------------------
# provenance / diagnostics (de)serialization
# --------------------------------------------------------------------------

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
                              tool_version=d.get("tool_version"), params=d.get("params", {}))


def _diags_to_list(diagnostics):
    return [
        {"severity": d.severity, "code": d.code, "message": d.message,
         "context": dict(d.context)}
        for d in diagnostics
    ]


def _diags_from_list(items):
    return [
        Diagnostic(severity=d["severity"], code=d["code"], message=d["message"],
                   context=d.get("context", {}))
        for d in items
    ]


def _guard(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise OutputExistsError(f"{path} already exists; pass overwrite=True.")


def _write_validated(doc: dict, path: Path, validator, where: str) -> Path:
    """Validate a built document *before* writing it (never persist garbage)."""
    validator(doc, where)
    _dump(doc, path)
    return path


# --------------------------------------------------------------------------
# per-kind structural + relational validators (shared by read AND write)
# --------------------------------------------------------------------------

def _validate_kfactors_dict(doc: dict, where: str) -> None:
    k_factors = _num_mapping(doc, "k_factors", where)
    sensitivities = _num_mapping(doc, "sensitivities", where, non_negative=True)
    for sym, kv in k_factors.items():
        if float(kv) <= 0:
            raise PayloadSerializationError(f"{where}.k_factors[{sym!r}]: must be > 0 ({kv!r}).")
    for sym, sv in sensitivities.items():
        if float(sv) <= 0:
            raise PayloadSerializationError(
                f"{where}.sensitivities[{sym!r}]: must be > 0 ({sv!r})."
            )
    reference = _req(doc, "reference_element", str, where)
    if reference not in k_factors:
        raise PayloadSerializationError(
            f"{where}: reference_element {reference!r} not among k_factors {sorted(k_factors)}."
        )
    # relational: a sensitivity must exist for every k-factor element
    missing = sorted(set(k_factors) - set(sensitivities))
    if missing:
        raise PayloadSerializationError(
            f"{where}: k_factors elements {missing} have no sensitivity entry."
        )
    excitation = _req(doc, "excitation_kev", (int, float), where)
    if isinstance(excitation, bool) or not (math.isfinite(float(excitation)) and excitation > 0):
        raise PayloadSerializationError(f"{where}: excitation_kev must be finite and > 0 ({excitation!r}).")
    _validate_provenance(doc, where)
    _validate_diagnostics(doc, where)


def _validate_quant_dict(doc: dict, where: str) -> None:
    net = _num_mapping(doc, "net_intensities", where, non_negative=True)
    wt_element = _num_mapping(doc, "wt_percent_element", where, non_negative=True)
    _num_mapping(doc, "wt_percent_oxide", where, non_negative=True)
    reference = _req(doc, "reference_element", str, where)
    gross = _num_mapping(doc, "gross_intensities", where, non_negative=True)
    background = _num_mapping(doc, "background_per_channel", where, non_negative=True)
    window = _int_mapping(doc, "window_channels", where)
    # relational checks: retained facts and wt% describe measured elements, and
    # the reference element must itself be among the measured intensities.
    for name, mapping in (("gross_intensities", gross),
                          ("background_per_channel", background),
                          ("window_channels", window),
                          ("wt_percent_element", wt_element)):
        extra = sorted(set(mapping) - set(net))
        if extra:
            raise PayloadSerializationError(
                f"{where}.{name}: keys {extra} absent from net_intensities."
            )
    # net intensity can never exceed gross (net = gross - background*window)
    for sym, gval in gross.items():
        if float(net[sym]) > float(gval) + 1e-9:
            raise PayloadSerializationError(
                f"{where}: net ({net[sym]}) exceeds gross ({gval}) for {sym!r}."
            )
    if reference not in net:
        raise PayloadSerializationError(
            f"{where}: reference_element {reference!r} not among net_intensities {sorted(net)}."
        )
    _validate_cluster_id(doc, where)
    _validate_provenance(doc, where)
    _validate_diagnostics(doc, where)


def _validate_reliability_dict(doc: dict, where: str) -> None:
    cluster_status = _req(doc, "cluster_status", str, where)
    if cluster_status not in CLUSTER_STATUSES:
        raise PayloadSerializationError(
            f"{where}: cluster_status {cluster_status!r} not in {sorted(CLUSTER_STATUSES)}."
        )
    element_status = _req(doc, "element_status", dict, where)
    for sym, status in element_status.items():
        if not isinstance(sym, str):
            raise PayloadSerializationError(f"{where}.element_status: non-string key {sym!r}.")
        if status not in ELEMENT_STATUSES:
            raise PayloadSerializationError(
                f"{where}.element_status[{sym!r}]: {status!r} not in {sorted(ELEMENT_STATUSES)}."
            )
    reasons = _req(doc, "reasons", list, where)
    if not all(isinstance(r, str) for r in reasons):
        raise PayloadSerializationError(f"{where}.reasons: all entries must be strings.")
    _validate_cluster_id(doc, where)
    _validate_provenance(doc, where)
    _validate_diagnostics(doc, where)


# --------------------------------------------------------------------------
# k-factors
# --------------------------------------------------------------------------

def write_kfactors(ks, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Validate then write ``ks`` to ``<stem>_kfactors.json``."""
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
    return _write_validated(doc, path, _validate_kfactors_dict, f"{stem}_kfactors (write)")


def read_kfactors(directory, stem: str):
    """Read and validate a KFactorSet written by :func:`write_kfactors`."""
    from axiomm.analysis.quant.models import KFactorSet
    path = Path(directory) / f"{stem}_kfactors.json"
    doc = _load_doc(path, "kfactors")
    where = path.name
    _validate_kfactors_dict(doc, where)
    return KFactorSet(
        k_factors=doc["k_factors"],
        sensitivities=doc["sensitivities"],
        reference_element=doc["reference_element"],
        excitation_kev=float(doc["excitation_kev"]),
        provenance=_validate_provenance(doc, where),
        diagnostics=_validate_diagnostics(doc, where),
    )


# --------------------------------------------------------------------------
# quantification result
# --------------------------------------------------------------------------

def write_quant(qr, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Validate then write a QuantResult to ``<stem>_quant.json``."""
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
    return _write_validated(doc, path, _validate_quant_dict, f"{stem}_quant (write)")


def read_quant(directory, stem: str):
    """Read and validate a QuantResult written by :func:`write_quant`."""
    from axiomm.analysis.quant.models import QuantResult
    path = Path(directory) / f"{stem}_quant.json"
    doc = _load_doc(path, "quant")
    where = path.name
    _validate_quant_dict(doc, where)
    return QuantResult(
        net_intensities=doc["net_intensities"],
        wt_percent_element=doc["wt_percent_element"],
        wt_percent_oxide=doc["wt_percent_oxide"],
        reference_element=doc["reference_element"],
        gross_intensities=doc["gross_intensities"],
        background_per_channel=doc["background_per_channel"],
        window_channels=doc["window_channels"],
        cluster_id=_validate_cluster_id(doc, where),
        provenance=_validate_provenance(doc, where),
        diagnostics=_validate_diagnostics(doc, where),
    )


# --------------------------------------------------------------------------
# reliability report
# --------------------------------------------------------------------------

def write_reliability(report, directory, stem: str, *, overwrite: bool = False) -> Path:
    """Validate then write a ReliabilityReport to ``<stem>_reliability.json``."""
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
    return _write_validated(doc, path, _validate_reliability_dict, f"{stem}_reliability (write)")


def read_reliability(directory, stem: str):
    """Read and validate a ReliabilityReport written by :func:`write_reliability`."""
    from axiomm.analysis.quant.reliability import ReliabilityReport
    path = Path(directory) / f"{stem}_reliability.json"
    doc = _load_doc(path, "reliability")
    where = path.name
    _validate_reliability_dict(doc, where)
    return ReliabilityReport(
        cluster_status=doc["cluster_status"],
        element_status=doc["element_status"],
        reasons=tuple(doc["reasons"]),
        cluster_id=_validate_cluster_id(doc, where),
        provenance=_validate_provenance(doc, where),
        diagnostics=_validate_diagnostics(doc, where),
    )


__all__ = ["SCHEMA_VERSION", "read_kfactors", "read_quant", "read_reliability",
           "write_kfactors", "write_quant", "write_reliability"]
