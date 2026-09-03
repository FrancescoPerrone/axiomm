# AXIOMM Stage Two · S3d — exploratory mineral matching design

> **Status:** design for review (2026-09-03). Fourth S3 chunk, homed in
> `axiomm.analysis.mineralogy.match`. Consumes S3c quantification +
> reliability and the S3a mineralogy reference. **This document is the
> contract to review before any matcher code is written; a companion test
> module (`tests/analysis/test_mineralogy_match_semantics.py`) encodes these
> semantics as skipped executable specifications.**

## 0. One-paragraph summary

S3d ranks each quantified cluster against a library of mineral endmembers and
returns **candidate matches with scores and diagnostics** — never a validated
mineral identification. It is explicitly exploratory: the upstream weight
percents are an uncorrected theoretical sensitivity-ratio estimate (S3c), there
is no empirical standards validation, no formal LOD/LOQ, and the heterogeneity
metric is provisional. Every claim S3d makes is constrained by those facts, and
its interface is designed so the provisional pieces can be replaced later
without changing the meaning of stored results.

## 1. Goal & scope

`axiomm.analysis.mineralogy.match` — given a cluster's `QuantResult` (and its
`ReliabilityReport`) plus a `MineralogyReference`, produce a **ranked list of
candidate endmembers** with a similarity score and per-candidate diagnostics.

**In scope**

- Convert a cluster's cation mass fractions to molar/cation proportions and
  score their structural similarity to each endmember's cation-proportion
  vector.
- Rank candidates; expose scores; propagate identity, reliability, provenance.
- A configurable, provenance-recorded similarity metric, normalization,
  element exclusions, and ranking thresholds.

**Out of scope (must not be implied by any output)**

- A single validated mineral identification per cluster.
- Any quantitative-accuracy claim: standards validation remains mandatory
  before that (see §11).
- Treating the reliability `count_floor` as an LOD/LOQ.
- Recomputing quantification or reliability (S3d is an overlay/consumer).

## 2. Inputs & data contract

A match call consumes, per cluster:

- `QuantResult` — `wt_percent_element` (cation **mass** fractions),
  `net_intensities`, retained peak facts, `cluster_id`, `provenance`,
  `diagnostics`.
- `ReliabilityReport` (optional but recommended) — `cluster_status`,
  `element_status`, `cluster_id`, `reasons`.
- `MineralogyReference` — `elements` (`ElementRef`, carrying `atomic_weight`
  and `structural_exclude` membership), `minerals` (`MineralEndmember`,
  `composition` = **stoichiometric cation counts**), `structural_exclude`,
  `family_display`, plus the library's `name` / `version`.

**Identity is checked, not assumed.** If a `ReliabilityReport` is supplied, its
`cluster_id` must equal the `QuantResult.cluster_id`; a mismatch raises
`PayloadValidationError`. A batch API aligns results to reports by `cluster_id`
one-to-one, reusing the S3c bijection rule.

## 3. The mass → molar conversion (core correctness)

**The single most important scientific rule in S3d.** Endmember vectors are
built from stoichiometric cation *counts* (`MineralEndmember.composition` →
`MineralogyReference.build_vectors_with_diagnostics`), i.e. molar/cation
proportions. A `QuantResult` gives cation **mass** fractions. These live in
different spaces and must never be compared directly.

For each measured cation *i* with mass fraction `w_i` and atomic weight `A_i`
(from `ElementRef`), the molar/cation proportion is

```
n_i = (w_i / A_i) / Σ_j (w_j / A_j)
```

over the cations that survive the exclusion + missing-data policy (§4, §5). The
similarity metric (§6) then compares the cluster's `n` vector to each
endmember's normalized cation-proportion vector on a shared element ordering.
Oxygen and the structural-exclude set (`O`, `Br`, `I`, …) are excluded on both
sides so the comparison is cation-basis on cation-basis.

Atomic weights must be finite and positive (already enforced by
`MineralogyReference.validate`); a missing atomic weight for a measured cation
is an error, not a silent drop.

## 4. Missing-data / censored-observation policy (Lisheen K)

Unmeasured elements and elements graded `below_count_floor` are **censored /
uncertain observations, not confirmed zeros.** This matters concretely: diluted
K in the Lisheen glass cluster was a known failure mode — treating its
below-floor K as a hard zero would wrongly reject K-bearing endmembers.

The policy is explicit and configurable (`MissingDataPolicy`), with these
modes, defaulting to the censoring-aware option:

- `exclude` (default) — drop a censored element from **both** the cluster
  vector and each candidate vector before scoring, so a censored element neither
  confirms nor refutes a candidate. Recorded per candidate as a diagnostic.
- `zero` — treat censored elements as 0 (the naive, rejected-by-default
  behaviour), offered only for explicit comparison/benchmarking.
- `penalize` — score censored elements against a configurable upper-bound
  (derived from the element's floor), contributing bounded uncertainty rather
  than a hard zero.

Which elements were censored, and under which mode, is recorded in the result's
diagnostics and provenance. The policy is tested directly against a
K-diluted-cluster fixture.

## 5. Reliability-gating policy

- **Invalid inputs are rejected.** A `QuantResult` that fails validation, or a
  `ReliabilityReport` with `cluster_status == "invalid"`, raises rather than
  being ranked.
- **`exploratory_only` may be ranked only with an explicit warning.** The
  result carries a `warning`-severity diagnostic and a flag; callers must opt in
  (`rank_exploratory=True`, default `False` → such clusters return an empty
  ranking plus the warning, never silent candidates).
- **`reportable_estimate` is still an uncalibrated screening estimate.** Even
  for it, every result is labelled a candidate/ranking, never an identification.

## 6. Similarity, normalization & ranking (configurable, provenance-recorded)

A `MatchConfig` (frozen dataclass, example defaults, caller-settable) holds:

- `metric` — similarity/distance function name, resolved through a small
  registry so alternatives plug in (default: cosine similarity on the
  molar/cation vectors; cityblock/aitchison candidates deferred).
- `normalization` — how vectors are normalized before scoring (default: sum-to-
  one on the cation basis, matching the reference vectors).
- `exclude` — elements excluded from scoring beyond `structural_exclude`.
- `min_score` / `top_k` — ranking thresholds: candidates below `min_score` are
  dropped; at most `top_k` are returned (both configurable, no hidden cutoff).
- `missing_data` — the §4 `MissingDataPolicy`.

Every one of these is copied into the result provenance, so a ranking is
reproducible from its record alone.

## 7. Output payload

`MineralMatchResult` (dataclass, composition not inheritance):

- `cluster_id: int | None` — carried from the `QuantResult`.
- `candidates: tuple[MineralCandidate, ...]` — ranked best-first; **may be
  empty** (no candidate cleared `min_score`, or an exploratory cluster was not
  opted in). There is no unconditional single-label field.
- `MineralCandidate`: `name`, `family`, `score`, `elements_used`
  (`tuple[str, ...]`), `elements_censored` (`tuple[str, ...]`), and a short
  `basis` note.
- `input_reliability: str | None` — the upstream `cluster_status` verbatim.
- `library_name` / `library_version` — reference identity.
- `provenance: AnalysisProvenance` and `diagnostics: list[Diagnostic]`.

A convenience `best()` returns the top candidate **or `None`**, never a
fabricated assignment.

## 8. Provenance & diagnostics propagation

Each result records: `cluster_id`, upstream `cluster_status` and the reliability
report's identity, the reference-library `name`/`version`, the k-factor
provenance carried on the `QuantResult` (values, xraylib version+backend,
physical-model caveat), the `MatchConfig` (metric, normalization, exclusions,
thresholds, missing-data mode), and the mass→molar conversion note. Upstream
diagnostics are carried forward and joined with S3d's own (censored elements,
exploratory warning, dropped candidates, unknown composition elements).

## 9. Extensibility (swap provisional parts without changing stored meaning)

The interface is designed so later, better components replace provisional ones
without altering what a stored `MineralMatchResult` means:

- **Calibrated k-factors** change the numbers inside `QuantResult`, not S3d's
  contract; S3d already reads `wt_percent_element` and provenance generically.
- **Formal per-element LOD/LOQ** replaces the crude `count_floor` as the source
  of the censoring decision: `MissingDataPolicy` consumes an abstract
  "is this element reportable / censored?" signal, so swapping the floor for a
  statistical LOQ needs no payload change.
- **A noise-aware heterogeneity metric** changes how `exploratory_only` is
  decided upstream; S3d only reads the resulting status string.

The stored result's fields and their meanings are fixed by this spec; provisional
inputs feed them through stable seams.

## 10. Module layout

```
src/axiomm/analysis/mineralogy/match/
  __init__.py         # public: match_cluster, match_clusters, MatchConfig,
                      #   MissingDataPolicy, MineralMatchResult, MineralCandidate,
                      #   metric registry, match I/O
  models.py           # MineralMatchResult, MineralCandidate
  config.py           # MatchConfig, MissingDataPolicy (validated dataclasses)
  compose.py          # mass->molar conversion + vector assembly (headless)
  metrics.py          # similarity/distance registry (cosine default)
  match.py            # match_cluster / match_clusters (composition of the above)
  io.py               # versioned JSON adapter (schema_version + kind, strict)
```

Headless core (no UX imports); a metric registry mirrors S3b/S2. All config
dataclasses self-validate (finite, admissible ranges, integral thresholds),
consistent with the repair-pass conventions.

## 11. Mandatory caveat (documented in code and user docs)

Every public S3d docstring and the `docs/user/analysis.md` matcher section state:
**standards validation remains mandatory before any quantitative-accuracy or
validated mineral-identification claim.** S3d output is exploratory ranking of an
uncalibrated screening estimate.

## 12. Acceptance criteria (mirrored by the semantics tests)

1. Mass fractions are converted to molar/cation proportions via atomic weights
   before scoring; a pure-endmember cluster's own vector ranks that endmember
   first (closed-form check on a simple oxide).
2. Comparing raw mass fractions to cation-count vectors is impossible through
   the public API (only the converted vector reaches the metric).
3. `below_count_floor` / unmeasured elements are censored per policy; the
   default `exclude` mode does not zero them; the K-diluted Lisheen-style
   fixture still surfaces K-bearing candidates.
4. `cluster_status == "invalid"` (or an invalid `QuantResult`) raises;
   `exploratory_only` returns empty + warning unless `rank_exploratory=True`.
5. `cluster_id`, upstream `cluster_status`, reference `name`/`version`, and
   k-factor provenance appear in every result.
6. `MatchConfig` (metric, normalization, exclusions, `min_score`, `top_k`,
   missing-data mode) is honoured and recorded in provenance.
7. Output is a ranked list with scores; `best()` returns `None` when nothing
   clears `min_score`; there is no unconditional single-label assignment.
8. A `ReliabilityReport` whose `cluster_id` disagrees with the `QuantResult`
   raises; batch matching aligns one-to-one by `cluster_id`.
9. Match I/O enforces `schema_version` + `kind`, strict finiteness, and deep
   validation, raising `PayloadSerializationError` on malformed files.
10. Config dataclasses reject non-finite / out-of-range / non-integral values.

## 13. Open decisions (for Francesco)

- **Metric default.** Cosine similarity on cation proportions is proposed;
  compositional-data alternatives (Aitchison/CLR distance) are a candidate but
  need a zero-handling decision — deferred.
- **`penalize` missing-data mode.** Whether the upper-bound formula should be
  derived from the crude count floor now, or wait for a real LOQ. Proposed:
  ship `exclude` + `zero`, defer `penalize` until LOQ exists.
- **Layered labels.** The roadmap mentions family→endmember layering; this spec
  ranks endmembers and exposes `family`. Whether S3d also emits a family-level
  roll-up is an open scope question.
```
