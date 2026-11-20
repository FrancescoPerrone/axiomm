# Stage two — S7: Phase classification framework (policy over evidence)

**Status:** design, for review. 2026-11.
**Depends on:** S3d mineral matching (evidence), S5 pipeline (host).
**Precedes / independent of:** S8 multi-energy fusion (energy is orthogonal to label policy).

## 1. Why this exists

Auditing AXIOMM on a real sample (A21_066, 13.55 keV) and taking Josh (a
geologist) and Isra (the experimentalist) as live user-cases exposed a
rigidity: **the pipeline forces one specific mineral species onto every
cluster.** On the real map, 5 of 7 clusters are only moderate matches, and 3
are a coin-flip between two names for the *same* mineral family (a mica
standard vs. phlogopite, Δscore ≈ 0.03) — yet all are reported with the same
confidence as the one unambiguous phase (rutile, score ≈ 0.95).

The fix is **not** to hard-code Josh's preference, nor Isra's. What Josh asked
for — *name the species when the evidence is clear, name the family when it
is not, say "unresolved" when it is just noise* — is **one instantiation of a
general decision policy**. Different users will want different cutoffs,
different ambiguity tolerances, family labels on or off. We cannot ship a
version of AXIOMM per experiment. The general capability belongs in AXIOMM;
the particular choice belongs in a named, reproducible configuration.

This stage adds that general capability: a small, pluggable **classification
framework** that turns *evidence* (ranked candidate matches) into a *label*
(species / family / unresolved) under a user-selected, fully-recorded policy —
following AXIOMM's existing registry/stage idiom (S1 decomposers, S2
clusterers, S4 reporters), not a new framework of its own invention.

## 2. Core principle — separate evidence from decision

- **Evidence** (unchanged): S3b peaks → S3c quantification + reliability →
  S3d `match_cluster` → a `MineralMatchResult` carrying ranked `candidates`
  (each with score, family, coverages) and gated `insufficient` candidates.
  **S7 does not touch this layer.** Changing a label policy must never change
  the underlying chemistry, scores, or reliability.
- **Decision** (new): a `ClassificationPolicy` consumes a `MineralMatchResult`
  and the reference, and emits a `ClusterLabel`. The phase map is built from
  `ClusterLabel`s instead of today's `match_result.best().name`.

Today the "decision" is implicit and trivial — `Pipeline._build_phase_map`
does `top = m.best(); name = top.name if top else UNRESOLVED`. S7 makes the
decision an explicit, selectable object.

### Hard scientific boundaries (carried from the bug-chain record)

- **Similarity is not probability.** Cosine on cation proportions is a
  similarity, not a calibrated confidence. Policy cutoffs are *similarity
  thresholds*; a label carries a qualitative `level` + a text `rationale`,
  never a fabricated percentage.
- **Labels only.** A policy re-labels; it never recovers unmeasured elements.
  The 13.55 keV light-element suppression stays a *data* limit (→ S8
  dual-energy), surfaced by diagnostics, not hidden by a label.
- **Reproducible.** The chosen policy and every threshold are recorded in the
  result provenance, so a map is reproducible from its record alone.
- **No over-abstention on good data.** The synthetic self-consistency demo
  (clean, well-measured phases) must still receive *species* labels under the
  default policy — the regression guard that the gates are not too strict.

## 3. Module layout

New subpackage `src/axiomm/analysis/mineralogy/classify/`:

| File | Responsibility |
|---|---|
| `models.py` | `ClusterLabel` result dataclass; `LabelLevel` literal. |
| `policy.py` | `ClassificationPolicy` ABC; `ThresholdPolicy`, `PermissivePolicy`. |
| `classify.py` | `classify_clusters(match_results, reference, policy) -> tuple[ClusterLabel, ...]`. |
| `__init__.py` | `classifiers: Registry`; named presets; public exports. |

One small change outside the subpackage: **store `observation_coverage` on
`MineralCandidate`** (S3d `models.py`). It is already computed in
`_score_candidate` and discarded; the policy and any future inspector need it.
This is additive (a new field), no behaviour change to matching.

## 4. Data model — `ClusterLabel`

```python
LabelLevel = Literal["species", "family", "unresolved"]

@dataclass(frozen=True)
class ClusterLabel:
    cluster_id: int
    level: LabelLevel
    name: str                 # species name, family display name, or "unresolved"
    family: str | None        # the family, when known (set for species & family levels)
    score: float | None       # the top candidate's score (context, never a probability)
    rationale: str            # plain-language why (e.g. "top two within 0.03, both mica")
    contenders: tuple[str, ...]  # candidate names within the ambiguity margin of the top
    policy: str               # policy name that produced this label
```

`UNRESOLVED` (the existing sentinel in `pipeline.result`) remains the phase-map
value for `level == "unresolved"`, so downstream rendering is unchanged.

## 5. Policy abstraction + the two shipped policies

```python
class ClassificationPolicy(ABC):
    name: str
    @abstractmethod
    def classify(self, match_result, reference) -> ClusterLabel: ...
    def params(self) -> dict: ...   # recorded in provenance
```

### 5.1 `ThresholdPolicy` (default) — the general species/family/unresolved rule

Parameters (all validated: finite, `species_floor`/`family_floor` in [0,1],
`family_margin` in [0,1]; defensible defaults, set in §7):

- `species_floor` — minimum top score to emit a **species** label.
- `family_floor` — minimum top score to emit a **family** label (below → unresolved).
- `family_margin` — candidates within this of the top are "near-ties" (contenders).
- `allow_family: bool` — if `False`, only species-or-unresolved (a conservative mode).

Decision (deterministic; `near` = candidates with `score ≥ top.score − family_margin`):

1. No rank-eligible candidates (all gated by the evidence layer) → **unresolved**
   (*"insufficient evidence — all candidates gated"*).
2. `top.score < family_floor` → **unresolved** (*"best match too weak"*).
3. `near == {top}` (clear leader) and `top.score ≥ species_floor` → **species** = `top.name`.
4. `allow_family` and all of `near` share one family → **family** = that family's
   display name (*"top candidates within margin, all <family>"* or *"clear leader,
   score below species floor"*).
5. Otherwise (near spans multiple families, or family disallowed) → **unresolved**
   (*"candidates span families; cannot resolve"* / *"below species floor, family labels off"*).

Worked on A21_066 (species_floor 0.80, family_floor 0.50, family_margin 0.05,
allow_family True): rutile (0.95) → **species**; the three mica clusters
(0.58–0.75, phlogopite a near-tie) → **family "mica"**; the two clinopyroxene
clusters (0.62–0.70, clear leader but below species floor) → **family
"clinopyroxene"**. This is exactly Josh's (a)+(b).

### 5.2 `PermissivePolicy` — preserves today's behaviour

Always returns the top candidate's species (or `unresolved` only when there is
no rank-eligible candidate). This is the current `best()`-based behaviour,
reachable by name so the default change in §6 is never a one-way door.

## 6. Pipeline wiring + the deliberate default change

`PipelineConfig` gains `classification` (name / `{"name": ...}` dict / instance,
default `"threshold"`), resolved through `classifiers` exactly like `reduction`
and `clustering` (`_resolve_*` pattern). `Pipeline._build_phase_map` consumes
`classify_clusters(...)` output. The result carries the `ClusterLabel`s and the
policy params land in provenance.

**This changes the default phase-map behaviour** from "always name the best
species" to the honest species/family/unresolved policy. That is the intended
bug-chain fix, but it is a default change and is called out as such:
`classification="permissive"` restores the prior behaviour, and a regression
test pins that `permissive` reproduces the old labels for a fixed input.

## 7. Defaults, presets, and calibration

Default thresholds are **proposals**, to be confirmed against (i) the synthetic
self-consistency guard (clean phases must still get species labels) and (ii) the
real A21_066 score distribution — not picked blind. Starting proposal:
`species_floor = 0.80`, `family_floor = 0.50`, `family_margin = 0.05`.

Named presets (registered factory configs, the "instantiations" users pick):

| Preset | Settings | A21_066 outcome |
|---|---|---|
| `conservative` | `species_floor≈0.85`, `allow_family=False` | rutile + unresolved elsewhere |
| `family_aware` (Josh's a+b) | the §7 defaults | rutile + mica + clinopyroxene |
| `permissive` | §5.2 | a species name everywhere (today) |

Presets are configuration, not code branches; a user may also pass their own
`ThresholdPolicy(...)`.

## 8. Errors, provenance, generality

- Bad policy config → `PayloadValidationError` (never a generic `Exception`).
- Provenance records `classification_policy` (name) and its `params`.
- Extensibility (CLAUDE.md "default to generality"): a new strategy registers
  in `classifiers` and is selected by name, proven by a dummy-policy test
  mirroring the S6 socket test. The `ClassificationPolicy` ABC is the seam.

## 9. Out of scope (deferred, explicitly)

- **No UX.** Configuration is programmatic now, UX-ready in *shape*. A live
  in-browser "move the slider, watch the map" control is a UX-phase item.
  (Re-classification is cheap — post-matching, no re-quant — so it will be easy
  to wire later.)
- **No new reporting surfaces** beyond having the phase map honour the label
  (showing `level`/`rationale` in the minerals/phase-map sections is a small
  follow-up chunk, not required for the backbone).
- **No calibrated probabilities** (needs a validation study; similarity stays
  similarity).
- **Interactive periodic-table phase viewer** (per-phase elements, per-pixel
  evidence) — a separate later task; see STATE backlog.

## 10. Acceptance criteria

1. `ThresholdPolicy.classify` produces species/family/unresolved per §5.1 on
   hand-built `MineralMatchResult`s (unit tests cover each branch).
2. `PermissivePolicy` reproduces today's best()-based labels for a fixed input
   (regression test).
3. The synthetic self-consistency demo still gets **species** labels under the
   default policy (no over-abstention).
4. A21_066 under the three §7 presets yields the documented maps.
5. `classification` resolves name/dict/instance via `classifiers`; a dummy
   policy registers and is selected (extensibility).
6. Policy name + params are in result provenance; a map is reproducible.
7. Evidence is untouched: the same `MineralMatchResult` yields identical
   scores/coverages regardless of policy.
8. `observation_coverage` is present on every `MineralCandidate`.

## 11. Chunk plan

- **S7.1** — `ClusterLabel` model + `ClassificationPolicy` ABC + `ThresholdPolicy`
  + `PermissivePolicy` + `classifiers` registry + store `observation_coverage`
  on the candidate + unit tests (criteria 1, 2, 8). No pipeline wiring yet.
- **S7.2** — `PipelineConfig.classification` + `_build_phase_map` consuming
  `classify_clusters` + presets + provenance + regression/guard tests
  (criteria 3, 4, 5, 6, 7). Default = `family_aware`/`threshold`, documented.
- **S7.3** (melts layer, not core) — three static A21_066 renders for Josh,
  one per preset, shared coordinates/colours/legend, each with its config +
  an assignment summary (species/family/ambiguous/unresolved counts).
- **S7.4** — run the Isra 5-sample subset under the chosen policy + her
  per-sample restrictions (needs the four other sample files).
- **Later** — reporting surfaces label level/rationale; UX knobs; periodic-table viewer.
