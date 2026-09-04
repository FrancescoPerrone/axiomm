# AXIOMM Stage Two · S3d — exploratory mineral matching design (rev. 2)

> **Status:** **IMPLEMENTED** (2026-09-04) in `axiomm.analysis.mineralogy.match`,
> after the source-basis audit closed. Fourth S3 chunk; consumes S3c
> quantification + reliability and the S3a mineralogy reference. The companion
> test module `tests/analysis/test_mineralogy_match_semantics.py` is now live
> (no longer skipped) and is the acceptance suite.
>
> **Implementation notes vs. this design.** (1) The source audit found the V1
> measured/standard endmembers are already *molar cation proportions* (derived
> from oxide wt%), so V2 tags them `atom_counts` (which normalises them
> correctly) and records the oxide-source provenance; the `oxide_mass_fraction`
> and `element_mass_fraction` converters are implemented and tested for clusters
> and future references. (2) `min_informative_dims` defaults to **2** (a
> one-element overlap is insufficient) rather than 3, so genuinely two-cation
> minerals (e.g. forsterite) remain matchable. (3) The matcher **rejects** a
> basis-unaudited reference (V1) outright rather than offering an opt-in.
>
> **Rev. 2** resolved the compositional-basis blocker, redefined the comparison
> basis honestly, added evidence-support controls, made reliability gating
> explicit, and defined a metric contract. See §3–§7.

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
candidate endmembers** with a similarity score and per-candidate evidence
diagnostics.

**In scope:** convert the cluster and every reference endmember to one common
comparison basis; score their similarity; rank; expose scores and evidence
support; propagate identity, reliability, provenance.

**Out of scope (must not be implied by any output):** a single validated mineral
identification; any quantitative-accuracy claim (standards validation stays
mandatory, §12); treating the reliability `count_floor` as an LOD/LOQ;
recomputing quantification or reliability.

## 2. Inputs & data contract

Per cluster: a `QuantResult` (`wt_percent_element` = cation-region **mass**
fractions, plus retained peak facts, `cluster_id`, provenance, diagnostics); a
`ReliabilityReport` (`cluster_status`, `element_status`, `cluster_id`); and a
`MineralogyReference` (`elements` with `atomic_weight`; `minerals`;
`structural_exclude`; `family_display`; library `name`/`version`).

**Reliability is part of the contract, not optional — see §6.** Identity is
checked: a supplied report's `cluster_id` must equal the `QuantResult`'s, and the
batch API aligns one-to-one by `cluster_id` (reusing the S3c bijection rule).

## 3. Compositional basis — the core correctness fix (blocker)

**The library currently mixes compositional bases.** `MineralEndmember.composition`
holds *stoichiometric atom counts* for ideal minerals, but measured phases and
glass standards are expressed as *elemental mass percentages*. Today
`MineralogyReference.build_vectors_with_diagnostics` sum-normalises **both** as if
they were counts — which is correct for atom-count endmembers and **wrong** for
mass-fraction endmembers. A measured cluster's `wt_percent_element` is a third
thing again (mass fractions). None of these may be compared until they are in one
basis.

**Fix: declare each reference's basis, and convert everything to one common
comparison basis (molar/element proportions) before scoring.**

- Add an explicit `basis` to `MineralEndmember`:
  `basis: Literal["atom_counts", "mass_fraction"]` (an S3a model addition made at
  implementation time; **not** in this design-only change).
- A basis-aware conversion produces, for every endmember *and* for the cluster,
  a vector of **molar/element proportions** on the included basis (§4):
  - `atom_counts` → proportions are the counts themselves, normalised over the
    included elements (already molar).
  - `mass_fraction` (and the cluster's `wt_percent_element`) → divide each
    element's mass fraction by its atomic weight, then normalise:
    `n_i = (w_i / A_i) / Σ_j (w_j / A_j)`.
- Because the conversion is identical for a mass-fraction endmember and for the
  cluster, a mass-fraction *standard* of a given phase and the atom-count *ideal*
  of the same phase converge to the same molar vector — a direct test of the fix.

`build_vectors_with_diagnostics` is basis-naive and must **not** be used as-is for
mass-fraction endmembers; the S3d compose step performs the basis-aware
conversion (and, at implementation, `build_vectors_with_diagnostics` is either
extended to honour `basis` or superseded). Atomic weights must be finite and
positive (already enforced by `MineralogyReference.validate`); a missing atomic
weight for an element being converted is an error, not a silent drop.

## 4. The included / excluded elemental basis (not "cation-only")

The comparison is **not strictly cation-only**, because F, S and Cl are retained.
The basis is defined and justified explicitly:

- **Excluded:** `O` and the reference's `structural_exclude` set (in the default
  library, `{O, Br, I}`). `O` is excluded because it is never independently
  measured here — it is added by assumed oxide stoichiometry, and including it
  would let a modelled quantity dominate the similarity. `Br`, `I` are excluded as
  the library's declared non-structural / mobile trace halogens.
- **Included:** every other measured, characteristic-line element — which
  includes the non-cation structural elements **F, S, Cl**. They are retained
  because they are directly measured and structurally diagnostic (F/Cl in
  apatite, S in sulfates/sulfides), so dropping them would discard real
  discriminating information.

The design therefore speaks of **"included structural elements"** and
**"molar/element proportions"**, never "cations". The exclusion set is taken from
the reference (`structural_exclude`) plus any `MatchConfig.exclude`, so it is data-
and config-driven, not hard-coded, and is recorded in provenance.

## 5. Evidence support (sparse overlap must not score as a perfect match)

Cosine similarity on a one- or two-element overlap can read 1.0 while meaning
almost nothing. S3d records evidence support per candidate and refuses to present
under-supported matches as confident:

- `elements_used` — included elements present with usable signal in **both** the
  cluster and the candidate (the dimensions actually scored).
- `coverage` — `|elements_used| / |candidate included elements|`: how much of the
  candidate the observation actually constrains.
- `elements_censored` — cluster elements that are `below_count_floor` (measured
  but not reportable): censored, not zero (§6, §7).
- `elements_unavailable` — candidate elements that were **never measured** (absent
  from the cluster's measured set entirely): missing data, distinct from censored.
- `n_informative_dims` — `|elements_used|`, the count of scored dimensions.
- **`insufficient_evidence` outcome** — when `n_informative_dims <
  config.min_informative_dims` (default: 3), the candidate is **not** presented as
  a scored match: it is either omitted from `candidates` or emitted with a flag
  and no rank-eligible score, plus a diagnostic. This is what stops a sparse
  overlap from producing a misleadingly perfect ranking.

`coverage` may also carry a `min_coverage` floor (config, default off) below which
a candidate is likewise treated as insufficiently supported.

## 6. Reliability gating (required, or explicitly ungated and recorded)

- **A `ReliabilityReport` is required by default.** `match_cluster` expects one;
  its `cluster_id` must match the `QuantResult`.
- **Absence requires an explicit, ungated opt-in that is recorded prominently.**
  Calling without a report raises unless `allow_ungated=True` is passed; when
  ungated, the result sets `reliability_gated = False`, carries a
  `warning`-severity `ungated_match` diagnostic, and records `input_reliability =
  "ungated"` in provenance — so a stored ungated result is unmistakable.
- **`cluster_status == "invalid"` (or an invalid `QuantResult`) raises.**
- **`exploratory_only` is ranked only with an explicit opt-in and a warning.**
  Default: such a cluster returns empty `candidates` plus a warning; with
  `rank_exploratory=True`, candidates are returned still carrying the warning.
- **`reportable_estimate` is still an uncalibrated screening estimate** — every
  result is a candidate/ranking, never an identification.

## 7. Metric contract (direction, scale, thresholding)

Metrics are resolved through a small registry and obey a single contract so
ranking and thresholding are metric-agnostic and the cosine-vs-`min_score`
contradiction cannot recur:

Each metric declares:

- `kind: "similarity" | "distance"` — the natural direction.
- `raw_bounds: (lo, hi)` — the range of the raw score (e.g. cosine similarity on
  non-negative molar vectors is `[0, 1]`).
- `raw(a, b) -> float` — the raw score.
- `rank_score(raw) -> float in [0, 1]` — a **monotonic** map where **1 is the
  best possible match**, regardless of `kind`. For a similarity this is a rescale
  of `raw`; for a distance it is a decreasing map (e.g. `1 / (1 + d)`).

Ranking always orders by `rank_score` descending. `MatchConfig.min_score` is a
threshold **on `rank_score`, in `[0, 1]`** — so it is always in range and always
means "minimum match quality", whatever the metric. Config validation rejects
`min_score` outside `[0, 1]`. (This is what resolves the earlier contradiction:
there is no `min_score = 2.0`, because thresholds live in `[0, 1]`, not in a raw
cosine range.) `MineralCandidate.score` stores `rank_score`; the raw score and
metric name are kept in provenance/diagnostics for traceability.

Default metric: **cosine similarity** on the molar/element vectors (provisional).

## 8. Output payload

`MineralMatchResult` (composition, not inheritance):

- `cluster_id: int | None`.
- `candidates: tuple[MineralCandidate, ...]` — ranked best-first by `rank_score`;
  **may be empty**. No unconditional single-label field.
- `MineralCandidate`: `name`, `family`, `score` (`rank_score` in `[0, 1]`),
  `elements_used`, `coverage`, `elements_censored`, `elements_unavailable`,
  `n_informative_dims`, `outcome` (`"scored" | "insufficient_evidence"`), and a
  short `basis` note.
- `input_reliability: str | None` — the upstream `cluster_status` verbatim, or
  `"ungated"`.
- `reliability_gated: bool`.
- `library_name` / `library_version`.
- `provenance: AnalysisProvenance` and `diagnostics: list[Diagnostic]`.

`best()` returns the top **scored** candidate or `None` — never a fabricated
assignment, and never an `insufficient_evidence` entry.

## 9. Provenance & diagnostics propagation

Each result records: `cluster_id`; upstream `cluster_status` (or `"ungated"`) and
the reliability report's identity; reference-library `name`/`version`; the
k-factor provenance carried on the `QuantResult`; the full `MatchConfig` (metric,
normalization, exclusions, `min_score`, `min_informative_dims`, missing-data
mode); and the basis-conversion note (which elements were converted from which
basis). Upstream diagnostics are carried forward and joined with S3d's own
(censored elements, unavailable elements, insufficient-evidence, exploratory or
ungated warnings, unknown composition elements).

## 10. Missing-data policy (censored vs unavailable)

Unmeasured and `below_count_floor` elements are **censored / uncertain, not
confirmed zeros** — the diluted-K Lisheen cluster is the motivating failure mode.
`MissingDataPolicy` (config, default `exclude`):

- `exclude` (default) — drop a censored/unavailable element from **both** vectors
  before scoring, so it neither confirms nor refutes a candidate; recorded in
  `elements_censored` / `elements_unavailable`.
- `zero` — treat censored elements as 0. This is a naive sensitivity mode only,
  **off by default and emitted with an explicit warning diagnostic** whenever used.
- `penalize` — **deferred** until a formal LOD/LOQ exists (a principled upper
  bound needs a real limit, not the crude count floor).

## 11. Module layout

```
src/axiomm/analysis/mineralogy/match/
  __init__.py    # match_cluster, match_clusters, MatchConfig, MissingDataPolicy,
                 #   MineralMatchResult, MineralCandidate, metric registry, match I/O
  models.py      # MineralMatchResult, MineralCandidate
  config.py      # MatchConfig, MissingDataPolicy (validated dataclasses)
  basis.py       # basis-aware mass/atom-count -> molar/element proportion vectors
  metrics.py     # metric registry + contract (kind, raw_bounds, raw, rank_score)
  match.py       # match_cluster / match_clusters (composition of the above)
  io.py          # versioned JSON adapter (schema_version + kind, strict, validated)
```

Headless core; validated config dataclasses (finite, admissible ranges, integral
thresholds), consistent with the repair-pass conventions. Match I/O follows the
completed persistence rules: `schema_version` + `kind`, strict finiteness, deep
structural + relational validation, validate-before-write.

## 12. Mandatory caveat

Every public S3d docstring and the `docs/user/analysis.md` matcher section state:
**standards validation remains mandatory before any quantitative-accuracy or
validated mineral-identification claim.** S3d output is an exploratory ranking of
an uncalibrated screening estimate.

## 13. Acceptance criteria (mirrored by the semantics tests)

1. **Basis conversion.** A mass-fraction standard and the atom-count ideal of the
   *same* phase convert to the same molar vector and rank each other first;
   comparing raw mass fractions to atom-count vectors is impossible via the public
   API (only converted vectors reach the metric).
2. **Included basis.** F/S/Cl are retained and can be discriminating; O/Br/I are
   excluded; the effective basis is recorded in provenance.
3. **Evidence support.** A one-element overlap yields `insufficient_evidence`
   (not a perfect score); `coverage`, `elements_used`, `elements_censored`,
   `elements_unavailable`, `n_informative_dims` are populated.
4. **Censoring.** `below_count_floor` / unmeasured elements are censored per
   policy; the default `exclude` mode does not zero them; a K-diluted fixture
   still surfaces K-bearing candidates; `zero` mode differs and warns.
5. **Reliability gating.** No report + no opt-in raises; `allow_ungated=True`
   sets `reliability_gated=False` and warns; `invalid` raises; `exploratory_only`
   is empty-with-warning unless opted in.
6. **Metric contract.** `min_score` is validated to `[0, 1]`; ranking is by
   `rank_score` descending; an achievable-but-unmet threshold yields empty
   candidates and `best() is None`; no `min_score = 2.0` is representable.
7. **Identity & provenance.** `cluster_id`, `input_reliability`, reference
   `name`/`version`, and k-factor provenance appear in every result; a
   report/quant `cluster_id` mismatch raises; batch aligns one-to-one.
8. **Output shape.** Ranked list with scores; no unconditional single label;
   `best()` returns `None` when nothing qualifies.
9. **Config validation.** `MatchConfig` rejects non-finite / out-of-range
   (`min_score` ∉ `[0,1]`) / non-integral (`min_informative_dims`, `top_k`) values.
10. **Match I/O.** Enforces `schema_version` + `kind`, strict finiteness, deep
    validation, validate-before-write; raises `PayloadSerializationError` on
    malformed files.

## 14. Resolved decisions

- **Metric default:** provisional **cosine** on molar/element vectors.
  Compositional-data alternatives (Aitchison/CLR) are deferred (need a zero-
  handling decision).
- **Missing-data:** ship `exclude` (default) and `zero` (explicitly warned
  sensitivity mode only); **defer `penalize`** until a formal LOD/LOQ exists.
- **Family-level roll-up:** **deferred**; `family` metadata is retained on every
  candidate so a later roll-up needs no data change.
- **Reference basis:** add `MineralEndmember.basis`; convert to molar/element
  proportions before scoring (§3), at implementation time.
