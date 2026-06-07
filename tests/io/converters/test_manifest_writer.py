"""Tests for :mod:`axiomm.io.converters.writers.manifest` (spec §9.5)."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from axiomm.io.converters.errors import OutputExistsError
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)
from axiomm.io.converters.writers.manifest import (
    MANIFEST_SCHEMA_VERSION,
    MANIFEST_SUFFIX,
    ManifestWriter,
    build_manifest_dict,
    extract_reader_config,
    manifest_path_for,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(*, with_classification: bool = True) -> AxiommSignalPayload:
    data = np.zeros((4, 3, 16), dtype=np.float32)
    axes = (
        AxisSpec("x", "navigation", 4, units="µm", scale=1.0, index_in_array=0),
        AxisSpec("y", "navigation", 3, units="µm", scale=1.0, index_in_array=1),
        AxisSpec("Energy", "signal", 16, units="keV", scale=0.01, index_in_array=2),
    )
    metadata: dict = {"AXIOMM": {"reader": "xrmmap_h5"}}
    if with_classification:
        metadata["AXIOMM"]["provenance_classification"] = {
            "observed": ["data"],
            "inferred": ["axes.x.size"],
            "assumed": ["axes.Energy.scale"],
        }
    return AxiommSignalPayload(
        data=data,
        axes=axes,
        signal_kind="signal1d",
        metadata=metadata,
        original_metadata={"environ": {"key": "value"}},
        provenance=SourceProvenance(
            path=Path("/tmp/example.h5"), reader="xrmmap_h5",
        ),
        diagnostics=[
            Diagnostic("info", "test_info", "info message"),
            Diagnostic("warning", "test_warn", "warn message", {"k": "v"}),
        ],
        title="example",
    )


# ---------------------------------------------------------------------------
# Constants and path helper
# ---------------------------------------------------------------------------

def test_manifest_suffix_is_dot_axiomm_json():
    assert MANIFEST_SUFFIX == ".axiomm.json"


def test_manifest_schema_version_is_a_nonempty_string():
    assert isinstance(MANIFEST_SCHEMA_VERSION, str)
    assert MANIFEST_SCHEMA_VERSION


def test_manifest_path_for_appends_full_suffix_to_output_name(tmp_path):
    out = tmp_path / "A21_054.hspy"
    assert manifest_path_for(out) == tmp_path / "A21_054.hspy.axiomm.json"


def test_manifest_path_for_accepts_string():
    assert manifest_path_for("/tmp/a.hspy") == Path("/tmp/a.hspy.axiomm.json")


# ---------------------------------------------------------------------------
# build_manifest_dict
# ---------------------------------------------------------------------------

def test_build_manifest_dict_has_required_fields():
    payload = _make_payload()
    m = build_manifest_dict(
        input_path=Path("/tmp/in.h5"),
        output_path=Path("/tmp/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    required = {
        "manifest_schema_version",
        "axiomm_version",
        "created_at",
        "input_path",
        "output_path",
        "reader_name",
        "writer_name",
        "source_shape",
        "axes_summary",
        "diagnostics",
        "config_used",
        "provenance_classification",
    }
    assert required.issubset(m.keys())


def test_build_manifest_dict_records_iso_8601_timestamp():
    payload = _make_payload()
    m = build_manifest_dict(
        input_path=Path("/tmp/in.h5"),
        output_path=Path("/tmp/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    # Round-trip parseability is the contract.
    parsed = datetime.fromisoformat(m["created_at"])
    assert parsed.tzinfo is not None  # must be timezone-aware (UTC)


def test_build_manifest_dict_source_shape_matches_data():
    payload = _make_payload()
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    assert m["source_shape"] == [4, 3, 16]


def test_build_manifest_dict_axes_summary_lists_each_axis():
    payload = _make_payload()
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    summary = m["axes_summary"]
    assert len(summary) == 3
    names = [a["name"] for a in summary]
    assert names == ["x", "y", "Energy"]
    energy = next(a for a in summary if a["name"] == "Energy")
    assert energy["units"] == "keV"
    assert energy["scale"] == pytest.approx(0.01)
    assert energy["role"] == "signal"


def test_build_manifest_dict_classification_is_three_bucket_dict():
    payload = _make_payload()
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    c = m["provenance_classification"]
    assert set(c.keys()) == {"observed", "inferred", "assumed"}
    assert c["observed"] == ["data"]
    assert c["inferred"] == ["axes.x.size"]
    assert c["assumed"] == ["axes.Energy.scale"]


def test_build_manifest_dict_classification_defaults_when_payload_has_none():
    payload = _make_payload(with_classification=False)
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    c = m["provenance_classification"]
    # Schema stable even for readers that don't classify.
    assert c == {"observed": [], "inferred": [], "assumed": []}


def test_build_manifest_dict_diagnostics_include_extras():
    payload = _make_payload()
    extras = (Diagnostic("info", "workflow_extra", "from workflow"),)
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
        extra_diagnostics=extras,
    )
    codes = {d["code"] for d in m["diagnostics"]}
    # Reader's diagnostics plus the workflow's extras.
    assert codes == {"test_info", "test_warn", "workflow_extra"}


def test_build_manifest_dict_passes_through_config_used():
    payload = _make_payload()
    cfg = {"counts_path": "/x/y", "energy_scale": 0.01}
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
        config_used=cfg,
    )
    assert m["config_used"] == cfg


def test_build_manifest_dict_is_json_serialisable():
    payload = _make_payload()
    m = build_manifest_dict(
        input_path=Path("/in.h5"),
        output_path=Path("/out.hspy"),
        reader_name="xrmmap_h5",
        writer_name="hspy",
        payload=payload,
    )
    # default=str catches any stragglers (e.g. Path / np types if leaked).
    json.dumps(m)


# ---------------------------------------------------------------------------
# extract_reader_config
# ---------------------------------------------------------------------------

def test_extract_reader_config_returns_dataclass_dict():
    pytest.importorskip("h5py")
    from axiomm.io.converters.readers.xrmmap_h5 import (
        XRMMapH5Config,
        XRMMapH5Reader,
    )

    reader = XRMMapH5Reader(config=XRMMapH5Config(counts_path="/custom"))
    cfg = extract_reader_config(reader)
    assert cfg["counts_path"] == "/custom"
    # All XRMMapH5Config fields should appear.
    assert "energy_scale" in cfg


def test_extract_reader_config_returns_empty_for_readerless_object():
    assert extract_reader_config(object()) == {}


def test_extract_reader_config_returns_empty_when_config_is_not_dataclass():
    class _Bare:
        config = {"counts_path": "/x"}  # not a dataclass

    assert extract_reader_config(_Bare()) == {}


# ---------------------------------------------------------------------------
# ManifestWriter
# ---------------------------------------------------------------------------

def test_writer_advertises_name_and_extensions():
    w = ManifestWriter()
    assert w.name == "manifest"
    assert w.supported_extensions == (MANIFEST_SUFFIX,)


def test_writer_writes_json_file(tmp_path):
    out = tmp_path / "out.hspy.axiomm.json"
    result = ManifestWriter().write({"foo": "bar"}, out)
    assert result == out
    assert json.loads(out.read_text()) == {"foo": "bar"}


def test_writer_creates_parent_directories(tmp_path):
    out = tmp_path / "nested" / "deep" / "out.axiomm.json"
    ManifestWriter().write({"a": 1}, out)
    assert out.exists()


def test_writer_refuses_to_overwrite_by_default(tmp_path):
    out = tmp_path / "m.json"
    out.write_text("{}")
    with pytest.raises(OutputExistsError):
        ManifestWriter().write({"foo": "bar"}, out)


def test_writer_overwrite_true_replaces_file(tmp_path):
    out = tmp_path / "m.json"
    out.write_text("{}")
    ManifestWriter().write({"foo": "bar"}, out, overwrite=True)
    assert json.loads(out.read_text()) == {"foo": "bar"}


def test_writer_output_is_sorted_for_diff_friendliness(tmp_path):
    """Sorted keys keep diffs across re-runs minimal."""
    out = tmp_path / "m.json"
    ManifestWriter().write({"b": 1, "a": 2}, out)
    text = out.read_text()
    assert text.index('"a"') < text.index('"b"')


# ---------------------------------------------------------------------------
# Import hygiene
# ---------------------------------------------------------------------------

def test_importing_manifest_module_does_not_load_tkinter():
    for mod_name in list(sys.modules):
        if (
            mod_name in ("tkinter", "_tkinter")
            or mod_name.startswith("tkinter.")
        ):
            del sys.modules[mod_name]

    import importlib

    import axiomm.io.converters.writers.manifest as mod

    importlib.reload(mod)

    leaked = sorted(
        m
        for m in sys.modules
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter.")
    )
    assert not leaked, f"manifest module leaked tkinter imports: {leaked!r}"
