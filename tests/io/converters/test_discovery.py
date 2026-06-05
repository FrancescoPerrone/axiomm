"""Tests for :func:`axiomm.io.converters.discovery.discover_inputs` (spec §6)."""

from __future__ import annotations

import builtins
import sys
from pathlib import Path

import pytest

from axiomm.io.converters.discovery import discover_inputs
from axiomm.io.converters.errors import InputDiscoveryError


def _touch(directory: Path, relpath: str) -> Path:
    p = directory / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    p.touch()
    return p


# -- single-file input --------------------------------------------------------

def test_discover_single_file_returns_that_file(tmp_path: Path) -> None:
    f = _touch(tmp_path, "A21_054_map.h5")
    assert discover_inputs(f) == [f]


def test_discover_single_file_accepts_string_path(tmp_path: Path) -> None:
    f = _touch(tmp_path, "A21_054_map.h5")
    assert discover_inputs(str(f)) == [f]


def test_discover_single_file_overrides_filters(tmp_path: Path) -> None:
    """Pointing at a specific file is an explicit user choice that overrides filters."""
    f = _touch(tmp_path, "notes.txt")
    assert discover_inputs(f, extensions=(".h5",), sample="A21_054") == [f]


# -- directory + extension filter ---------------------------------------------

def test_discover_directory_extension_filter(tmp_path: Path) -> None:
    keep1 = _touch(tmp_path, "a.h5")
    keep2 = _touch(tmp_path, "b.hdf5")
    _touch(tmp_path, "c.txt")
    _touch(tmp_path, "d.csv")

    result = discover_inputs(tmp_path, extensions=(".h5", ".hdf5"))

    assert result == sorted([keep1, keep2])


def test_extension_match_is_case_insensitive_on_files(tmp_path: Path) -> None:
    upper = _touch(tmp_path, "upper.H5")
    mixed = _touch(tmp_path, "mixed.Hdf5")
    _touch(tmp_path, "other.txt")

    result = discover_inputs(tmp_path, extensions=(".h5", ".hdf5"))

    assert result == sorted([upper, mixed])


def test_extension_match_is_case_insensitive_on_filter(tmp_path: Path) -> None:
    keep = _touch(tmp_path, "a.h5")

    result = discover_inputs(tmp_path, extensions=(".H5",))

    assert result == [keep]


# -- directory + sample filter ------------------------------------------------

def test_discover_directory_sample_filter(tmp_path: Path) -> None:
    matches = [
        _touch(tmp_path, "A21_054_map.h5"),
        _touch(tmp_path, "A21_054_other.h5"),
        _touch(tmp_path, "prefix_A21_054.h5"),
    ]
    _touch(tmp_path, "B99_001.h5")
    _touch(tmp_path, "unrelated.h5")

    result = discover_inputs(tmp_path, extensions=(".h5",), sample="A21_054")

    assert result == sorted(matches)


def test_sample_filter_targets_filename_not_path(tmp_path: Path) -> None:
    """A parent directory whose *name* contains the sample must not pull in unrelated files."""
    nested_dir = tmp_path / "A21_054"
    f = _touch(nested_dir, "irrelevant.h5")

    result = discover_inputs(
        tmp_path,
        extensions=(".h5",),
        sample="A21_054",
        recursive=True,
        require_non_empty=False,
    )

    assert result == []
    assert f.exists()  # sanity: the file does exist, it just doesn't match


# -- recursion ----------------------------------------------------------------

def test_recursive_true_descends_into_subdirectories(tmp_path: Path) -> None:
    top = _touch(tmp_path, "top.h5")
    nested = _touch(tmp_path, "sub/deep/nested.h5")

    result = discover_inputs(tmp_path, extensions=(".h5",), recursive=True)

    assert result == sorted([top, nested])


def test_recursive_false_does_not_descend(tmp_path: Path) -> None:
    top = _touch(tmp_path, "top.h5")
    _touch(tmp_path, "sub/nested.h5")

    result = discover_inputs(tmp_path, extensions=(".h5",), recursive=False)

    assert result == [top]


# -- determinism --------------------------------------------------------------

def test_results_are_deterministically_sorted(tmp_path: Path) -> None:
    # create files in a non-alphabetical creation order
    z = _touch(tmp_path, "z.h5")
    a = _touch(tmp_path, "a.h5")
    m = _touch(tmp_path, "m.h5")

    first = discover_inputs(tmp_path, extensions=(".h5",))
    second = discover_inputs(tmp_path, extensions=(".h5",))

    assert first == sorted([z, a, m])
    assert first == second


# -- error / empty handling ---------------------------------------------------

def test_no_matches_raises_input_discovery_error(tmp_path: Path) -> None:
    _touch(tmp_path, "a.txt")

    with pytest.raises(InputDiscoveryError):
        discover_inputs(tmp_path, extensions=(".h5",))


def test_no_matches_returns_empty_when_require_non_empty_false(tmp_path: Path) -> None:
    _touch(tmp_path, "a.txt")

    assert discover_inputs(tmp_path, extensions=(".h5",), require_non_empty=False) == []


def test_nonexistent_path_raises_input_discovery_error(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    with pytest.raises(InputDiscoveryError):
        discover_inputs(missing)


def test_nonexistent_path_raises_even_with_require_non_empty_false(tmp_path: Path) -> None:
    """A missing path is a hard error: it's not 'matched nothing', it's 'invalid input'."""
    missing = tmp_path / "does_not_exist"

    with pytest.raises(InputDiscoveryError):
        discover_inputs(missing, require_non_empty=False)


# -- no side effects ----------------------------------------------------------

def test_discover_inputs_is_silent(capsys, tmp_path: Path) -> None:
    f = _touch(tmp_path, "a.h5")
    discover_inputs(f)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_discover_inputs_does_not_call_input(monkeypatch, tmp_path: Path) -> None:
    def _fail_input(prompt: object = "") -> str:  # pragma: no cover
        raise AssertionError(f"input() called with prompt={prompt!r}")

    monkeypatch.setattr(builtins, "input", _fail_input)
    f = _touch(tmp_path, "a.h5")
    discover_inputs(f)


def test_discover_inputs_does_not_import_h5py_or_tkinter(tmp_path: Path) -> None:
    """discover_inputs is filesystem-only — no HDF5 reading, no GUI."""
    # Drop any cached imports so we get a clean measurement.
    for mod_name in list(sys.modules):
        if (
            mod_name.startswith(("h5py", "tkinter"))
            or mod_name == "_tkinter"
            or mod_name == "axiomm.io.converters.discovery"
        ):
            del sys.modules[mod_name]

    from axiomm.io.converters.discovery import discover_inputs as fresh_discover

    f = _touch(tmp_path, "a.h5")
    fresh_discover(f)

    leaked = sorted(
        m for m in sys.modules if m.startswith(("h5py", "tkinter")) or m == "_tkinter"
    )
    assert not leaked, f"discovery leaked imports: {leaked!r}"
