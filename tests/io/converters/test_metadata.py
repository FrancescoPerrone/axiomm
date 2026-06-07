"""Tests for :mod:`axiomm.io.converters.metadata`.

Each composable transformer is tested in isolation, not just through
the orchestrator that calls them. This is the "tests prove reuse" rule
from the modularity policy: if a helper is claimed as reusable, at
least one test must exercise it on its own.
"""

from __future__ import annotations

from pathlib import Path

from axiomm.io.converters.metadata import (
    build_axiomm_namespace,
    diagnostics_to_dicts,
    nest_axes_section,
    nest_classification,
    nest_converter_section,
    nest_source_section,
)
from axiomm.io.converters.models import (
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)


# ---------------------------------------------------------------------------
# nest_converter_section
# ---------------------------------------------------------------------------

def test_nest_converter_section_returns_three_documented_keys():
    section = nest_converter_section(
        reader_name="xrmmap_h5",
        reader_version="0.0.0",
        config={"counts_path": "/x"},
    )
    assert set(section) == {"reader", "reader_version", "config"}
    assert section["reader"] == "xrmmap_h5"
    assert section["reader_version"] == "0.0.0"
    assert section["config"] == {"counts_path": "/x"}


def test_nest_converter_section_treats_none_config_as_empty_dict():
    section = nest_converter_section(
        reader_name="x", reader_version=None, config=None,
    )
    assert section["config"] == {}


def test_nest_converter_section_copies_config_dict():
    """Mutating the returned config must not mutate the caller's dict."""
    original = {"counts_path": "/x"}
    section = nest_converter_section(
        reader_name="x", reader_version=None, config=original,
    )
    section["config"]["counts_path"] = "/y"
    assert original["counts_path"] == "/x"


# ---------------------------------------------------------------------------
# nest_axes_section
# ---------------------------------------------------------------------------

def test_nest_axes_section_returns_one_dict_per_axis():
    axes = (
        AxisSpec("x", "navigation", 4, units="µm", scale=1.0, index_in_array=0),
        AxisSpec("Energy", "signal", 16, units="keV", scale=0.01, index_in_array=1),
    )
    result = nest_axes_section(axes)
    assert len(result) == 2
    assert result[0]["name"] == "x"
    assert result[0]["role"] == "navigation"
    assert result[0]["size"] == 4
    assert result[0]["units"] == "µm"
    assert result[0]["scale"] == 1.0
    assert result[0]["offset"] == 0.0
    assert result[0]["index_in_array"] == 0


def test_nest_axes_section_handles_empty_tuple():
    assert nest_axes_section(()) == []


# ---------------------------------------------------------------------------
# nest_source_section
# ---------------------------------------------------------------------------

def test_nest_source_section_returns_none_for_none_provenance():
    assert nest_source_section(None) is None


def test_nest_source_section_stringifies_path():
    provenance = SourceProvenance(
        path=Path("/tmp/example.h5"),
        reader="xrmmap_h5",
        reader_version="0.0.0",
        input_hash="cafebabe",
    )
    section = nest_source_section(provenance)
    assert section == {
        "path": "/tmp/example.h5",
        "reader": "xrmmap_h5",
        "reader_version": "0.0.0",
        "input_hash": "cafebabe",
    }


# ---------------------------------------------------------------------------
# diagnostics_to_dicts
# ---------------------------------------------------------------------------

def test_diagnostics_to_dicts_serialises_each_field():
    diags = [
        Diagnostic("info", "code_i", "msg i"),
        Diagnostic("warning", "code_w", "msg w", {"key": "value"}),
    ]
    result = diagnostics_to_dicts(diags)
    assert len(result) == 2
    assert result[0] == {
        "severity": "info",
        "code": "code_i",
        "message": "msg i",
        "context": {},
    }
    assert result[1]["severity"] == "warning"
    assert result[1]["context"] == {"key": "value"}


def test_diagnostics_to_dicts_handles_empty_input():
    assert diagnostics_to_dicts([]) == []


def test_diagnostics_to_dicts_accepts_tuples_and_other_iterables():
    diags = (Diagnostic("info", "c", "m"),)
    assert len(diagnostics_to_dicts(diags)) == 1


# ---------------------------------------------------------------------------
# nest_classification
# ---------------------------------------------------------------------------

def test_nest_classification_normalises_to_three_buckets():
    result = nest_classification({"observed": ["x"]})
    # Missing buckets default to empty lists.
    assert result == {"observed": ["x"], "inferred": [], "assumed": []}


def test_nest_classification_handles_none():
    result = nest_classification(None)
    assert result == {"observed": [], "inferred": [], "assumed": []}


def test_nest_classification_copies_inner_lists():
    """Mutating the result must not affect the caller's lists."""
    src = {"observed": ["a"], "inferred": ["b"], "assumed": ["c"]}
    result = nest_classification(src)
    result["observed"].append("mutated")
    assert src["observed"] == ["a"]


def test_nest_classification_drops_unexpected_buckets():
    """The three documented buckets are the contract; extras don't leak through."""
    result = nest_classification({"observed": [], "rogue_bucket": ["x"]})
    assert set(result) == {"observed", "inferred", "assumed"}


# ---------------------------------------------------------------------------
# build_axiomm_namespace — orchestrator over the above
# ---------------------------------------------------------------------------

def test_build_axiomm_namespace_composes_required_sections():
    namespace = build_axiomm_namespace(
        reader_name="xrmmap_h5",
        reader_version="0.0.0",
        config={"counts_path": "/x"},
        axes=(
            AxisSpec("x", "navigation", 4, index_in_array=0),
        ),
        provenance=SourceProvenance(
            path=Path("/tmp/in.h5"), reader="xrmmap_h5",
        ),
        classification={"observed": ["data"]},
        diagnostics=[Diagnostic("info", "c", "m")],
    )
    assert set(namespace) == {
        "converter",
        "axes",
        "source",
        "provenance_classification",
        "diagnostics",
    }


def test_build_axiomm_namespace_omits_source_when_provenance_is_none():
    namespace = build_axiomm_namespace(
        reader_name="x", reader_version=None, config=None,
        axes=(), provenance=None, classification=None, diagnostics=[],
    )
    assert "source" not in namespace
    # All other sections still present.
    assert "converter" in namespace
    assert "axes" in namespace
    assert "provenance_classification" in namespace
    assert "diagnostics" in namespace


def test_build_axiomm_namespace_delegates_to_transformers():
    """Sanity check that the orchestrator returns what the transformers produce.

    Acts as a guard that future refactors of the orchestrator don't drift
    from the per-transformer contracts.
    """
    axes = (AxisSpec("x", "navigation", 4, units="µm", index_in_array=0),)
    diags = [Diagnostic("warning", "w", "warn")]
    provenance = SourceProvenance(path=Path("/in.h5"), reader="r")
    classification = {"observed": ["data"]}

    ns = build_axiomm_namespace(
        reader_name="r",
        reader_version="v",
        config={"a": 1},
        axes=axes,
        provenance=provenance,
        classification=classification,
        diagnostics=diags,
    )

    assert ns["converter"] == nest_converter_section(
        reader_name="r", reader_version="v", config={"a": 1},
    )
    assert ns["axes"] == nest_axes_section(axes)
    assert ns["source"] == nest_source_section(provenance)
    assert ns["provenance_classification"] == nest_classification(classification)
    assert ns["diagnostics"] == diagnostics_to_dicts(diags)
