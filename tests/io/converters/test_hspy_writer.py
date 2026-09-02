"""Tests for :mod:`axiomm.io.converters.writers.hspy` (spec §9.4)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

hs = pytest.importorskip("hyperspy.api")

from axiomm.io.converters.errors import OutputExistsError
from axiomm.io.converters.writers.hspy import HSpyWriter


@pytest.fixture
def signal():
    """A minimal HyperSpy ``Signal1D`` with a non-trivial shape."""
    return hs.signals.Signal1D(np.zeros((4, 3, 16), dtype=np.float32))


# -- protocol attributes -----------------------------------------------------

def test_writer_advertises_name_and_extensions():
    w = HSpyWriter()
    assert w.name == "hspy"
    assert w.supported_extensions == (".hspy",)


# -- write happy path --------------------------------------------------------

def test_write_creates_hspy_file(signal, tmp_path):
    out = tmp_path / "ok.hspy"
    result = HSpyWriter().write(signal, out)
    assert result == out
    assert out.exists()


def test_write_accepts_string_path(signal, tmp_path):
    out = tmp_path / "ok.hspy"
    result = HSpyWriter().write(signal, str(out))
    assert isinstance(result, Path)
    assert result == out


def test_write_creates_parent_directories(signal, tmp_path):
    out = tmp_path / "nested" / "deep" / "ok.hspy"
    HSpyWriter().write(signal, out)
    assert out.exists()


def test_written_file_loads_back_with_same_shape(signal, tmp_path):
    out = tmp_path / "ok.hspy"
    HSpyWriter().write(signal, out)
    loaded = hs.load(str(out))
    assert loaded.data.shape == signal.data.shape


def test_axiomm_metadata_namespace_survives_round_trip(signal, tmp_path):
    signal.metadata.add_dictionary(
        {"AXIOMM": {"reader": "xrmmap_h5", "config": {"counts_path": "/x"}}}
    )
    out = tmp_path / "ok.hspy"
    HSpyWriter().write(signal, out)
    loaded = hs.load(str(out))
    assert loaded.metadata.AXIOMM.reader == "xrmmap_h5"
    assert loaded.metadata.AXIOMM.config.counts_path == "/x"


# -- overwrite policy --------------------------------------------------------

def test_refuses_to_overwrite_existing_file_by_default(signal, tmp_path):
    out = tmp_path / "ok.hspy"
    out.write_bytes(b"pre-existing")
    with pytest.raises(OutputExistsError):
        HSpyWriter().write(signal, out)
    # Original file is untouched.
    assert out.read_bytes() == b"pre-existing"


def test_overwrite_true_replaces_existing_file(signal, tmp_path):
    out = tmp_path / "ok.hspy"
    out.write_bytes(b"old content not real hspy")
    HSpyWriter().write(signal, out, overwrite=True)
    loaded = hs.load(str(out))
    assert loaded.data.shape == signal.data.shape


def test_overwrite_error_message_is_actionable(signal, tmp_path):
    out = tmp_path / "ok.hspy"
    out.touch()
    with pytest.raises(OutputExistsError) as exc:
        HSpyWriter().write(signal, out)
    msg = str(exc.value)
    assert str(out) in msg
    assert "overwrite" in msg


# -- import hygiene ----------------------------------------------------------

def test_importing_writer_module_does_not_load_tkinter():
    for mod_name in list(sys.modules):
        if (
            mod_name in ("tkinter", "_tkinter")
            or mod_name.startswith("tkinter.")
        ):
            del sys.modules[mod_name]

    import importlib

    import axiomm.io.converters.writers.hspy as mod

    importlib.reload(mod)

    leaked = sorted(
        m
        for m in sys.modules
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter.")
    )
    assert not leaked, f"writer module leaked tkinter imports: {leaked!r}"
