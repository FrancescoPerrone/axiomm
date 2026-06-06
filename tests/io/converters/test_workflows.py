"""Tests for :func:`axiomm.io.converters.workflows.convert_file` (spec §11.2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

hs = pytest.importorskip("hyperspy.api")
h5py = pytest.importorskip("h5py")

from axiomm.io.converters.errors import (
    OutputExistsError,
    ReaderDetectionError,
    UnsupportedFormatError,
)
from axiomm.io.converters.models import ConversionResult
from axiomm.io.converters.workflows import convert_file


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_convert_file_returns_conversion_result(synthetic_xrmmap_h5, tmp_path):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(src, output_path=out, reader="xrmmap_h5")
    assert isinstance(result, ConversionResult)
    assert result.input_path == src
    assert result.output_path == out
    assert result.reader_name == "xrmmap_h5"
    assert result.writer_name == "hspy"


def test_convert_file_writes_loadable_hspy_file(synthetic_xrmmap_h5, tmp_path):
    src = synthetic_xrmmap_h5("input.h5", shape=(4, 3, 16))
    out = tmp_path / "out.hspy"
    convert_file(src, output_path=out, reader="xrmmap_h5")
    loaded = hs.load(str(out))
    assert loaded.data.shape == (4, 3, 16)


def test_convert_file_preserves_axiomm_metadata(synthetic_xrmmap_h5, tmp_path):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    convert_file(src, output_path=out, reader="xrmmap_h5")
    loaded = hs.load(str(out))
    assert loaded.metadata.AXIOMM.reader == "xrmmap_h5"
    assert loaded.metadata.AXIOMM.provenance.reader == "xrmmap_h5"


def test_convert_file_axis_labels_are_correct_end_to_end(
    synthetic_xrmmap_h5, tmp_path
):
    """End-to-end guard against the prototype's silent x/y swap.

    The reader gives x at numpy index 0, y at numpy index 1, Energy at
    numpy index 2. After convert_file the loaded .hspy must keep that
    mapping — i.e. the axis with index_in_array=0 is named 'x' and has
    size 4, even though HyperSpy lists it second in navigation_axes.
    """
    src = synthetic_xrmmap_h5("input.h5", shape=(4, 3, 16))
    out = tmp_path / "out.hspy"
    convert_file(src, output_path=out, reader="xrmmap_h5")
    loaded = hs.load(str(out))

    by_index = {}
    for ax in list(loaded.axes_manager.navigation_axes) + list(
        loaded.axes_manager.signal_axes
    ):
        by_index[ax.index_in_array] = ax
    assert by_index[0].name == "x" and by_index[0].size == 4
    assert by_index[1].name == "y" and by_index[1].size == 3
    assert by_index[2].name == "Energy" and by_index[2].size == 16


def test_convert_file_carries_reader_diagnostics_into_result(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(src, output_path=out, reader="xrmmap_h5")
    codes = {d.code for d in result.diagnostics}
    # The XRMMapH5Reader's MVP behaviour emits this; lazy=True is the default.
    assert "lazy_downgraded_to_eager" in codes


def test_manifest_default_emits_diagnostic_until_chunk_7(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(src, output_path=out, reader="xrmmap_h5")
    codes = {d.code for d in result.diagnostics}
    assert "manifest_not_yet_implemented" in codes
    assert result.manifest_path is None


def test_manifest_false_does_not_emit_the_diagnostic(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(
        src, output_path=out, reader="xrmmap_h5", manifest=False
    )
    codes = {d.code for d in result.diagnostics}
    assert "manifest_not_yet_implemented" not in codes
    assert result.manifest_path is None


# ---------------------------------------------------------------------------
# Output-path resolution (spec §11.2)
# ---------------------------------------------------------------------------

def test_explicit_output_path_wins_over_output_dir(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "custom" / "name.hspy"
    other = tmp_path / "other"
    convert_file(
        src,
        output_path=out,
        output_dir=other,
        reader="xrmmap_h5",
    )
    assert out.exists()
    assert not other.exists()


def test_output_dir_combines_with_stem_and_writer_extension(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("mysample.h5")
    out_dir = tmp_path / "outputs"
    result = convert_file(src, output_dir=out_dir, reader="xrmmap_h5")
    expected = out_dir / "mysample.hspy"
    assert result.output_path == expected
    assert expected.exists()


def test_default_output_replaces_extension_alongside_input(synthetic_xrmmap_h5):
    src = synthetic_xrmmap_h5("input.h5")
    result = convert_file(src, reader="xrmmap_h5")
    expected = src.with_suffix(".hspy")
    assert result.output_path == expected
    assert expected.exists()


# ---------------------------------------------------------------------------
# Reader resolution
# ---------------------------------------------------------------------------

def test_reader_name_resolves_through_builtin_mapping(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(src, output_path=out, reader="xrmmap_h5")
    assert result.reader_name == "xrmmap_h5"


def test_reader_auto_dispatches_to_xrmmap_h5(synthetic_xrmmap_h5, tmp_path):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(src, output_path=out, reader="auto")
    assert result.reader_name == "xrmmap_h5"


def test_reader_auto_raises_when_no_registered_reader_accepts(tmp_path):
    src = tmp_path / "fake.h5"
    src.write_bytes(b"definitely not hdf5")
    with pytest.raises(ReaderDetectionError):
        convert_file(src, output_path=tmp_path / "out.hspy", reader="auto")


def test_unknown_reader_name_raises_unsupported_format(tmp_path):
    src = tmp_path / "x.h5"
    src.touch()
    with pytest.raises(UnsupportedFormatError):
        convert_file(
            src, output_path=tmp_path / "out.hspy", reader="bogus_format"
        )


def test_reader_instance_is_accepted_directly(synthetic_xrmmap_h5, tmp_path):
    from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Reader

    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(src, output_path=out, reader=XRMMapH5Reader())
    assert result.reader_name == "xrmmap_h5"


# ---------------------------------------------------------------------------
# Writer resolution
# ---------------------------------------------------------------------------

def test_unknown_writer_name_raises_unsupported_format(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    with pytest.raises(UnsupportedFormatError):
        convert_file(
            src,
            output_path=tmp_path / "out.unknown",
            reader="xrmmap_h5",
            writer="bogus_writer",
        )


def test_writer_instance_is_accepted_directly(synthetic_xrmmap_h5, tmp_path):
    from axiomm.io.converters.writers.hspy import HSpyWriter

    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    result = convert_file(
        src, output_path=out, reader="xrmmap_h5", writer=HSpyWriter()
    )
    assert result.writer_name == "hspy"


# ---------------------------------------------------------------------------
# Overwrite / skip-existing
# ---------------------------------------------------------------------------

def test_existing_output_raises_by_default(synthetic_xrmmap_h5, tmp_path):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    convert_file(src, output_path=out, reader="xrmmap_h5")
    with pytest.raises(OutputExistsError):
        convert_file(src, output_path=out, reader="xrmmap_h5")


def test_overwrite_true_replaces_existing_output(synthetic_xrmmap_h5, tmp_path):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    convert_file(src, output_path=out, reader="xrmmap_h5")
    result = convert_file(
        src, output_path=out, reader="xrmmap_h5", overwrite=True
    )
    assert result.output_path == out


def test_skip_existing_leaves_file_and_short_circuits(
    synthetic_xrmmap_h5, tmp_path
):
    src = synthetic_xrmmap_h5("input.h5")
    out = tmp_path / "out.hspy"
    out.write_bytes(b"sentinel")

    result = convert_file(
        src, output_path=out, reader="xrmmap_h5", skip_existing=True
    )
    # File was not overwritten.
    assert out.read_bytes() == b"sentinel"
    # Result still describes the file.
    assert result.output_path == out
    assert result.reader_name == "xrmmap_h5"
    # An info diagnostic records the short-circuit.
    codes = {d.code for d in result.diagnostics}
    assert "output_skipped_existing" in codes


# ---------------------------------------------------------------------------
# Top-level import
# ---------------------------------------------------------------------------

def test_convert_file_is_importable_from_converters_top_level():
    from axiomm.io.converters import convert_file as cf

    assert callable(cf)


# ---------------------------------------------------------------------------
# Import hygiene
# ---------------------------------------------------------------------------

def test_importing_workflows_does_not_load_tkinter():
    for mod_name in list(sys.modules):
        if (
            mod_name in ("tkinter", "_tkinter")
            or mod_name.startswith("tkinter.")
        ):
            del sys.modules[mod_name]

    import importlib

    import axiomm.io.converters.workflows as mod

    importlib.reload(mod)

    leaked = sorted(
        m
        for m in sys.modules
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter.")
    )
    assert not leaked, f"workflows module leaked tkinter imports: {leaked!r}"
