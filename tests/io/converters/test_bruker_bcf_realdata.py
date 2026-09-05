"""Opt-in real-data test: BrukerBCFReader + AXIOMM pipeline on a local .bcf.

Gated by ``AXIOMM_REALDATA_BCF``. Skips cleanly when unset/invalid or when the
edge reader / analysis backends are absent. Verifies facts from the real file
and pipeline run; never requires the binary to be committed.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.realdata

_BCF = os.environ.get("AXIOMM_REALDATA_BCF")
_EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "bcf_pipeline.py"


def _load_pipeline_example():
    spec = importlib.util.spec_from_file_location("bcf_pipeline", _EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _skip_guard():
    if not _BCF or not Path(_BCF).is_file():
        pytest.skip("set AXIOMM_REALDATA_BCF to a local .bcf to run this test")
    pytest.importorskip("hyperspy")
    pytest.importorskip("sklearn")


def test_reader_builds_payload_from_real_bcf():
    _skip_guard()
    from axiomm.io.converters.readers.bruker_bcf import BrukerBCFReader
    p = BrukerBCFReader().read(_BCF, lazy=False)
    assert np.asarray(p.data).ndim == 3
    sig = [a for a in p.axes if a.role == "signal"]
    assert len(sig) == 1 and sig[0].units == "keV"
    assert sig[0].index_in_array == max(a.index_in_array for a in p.axes)
    assert p.metadata["AXIOMM"]["reader"] == "bruker_bcf"
    assert p.provenance.input_hash and len(p.provenance.input_hash) == 64


def test_pipeline_runs_and_abstains_on_real_bcf(tmp_path):
    _skip_guard()
    mod = _load_pipeline_example()
    r1 = mod.run_pipeline(_BCF, n_clusters=6, seed=0, plot=False, out_dir=tmp_path)

    cl = r1["clustering"]
    assert cl.label_map.ndim == 2
    assert np.asarray(r1["means"].means).shape[0] == len(cl.cluster_ids)
    # peaks measured on real spectra (at least one positive net somewhere)
    nets = [m.net for ps in r1["peaks"] for m in ps.measurements]
    assert any(n > 0 for n in nets)
    # honest scope: quant + matching abstained (out of reference scope)
    assert "NOT RUN" in r1["report"]["quantification_and_matching"]

    # deterministic under a fixed seed
    r2 = mod.run_pipeline(_BCF, n_clusters=6, seed=0, plot=False, out_dir=tmp_path)
    assert np.array_equal(np.asarray(cl.label_map), np.asarray(r2["clustering"].label_map))
