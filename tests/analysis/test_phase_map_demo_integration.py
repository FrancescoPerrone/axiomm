"""The synthetic phase-map demo as a deterministic round-trip integration test.

This is the *synthetic self-consistency* demo (not empirical validation): it
generates observations from the same references the pipeline consumes, so
recovering the input phases checks that the stages fit together, not accuracy.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_DEMO = Path(__file__).resolve().parents[2] / "examples" / "phase_map_demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("phase_map_demo", _DEMO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_deterministic_and_round_trips(tmp_path):
    pytest.importorskip("sklearn")     # PCA + GMM backends
    pytest.importorskip("xraylib")     # theoretical k-factors
    from axiomm.analysis.mineralogy.match import read_match, write_match

    mod = _load_demo()
    r1 = mod.run(save=False, verbose=False)
    r2 = mod.run(save=False, verbose=False)
    assert r1["best"] == r2["best"]                     # deterministic under fixed seed

    # end-to-end match-result round-trip through the strict adapter
    m = r1["matches"][0]
    write_match(m, tmp_path, "demo")
    back = read_match(tmp_path, "demo")
    assert back.cluster_id == m.cluster_id
    assert [c.name for c in back.candidates] == [c.name for c in m.candidates]

    # self-consistency (NOT an accuracy claim): the injected phases come back
    recovered = set(r1["best"].values())
    assert {"Forsterite", "Fayalite", "Apatite"} <= recovered
