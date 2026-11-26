# Validation environment & comparator record

Pinned for the v0.1 external-validation pilot (recorded before results; `run_pilot.py`
also captures the live versions into `results/pilot_results.json` for cross-check).

| component | version | role |
|---|---|---|
| Python | 3.11.2 | runtime |
| AXIOMM | current frozen branch (commit recorded in results) | system under test |
| PyMca5 | 5.9.7 | primary XRF spectrum-fitting comparator (C1 secondary differential) |
| HyperSpy | 2.5.0 | EDS infrastructure |
| eXSpy | 0.3.2 | independent Cliff–Lorimer implementation (C3): `exspy._misc.eds.utils.quantification_cliff_lorimer` |
| PyXRF | (not installed) | optional secondary — added only if materially distinct |
| NumPy | 1.26.4 | — |
| SciPy | 1.10.1 | CI / stats |
| xraylib | 4.3.0 | k-factor physics |
| fisx | 1.2.0 | (PyMca dependency) |

**eXSpy Cliff–Lorimer convention (verified).** `quantification_cliff_lorimer(intensities,
kfactors)` returns weight fractions with `C_i ∝ k_i · I_i` (normalised). Confirmed by the
analytic fixture `I=[100,50], k=[2,1] → [0.8,0.2]`, ratio `4.0` — the same convention AXIOMM
uses, so the same k-factor numbers feed AXIOMM, the hand oracle and eXSpy in C3.

**Build:** a Python ≥3.10 environment with `axiomm` importable (`pip install -e .` or
`PYTHONPATH=src`), plus `pip install "PyMca5==5.9.7" "hyperspy==2.5.0" "exspy==0.3.2"`
(and a recent `typing_extensions`). The AXIOMM `src/` is **not** modified by the harness.
