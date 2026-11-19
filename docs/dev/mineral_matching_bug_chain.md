# Mineral phase mapping — bug chain, root causes, and fix plan

**Status:** diagnosed (evidence below), fix designed. 2026-11.
**Trigger:** the first real run (A21_066 map1_002, 13.55 keV) labelled the matrix
and glass as Fe-Ti oxides (Pseudobrookite / Rutile) and **nothing abstained** —
all 7 clusters came back `reportable_estimate` with a named mineral.

This is not one bug. It is a chain; each link was verified against the real run.
The defensible goal is **not** to force a confident name onto every cluster — the
data + current method support confident single-phase identification only for some
phases. It is to fix the clear bug, make the matcher **abstain honestly**, and
document the physical limits as the scientific boundary.

## The chain

### Cause 1 (root, a real bug) — Ba Lα / Ti Kα line overlap → spurious BaO
- Ba Lα = **4.466 keV**, Ti Kα = **4.508 keV** — 0.042 keV apart; a typical SDD
  resolution is ~0.13 keV, so the two lines are **fully blended**.
- AXIOMM measures each element line's net intensity in its own window
  (`NetIntensityMeasurer`), independently — so the single ~4.5 keV **Ti peak is
  double-counted as "Ba."**
- **Evidence:** BaO was **20–55 wt% in every cluster** (impossible); BaO tracked
  TiO₂ exactly (cluster 1: BaO 55 / TiO₂ 38 — the same peak); Ba even appeared in
  the Ba-free apatite cluster.
- **Verified fix:** removing Ba from quantification turned cluster 1 into
  TiO₂ 85.8 % → **Rutile score 1.00**, and cleaned every composition.

### Cause 2 (physical limitation, documented, not a code bug) — uncorrected absorption + single energy
- The theoretical k-factors omit absorption / self-absorption (see
  `quantification_validation_freeze.md`): the result is an *uncorrected* estimate.
- At a single 13.55 keV excitation, low-Z lines (P 2.0, Si 1.74, Al, Na, Mg) are
  weakly excited **and** strongly absorbed relative to Fe/Ti/Ca → **under-measured**.
- **Effect:** compositions are biased toward Fe/Ti/K. Even the (spatially correct)
  apatite cluster reads Fe/K/Ti-heavy after Ba removal (CaO 34, FeO 24, K₂O 14,
  TiO₂ 12, SiO₂ 9, P₂O₅ 5.6) — P and Si are suppressed.
- Proper fix is matrix (ZAF / absorption) correction and/or **dual-energy fusion**
  (bring in the companion 2.9 keV map for light elements). Both are future work;
  until then, high-excitation light-element-poor readings are a known bias.

### Cause 3 (matcher flaw) — rewards partial explanation (asymmetric coverage)
- The cosine is scored over the **shared** elements; the eligibility gate
  (`min_composition_coverage ≥ 0.5`) checks the **candidate** is explained, **not**
  that the candidate explains the **observation**.
- So a two-element oxide (Pseudobrookite = Fe,Ti) scores high against a K-Fe-Ti-Si
  cluster using only Fe+Ti (dims = 2, composition_coverage = 1.00) — **ignoring the
  cluster's K (26 %) and Si (12 %)**, elements the oxide cannot contain. A phase
  with 26 % K₂O cannot be pseudobrookite.

### Cause 4 (matcher default) — no confidence floor
- `MatchConfig.min_score` defaults to **0.0** → the best candidate is always
  eligible → `UNRESOLVED` only fires when a cluster is out-of-coverage → the matcher
  **never abstains on weak or ambiguous matches**.

## Fix plan (defensible, layered, all thresholds configurable)

### Layer A — line-overlap detection + handling (fixes Cause 1)
- Add a detector energy-resolution value (`line_resolution_kev`, default ~0.13;
  set per instrument).
- Detect element-line pairs within the resolution; emit a **`line_overlap`
  warning** naming the pair + energies.
- Policy: AXIOMM does **not** independently quantify overlapping lines and does
  **not** guess which element is real. Default — exclude overlap-affected elements
  from the quantitative composition and from matching, recording it in a
  diagnostic; the domain expert resolves by removing the interfering element from
  the element set (for this suite: **exclude Ba** — trace; the 4.5 keV peak is Ti).
- Add a clean **exclude seam** for quant elements at the pipeline level.

### Layer B — honest matching (fixes Causes 3 & 4)
- Add **`observation_coverage`**: the fraction of the observed cation proportions
  the candidate's elements explain (the symmetric counterpart of
  `composition_coverage`). New gate `min_observation_coverage`.
- Add a phase-map **`min_score` floor** so weak best-matches render `unresolved`.
- Add an **ambiguity** check: abstain (or flag) when the top-2 scores are within a
  small margin.
- Thresholds tuned on the real run so strong matches (Rutile, Apatite, Phlogopite,
  Clinopyroxene) survive and mixed / absorption-biased clusters abstain. The phase
  map becomes **"named where confident, unresolved elsewhere."**

### Layer C — documentation
- This record.
- User docs + report caveats: the phase map names only confident single-phase
  matches; `unresolved` = mixed / weak / ambiguous / out-of-reference; the
  quantification is uncorrected theoretical (absorption omitted), so at high
  excitation light elements are under-measured.
- Record per-run decisions (Ba exclusion, detector resolution) in the
  `acquisition_record_template.md`.

## Scientific decisions (defensible defaults; configurable)
- `line_resolution_kev = 0.13` keV (typical SDD FWHM near Mn Kα).
- Ba excluded for the West Kimberley / Basanite / Gaussie suite (trace; Ti overlap).
- `min_observation_coverage`, `min_score`, ambiguity margin — set from the real run
  so strong matches survive and weak abstain; recorded here once chosen.

## What this does and does not claim
Even fully fixed, this is still **candidate ranking, not validated identification**,
and the quantification is **uncorrected theoretical**. The fix makes AXIOMM **honest**
(abstaining where it cannot confidently identify a single phase) and removes a real
artifact (Ba/Ti). Confident, validated phase/composition maps still require matrix
correction, dual-energy fusion, and standards — tracked as future work.
