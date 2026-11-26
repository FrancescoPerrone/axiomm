# v0.1 validation pilot — summary

AXIOMM commit `59c481c3182f28e45eb5a24a89b7313870f994c3` · Python 3.11.2 · manifest `1e2a649527ea`
Comparators: PyMca5 5.9.7, HyperSpy 2.5.0, eXSpy 0.3.2.

## C1 — net line intensities vs synthetic truth
| stratum | injected area | mean signed rel err | 95% CI | mean |err| | RMSE |
|---|---|---|---|---|---|
| S_5k | 5000 | +0.0078% | [-0.1063%, +0.1220%] | 1.1472% | 1.4228% |
| S_20k | 20000 | -0.0066% | [-0.0630%, +0.0497%] | 0.5676% | 0.7021% |
| S_100k | 100000 | -0.0132% | [-0.0393%, +0.0129%] | 0.2594% | 0.3255% |

**Proposed C1 margin:** **5%** (all high-signal strata CIs within ±5%)

## C2 — overlaps / missing / zero
- clear_peak: net=19979.518 → PASS
- zero_window: net=0.000 → PASS
- out_of_range: net=0.000 → PASS
- noisy blanks: 0/500 false detections (rate 0.0000, policy net≥50) → PASS

**C2: PASS**

## C3 — Cliff–Lorimer arithmetic (numerical equivalence)
- analytic fixture I=[100.0, 50.0], k=[2.0, 1.0] → expected ratio 4.0; oracle 4.000000 (PASS), eXSpy 4.000000 (PASS)
- rtol=1e-10, atol=1e-12
- Ca/Si: AXIOMM 0.06780020376 vs oracle (PASS) vs eXSpy (PASS)
- Fe/Si: AXIOMM 0.01426719385 vs oracle (PASS) vs eXSpy (PASS)
- Mg/Si: AXIOMM 0.442975355 vs oracle (PASS) vs eXSpy (PASS)
- Al/Si: AXIOMM 0.4015118933 vs oracle (PASS) vs eXSpy (PASS)

**C3: PASS**

## C6 — reproducibility
- rerun identical: True; save/load clusters: True; phase map: True → **PASS**

## C7 — runtime & memory (descriptive)
- wall 0.0526 s, peak RSS 233.6 MiB (2 clusters)

## C8 — provenance
- top-level complete: True; config complete: True; round-trip faithful: True → **PASS**

## Evidence-backed release blockers
- **None** among the ungated comparisons.

C4/C5 remain gated on Tier-A independent references. Held-out confirmatory set NOT opened. Returned for sign-off before the held-out run.
