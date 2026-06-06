"""Acceptance test §24.1: ``import axiomm.io.converters`` must be silent.

The headless-core rule (spec §10.2) requires that the four core converter
components never trigger a GUI window, an ``input()`` prompt, or stdout
output as a side effect of being imported. This test guards that invariant
and must keep passing across every chunk.
"""

from __future__ import annotations

import builtins
import io
import sys

import pytest


def _drop_axiomm_modules() -> None:
    """Remove any cached ``axiomm.*`` modules so the next import is fresh."""
    for mod_name in list(sys.modules):
        if mod_name == "axiomm" or mod_name.startswith("axiomm."):
            del sys.modules[mod_name]


def test_import_does_not_call_input(monkeypatch):
    """Importing the converter package must not call ``builtins.input``."""

    def _fail_input(prompt: object = "") -> str:  # pragma: no cover - defensive
        raise AssertionError(
            f"input() was called during import with prompt={prompt!r}"
        )

    monkeypatch.setattr(builtins, "input", _fail_input)
    _drop_axiomm_modules()

    import axiomm.io.converters  # noqa: F401


def test_import_does_not_load_tkinter():
    """Importing the converter package must not pull in tkinter, even transitively."""
    for mod_name in list(sys.modules):
        if (
            mod_name == "axiomm"
            or mod_name.startswith("axiomm.")
            or mod_name in {"tkinter", "_tkinter"}
            or mod_name.startswith("tkinter.")
        ):
            del sys.modules[mod_name]

    import axiomm.io.converters  # noqa: F401

    leaked = sorted(
        m for m in sys.modules if m == "tkinter" or m.startswith("tkinter.") or m == "_tkinter"
    )
    assert not leaked, f"core converter modules pulled in tkinter: {leaked!r}"


def test_import_is_silent_on_stdout(capsys):
    """Importing the converter package must not write to stdout or stderr."""
    _drop_axiomm_modules()
    # Drain any output captured before this point.
    capsys.readouterr()

    import axiomm.io.converters  # noqa: F401

    captured = capsys.readouterr()
    assert captured.out == "", f"unexpected stdout on import: {captured.out!r}"
    assert captured.err == "", f"unexpected stderr on import: {captured.err!r}"


def test_public_symbols_exposed():
    """Sanity check that the documented top-level symbols are importable."""
    from axiomm.io.converters import (  # noqa: F401
        AxiommConverterError,
        AxiommSignalPayload,
        AxisSpec,
        ConversionResult,
        Diagnostic,
        Reader,
        SignalBuilder,
        SourceProvenance,
        Writer,
        discover_inputs,
    )


def test_lazy_concrete_reader_exports():
    """XRMMapH5Reader / XRMMapH5Config are importable lazily from the top-level package."""
    pytest.importorskip("h5py")
    from axiomm.io.converters import XRMMapH5Config, XRMMapH5Reader  # noqa: F401

    assert XRMMapH5Reader().name == "xrmmap_h5"
    assert XRMMapH5Config().counts_path == "/xrmmap/mcasum/counts"


def test_lazy_concrete_builder_exports():
    """HyperSpyBuilder / build_hyperspy_signal are importable lazily from the top-level package."""
    pytest.importorskip("hyperspy")
    from axiomm.io.converters import HyperSpyBuilder, build_hyperspy_signal  # noqa: F401

    assert HyperSpyBuilder().name == "hyperspy"
    assert callable(build_hyperspy_signal)


def test_validate_axes_is_eagerly_importable():
    """validate_axes is part of the package surface and does not require hyperspy."""
    from axiomm.io.converters import validate_axes  # noqa: F401

    assert callable(validate_axes)


def test_models_are_backend_neutral():
    """Models module must not depend on hyperspy or h5py."""
    _drop_axiomm_modules()
    for mod_name in list(sys.modules):
        if mod_name.startswith(("hyperspy", "h5py")):
            del sys.modules[mod_name]

    import axiomm.io.converters.models  # noqa: F401

    forbidden = sorted(
        m for m in sys.modules if m.startswith(("hyperspy", "h5py"))
    )
    assert not forbidden, (
        f"axiomm.io.converters.models leaked backend imports: {forbidden!r}"
    )
