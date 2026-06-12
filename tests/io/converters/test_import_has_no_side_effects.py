"""Acceptance test §24.1: ``import axiomm.io.converters`` must be silent.

The headless-core rule (spec §10.2) requires that the four core converter
components never trigger a GUI window, an ``input()`` prompt, or stdout
output as a side effect of being imported. This test guards that invariant
and must keep passing across every chunk.

**Why these tests run in subprocesses.** A fresh import of
``axiomm.io.converters`` is the only way to observe the side effects of
import itself. Deleting cached ``axiomm.*`` modules from the parent
process's ``sys.modules`` and re-importing in place would corrupt class
identity for any tests that loaded the package earlier (the freshly-
imported exception classes would not be ``isinstance``-compatible with
the classes already captured by closures in the writer / builder / reader
modules), breaking later tests in the same session. Subprocesses
guarantee isolation without that side effect.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest


def _run_in_subprocess(script: str) -> subprocess.CompletedProcess:
    """Execute ``script`` in a fresh Python interpreter and return the result.

    Propagates the current ``sys.path`` to the subprocess via
    ``PYTHONPATH`` so that the package is importable in environments
    that rely on pytest's ``[tool.pytest.ini_options].pythonpath``
    setting rather than an editable install.
    """
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _assert_subprocess_ok(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


def test_import_does_not_call_input():
    """Importing the converter package must not call ``builtins.input``."""
    result = _run_in_subprocess(
        """
        import builtins, sys

        def _fail(*args, **kwargs):
            raise AssertionError(
                f"input() was called during import (args={args!r})"
            )

        builtins.input = _fail
        import axiomm.io.converters  # noqa: F401
        """
    )
    _assert_subprocess_ok(result)


def test_import_does_not_load_tkinter():
    """Importing the converter package must not pull in tkinter, even transitively."""
    result = _run_in_subprocess(
        """
        import sys
        import axiomm.io.converters  # noqa: F401

        leaked = sorted(
            m for m in sys.modules
            if m == 'tkinter' or m.startswith('tkinter.') or m == '_tkinter'
        )
        if leaked:
            raise AssertionError(
                f'importing axiomm.io.converters pulled in tkinter: {leaked!r}'
            )
        """
    )
    _assert_subprocess_ok(result)


def test_import_is_silent_on_stdout():
    """Importing the converter package must not write to stdout or stderr."""
    result = _run_in_subprocess(
        """
        import io, sys

        captured_out = io.StringIO()
        captured_err = io.StringIO()
        sys.stdout = captured_out
        sys.stderr = captured_err

        import axiomm.io.converters  # noqa: F401

        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

        out = captured_out.getvalue()
        err = captured_err.getvalue()
        if out or err:
            raise AssertionError(
                f'import wrote to stdout/stderr. stdout={out!r} stderr={err!r}'
            )
        """
    )
    _assert_subprocess_ok(result)


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
    """XRMMapH5Reader / XRMMapH5Calibration / XRMMAP_H5_SCHEMA are
    importable lazily from the top-level package (Phase 4, Chunk 17)."""
    pytest.importorskip("h5py")
    from axiomm.io.converters import (  # noqa: F401
        XRMMAP_H5_SCHEMA,
        XRMMapH5Calibration,
        XRMMapH5Reader,
    )

    assert XRMMapH5Reader().name == "xrmmap_h5"
    assert XRMMAP_H5_SCHEMA.counts_path == "/xrmmap/mcasum/counts"
    assert XRMMapH5Calibration().energy_scale is None


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
    """Models module must not depend on hyperspy or h5py.

    We snapshot ``sys.modules`` before re-importing
    ``axiomm.io.converters.models`` and check that the *delta* contains no
    h5py / hyperspy modules. Snapshotting (rather than nuking those
    backends from ``sys.modules``) matters because h5py's C extension
    cannot be safely re-initialised inside the same Python process —
    deleting and re-importing it crashes h5py's conversion-function
    registration. See spec §24.1.
    """
    for mod_name in list(sys.modules):
        if mod_name == "axiomm.io.converters.models":
            del sys.modules[mod_name]

    before = set(sys.modules)
    import axiomm.io.converters.models  # noqa: F401

    new_modules = set(sys.modules) - before
    forbidden = sorted(
        m for m in new_modules if m.startswith(("hyperspy", "h5py"))
    )
    assert not forbidden, (
        f"importing axiomm.io.converters.models triggered backend imports: {forbidden!r}"
    )
