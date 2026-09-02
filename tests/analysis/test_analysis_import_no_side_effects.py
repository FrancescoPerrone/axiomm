"""Importing axiomm.analysis must be silent and side-effect free (S0).

Mirrors the converter's import-guard test. Run in a subprocess so the
observation is clean and never mutates the parent interpreter's
``sys.modules`` (see the Chunk-5 finding in docs/dev/STATE.md).
"""

from __future__ import annotations

import subprocess
import sys


def test_import_is_silent_and_exports_foundations():
    code = (
        "import axiomm.analysis as a;"
        "assert a.AxiommAnalysisError;"
        "assert a.Diagnostic;"
        "assert a.AnalysisResult;"
        "assert a.Registry;"
        "assert a.ReferenceLibrary;"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert proc.stderr == ""
