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

### Cause 2 (a property of the DATA / acquisition — not an AXIOMM limit) — single excitation under-excites low-Z
- At a single 13.55 keV excitation, low-Z lines (P 2.0, Si 1.74, Al, Na, Mg) sit far
  above their absorption edges → low fluorescence cross-section → **weakly excited**,
  and what is emitted is more strongly self-absorbed than Fe/Ti/Ca.
- **This is a designed property of the experiment, verified:** the *same sample*
  mapped at **2.9 keV** vs **13.55 keV** has a low-Z/mid-Z count ratio of **29.9 vs
  0.01** — the light elements are ~3000× stronger in the low-energy map. The 2.9 keV
  map was acquired precisely to capture them (dual-energy by design). See
  `melts/axiomm_figures/dual_energy_compare.png`.
- **Effect:** the 13.55 keV map is genuinely light-element-poor, so single-map
  compositions are biased toward Fe/Ti/K; even the (spatially correct) apatite cluster
  reads Fe/K/Ti-heavy after Ba removal (CaO 34, FeO 24, K₂O 14, TiO₂ 12, SiO₂ 9,
  P₂O₅ 5.6).
- **This is not AXIOMM being bad at light elements** — AXIOMM correctly reports what
  the 13.55 keV data contains. The scientific-software obligation is that AXIOMM
  **detect and report** the condition (an excitation-coverage diagnostic: "elements
  below ~X keV are weakly excited at this beam energy; composition under-represents
  them; use the complementary low-energy map"), and abstain rather than over-claim.
- The path to a *complete* composition for this experiment is **dual-energy fusion**
  (combine the 2.9 + 13.55 keV maps); matrix (ZAF) correction and standards further
  validate it. These get *better science from the data*, they do not fix an AXIOMM
  flaw. To be reported to Isra and verified scientifically.

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

## Design principles (these govern every fix)

1. **General, not dataset-specific.** The fixes must produce **correct labels when
   the data supports them** and abstain only when it does not. Nothing is tuned to
   "always abstain on A21_066." Regression guard: the synthetic self-consistency demo
   (clean, well-measured phases) must still name its phases correctly after the fix —
   if it starts abstaining, the gates are too strict.
2. **AXIOMM is the honest instrument, never the limit.** A limitation lives in the
   *data / acquisition* (a line overlap unresolvable at this resolution; light
   elements under-excited at this beam energy; a mixed cluster; out-of-reference
   chemistry). AXIOMM's job is to **detect and report** that condition (diagnostics)
   and abstain — not to silently corrupt the result, and not to be blamed for the
   data. Every "limit" we document is a property of the data, surfaced by an AXIOMM
   diagnostic.
3. **Everything configurable.** Detector resolution, exclusions, and all match
   thresholds are parameters with defensible defaults, overridable per run and
   recorded in the acquisition record.

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

### Layer C — AXIOMM reports the data's limits (diagnostics first, docs second)
- **Excitation-coverage diagnostic:** when elements are quantified whose lines are
  weakly excited at the beam energy (line energy far above the edge / low cross-section
  at `excitation_kev`), emit a diagnostic naming them — so a single-energy map's
  light-element under-representation is a **reported data property**, not a silent bias.
- The **`line_overlap`** diagnostic (Layer A) and the **`unresolved`** labels
  (Layer B) are AXIOMM honestly reporting what the data supports.
- Docs then describe these as **data / acquisition** properties and the scientific
  remedies (dual-energy fusion, standards, matrix correction) — framed as getting more
  from the data, never as an AXIOMM shortcoming.
- Record per-run decisions (Ba exclusion, detector resolution, dual-energy pairing) in
  `acquisition_record_template.md`.

## Scientific decisions (defensible defaults; configurable) — FINAL
- `line_resolution_kev = 0.13` keV (typical SDD FWHM near Mn Kα). [Layer A, shipped]
- `exclude_elements = {"Ba"}` for the West Kimberley / Basanite / Gaussie suite
  (trace; the 4.5 keV peak is Ti). Recorded per run in the acquisition record.
- `min_observation_coverage = 0.6` (a single-phase ID must account for ≥60 % of the
  observed cations). [Layer B, shipped]. `min_score` left at 0.0 (ranking floor stays
  user-configurable); add a floor to additionally abstain the weakest labels.
- Chosen from the real A21_066 sweep: these recover Phlogopite + Clinopyroxene and
  reject the implausible Fe-Ti-oxide labels, while the synthetic self-consistency demo
  still names its phases (no over-abstention on good data).

## Validation (A21_066, after Layers A+B)
Fixed phase map = **Phlogopite (mica) + Clinopyroxene + Rutile + Amphibole** (a coherent
ultrapotassic-mafic assemblage). Against Isra's annotations: **Phlogopite ✅,
Clinopyroxene ✅** (the two dominant phases); **Apatite not recoverable from the 13.55 keV
map alone** (P suppressed — a data property, Figure 2 of the report). Full write-up with
figures + the dual-energy proof: `melts/axiomm_figures/REPORT_mineral_phase_map_bugfix.md`.

## What this does and does not claim
Even fully fixed, this is still **candidate ranking, not validated identification**,
and the quantification is **uncorrected theoretical**. The fix makes AXIOMM **honest**
(abstaining where it cannot confidently identify a single phase) and removes a real
artifact (Ba/Ti). Confident, validated phase/composition maps still require matrix
correction, dual-energy fusion, and standards — tracked as future work.
