# v0.1 validation — pilot summary

AXIOMM commit `bb949b4247e57512203b04dd5b7c259291734175` · Python 3.11.2 · manifest `328ff721cd91`
Comparators: PyMca5 5.9.7, HyperSpy 2.5.0, eXSpy 0.3.2.

## C1 — net line intensities vs synthetic truth
| stratum | area | AXIOMM mean signed | AXIOMM 95% CI | AXIOMM |err| | RMSE |
|---|---|---|---|---|---|
| S_5k | 5000 | +0.0078% | [-0.1063%, +0.1220%] | 1.1472% | 1.4228% |
| S_20k | 20000 | -0.0066% | [-0.0630%, +0.0497%] | 0.5676% | 0.7021% |
| S_100k | 100000 | -0.0132% | [-0.0393%, +0.0129%] | 0.2594% | 0.3255% |

**Proposed C1 margin:** 5% (all high-signal strata CIs within ±5%)

## C2 — overlaps / missing / zero (with observation states)
- clear_peak: net=19979.518, state=`measured_positive` → PASS
- zero_window: net=0.000, state=`measured_zero` → PASS
- unavailable_out_of_range: net=0.000, state=`not_measured` → PASS
- unresolved_overlap: unresolved pair flagged=True, resolved pair not flagged=True (policy 0.13 keV) → PASS
- noisy blanks: 0/500 false detections (net≥50) → PASS

**C2: PASS**

## C3 — Cliff–Lorimer arithmetic (numerical equivalence)
- analytic fixture → expected 4.0; oracle 4.000000 (PASS), eXSpy 4.000000 (PASS); rtol=1e-10, atol=1e-12
- Ca/Si: AXIOMM vs oracle PASS, vs eXSpy PASS
- Fe/Si: AXIOMM vs oracle PASS, vs eXSpy PASS
- Mg/Si: AXIOMM vs oracle PASS, vs eXSpy PASS
- Al/Si: AXIOMM vs oracle PASS, vs eXSpy PASS

**C3: PASS**

## C6 — reproducibility → **PASS** (rerun True, save/load True)
## C7 — runtime 0.0674 s, peak RSS 233.9 MiB (descriptive)
## C8 — provenance → **PASS** (round-trip faithful True)

## Evidence-backed P0/P1 findings
- **None** among the ungated comparisons.

## Outstanding release gates
- C4 (map-level spatial) and confirmatory C5 (false-discovery/abstention) remain gated on Tier-A independent references (imaging/EPMA). The freeze and P0/P1 stop rule remain in force.
