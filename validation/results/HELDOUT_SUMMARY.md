# v0.1 validation — heldout summary

AXIOMM commit `bb949b4247e57512203b04dd5b7c259291734175` · Python 3.11.2 · manifest `328ff721cd91`
Comparators: PyMca5 5.9.7, HyperSpy 2.5.0, eXSpy 0.3.2.

**PyMca adapter verification** (noiseless pilot fixtures): max rel diff 1.57e-13 → VERIFIED

## C1 — net line intensities vs synthetic truth
| stratum | area | AXIOMM mean signed | AXIOMM 95% CI | AXIOMM |err| | RMSE | PyMca mean signed | PyMca 95% CI |
|---|---|---|---|---|---|---|---|
| S_5k | 5000 | -0.0205% | [-0.1347%, +0.0936%] | 1.0984% | 1.4224% | -0.0759% | [-0.1937%, +0.0420%] |
| S_20k | 20000 | +0.0402% | [-0.0183%, +0.0987%] | 0.5831% | 0.7301% | +0.0329% | [-0.0280%, +0.0938%] |
| S_100k | 100000 | -0.0142% | [-0.0406%, +0.0122%] | 0.2656% | 0.3290% | -0.0165% | [-0.0438%, +0.0107%] |

**C1 vs LOCKED margin ±5%: PASS** (every high-signal stratum CI within ±5%)

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
## C7 — runtime 0.0975 s, peak RSS 235.3 MiB (descriptive)
## C8 — provenance → **PASS** (round-trip faithful True)

## Evidence-backed P0/P1 findings
- **None** among the ungated comparisons.

## Outstanding release gates
- C4 (map-level spatial) and confirmatory C5 (false-discovery/abstention) remain gated on Tier-A independent references (imaging/EPMA). The freeze and P0/P1 stop rule remain in force.
