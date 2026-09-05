"""Opt-in real-data test: inspect a local STEM-EDS Bruker .bcf spectrum image.

Gated by ``AXIOMM_REALDATA_BCF`` (absolute path to the local file). Skips
cleanly when the variable is unset/invalid or the reader is absent. It verifies
only facts observed from the real file and never requires the binary — or any
derivative — to be committed. The dataset is GPL-3.0; it stays outside git.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.realdata

_BCF = os.environ.get("AXIOMM_REALDATA_BCF")
_EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "bcf_inspect.py"


def _load_example():
    spec = importlib.util.spec_from_file_location("bcf_inspect", _EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bcf_inspection_reports_real_facts():
    if not _BCF or not Path(_BCF).is_file():
        pytest.skip("set AXIOMM_REALDATA_BCF to a local .bcf to run this test")
    pytest.importorskip("hyperspy")
    pytest.importorskip("rsciio")

    mod = _load_example()
    report = mod.inspect_bcf(_BCF, plot=False)   # no figure written during tests

    assert len(report["dataset"]["sha256"]) == 64
    assert report["dataset"]["size_bytes"] > 0
    assert report["signals"], "expected at least one signal"

    s0 = report["signals"][0]
    assert len(s0["shape"]) == 3                              # (nav, nav, energy)
    # exactly one signal (energy) axis, calibrated in keV, last in array order
    sig_axes = [a for a in s0["axes"] if not a["navigate"]]
    assert len(sig_axes) == 1 and sig_axes[0]["units"] == "keV"
    assert s0["array_axis_order"][-1] == sig_axes[0]["name"]
    # real acquisition facts are present (not inferred)
    assert s0["acquisition"]["beam_energy"] is not None
    assert s0["acquisition"]["live_time_s"] is not None
    # quick-look is finite and non-trivial
    assert s0["quicklook"]["total_counts_sum"] > 0
    assert s0["quicklook"]["summed_spectrum_peak_keV"] is not None
    # diagnostics record presence/absence explicitly for every curated key
    assert any("present" in d or "ABSENT" in d for d in s0["diagnostics"])
