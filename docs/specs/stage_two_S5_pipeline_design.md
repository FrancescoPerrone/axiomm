# AXIOMM Stage Two · S5 — the pipeline (the front door)

> **Status:** design for build (2026-09-06). Homed in `axiomm.pipeline`, exposed
> as `from axiomm import Pipeline`. Composes S1–S3d. This is the piece meant to
> become AXIOMM's **first access point** for users — most of whom are not
> programmers — so the guiding rule is: it must read almost like plain English
> and be easy to remember. A proper UX will later sit on top of exactly this
> object.

## 1. Goal, in one sentence

Give someone a data file, run the whole analysis for them in the right order, and
hand back one result they can look at, plot, and save:

```python
from axiomm import Pipeline

result = Pipeline().run("map.bcf")
result.clusters          # what it grouped the map into
result.phase_map         # per-pixel mineral labels (or "unresolved")
result.summary()         # a short plain-text account of the run
result.save("out/")      # the whole result, reproducibly
```

## 2. What it is / is not

**Is:** one object that orchestrates the existing, trusted tools
(decomposition → clustering → cluster spectra → peaks → quantification →
reliability → mineral matching) with sensible defaults, and returns one bundle
carrying every step's output plus provenance and diagnostics.

**Is not:** a GUI (that comes after); any new science (pure orchestration); a
cage (every underlying tool is still usable and swappable on its own).

## 3. Plain-English surface (the part that matters)

- `Pipeline(...)` — construct with defaults; a few plainly-named settings.
- `.run(source)` — ``source`` is a **file path** (read via the converter's
  auto-detected reader, so `.h5` and `.bcf` both work) *or* an already-loaded
  `AxiommSignalPayload`.
- `PipelineResult` attributes read as nouns: `.clusters`, `.cluster_means`,
  `.minerals` (per-cluster ranked matches), `.phase_map`, `.diagnostics`,
  `.provenance`, plus the raw stage objects (`.decomposition`, `.clustering`,
  `.quantification`, `.reliability`) for anyone who wants them.
- `.best_match(cluster_id)` / `.summary()` / `.save(dir)` and a friendly
  `repr()` so printing a result explains itself.
- Settings names avoid jargon where possible: `groups` (number of clusters),
  `detail` (components), `reference`, `beam_energy_kev`, `seed`.

## 4. Honest, graceful behaviour

The pipeline does **as much as the data and settings support**, and says what it
skipped — it never forces a result:

- Decomposition → clustering → cluster spectra always run.
- Peaks → quantification → reliability → matching run only when a **reference**
  and a **beam energy** are available (no beamline value is ever baked in). If
  not, those steps are skipped with a clear diagnostic, and `.phase_map` /
  `.minerals` are `None` — the clusters are still returned.
- Where the observed chemistry is outside the reference, matching **abstains**
  (per S3d), and `.phase_map` marks those clusters `"unresolved"`.
- Reproducible by default: one `seed` threads to PCA and GMM.
- Every step's diagnostics and provenance are aggregated onto the result; the
  result records the exact config so the run can be repeated.

## 5. Defaults that "just work"

`Pipeline()` with no arguments runs decomposition + clustering + cluster spectra
on any readable map. To get minerals, the two honest requirements are a
`reference` (default `minerals_default_v2`, already basis-audited) and a
`beam_energy_kev` (must be supplied — instrument-specific). The measured element
set and line energies default from the reference, restricted to the spectrum's
energy range.

## 6. Save / load

`result.save(dir)` writes a self-describing directory: a `pipeline.json` manifest
(config, provenance, aggregated diagnostics, and a per-cluster summary), the
`label_map`/`phase_map` arrays, and — reusing the existing strict, versioned
adapters — the cluster means and the per-cluster quantification, reliability, and
match payloads. `load_result(dir)` reconstructs the result from that directory.
No new serialization format is invented; the pipeline manifest ties the existing
ones together.

## 7. Module layout

```
src/axiomm/pipeline/
  __init__.py   # Pipeline, PipelineConfig, PipelineResult, load_result
  config.py     # PipelineConfig (validated, plain-named settings)
  result.py     # PipelineResult + save / load
  core.py       # Pipeline.run — the orchestration
```
Headless core; `from axiomm import Pipeline` stays import-light (heavy backends
load lazily inside `.run()`). Reading a file at the edge uses the converter's
readers, so HyperSpy/h5py remain optional.

## 8. Acceptance criteria

1. `from axiomm import Pipeline` works without importing sklearn/xraylib/hyperspy.
2. `Pipeline().run(payload)` on a payload runs decomposition → clustering →
   cluster spectra and returns a populated `PipelineResult`; `.phase_map` /
   `.minerals` are `None` with a clear diagnostic when no reference+beam energy.
3. With a reference + `beam_energy_kev`, the full chain runs and `.phase_map`
   gives per-pixel mineral labels; out-of-reference chemistry yields
   `"unresolved"`, never a forced label.
4. `.run("file.bcf")` and `.run("file.h5")` read via the converter's auto reader.
5. Deterministic under a fixed `seed` (same label map on re-run).
6. `save` → `load_result` round-trips the manifest, arrays, and per-cluster
   payloads through the existing strict adapters.
7. Config is validated with plain, domain-specific errors; provenance records
   the exact settings and every stage's provenance.
8. Reads like plain English: the one-liner and the result attributes need no
   knowledge of the underlying tool names.

## 9. Pluggable stages (refinement)

The pipeline reflects the real analysis work: each stage is a decision the user
makes, not a fixed recipe. The reader stage is already pluggable (auto-detected
via the converter registry); this refinement makes **dimensional reduction** and
**clustering** selectable too, behind one uniform, plain convention — while the
one-line default stays exactly as easy.

`PipelineConfig` gains two fields beside the simple `components` / `groups` knobs:

- `reduction` — the dimensional-reduction backend
- `clustering` — the clustering backend

Each accepts **four forms**:

1. `None` (default) — today's seeded PCA / GMM. `Pipeline().run(map)` is unchanged.
2. a **name** (`"pca"`, `"gmm"`) — resolved through the S1/S2 backend registries,
   built with the simple knobs (`components` / `groups` / `seed`).
3. an **instance** (`SklearnPCADecomposer(...)`, `GMMClusterer(...)`) — used as-is;
   the user owns its settings. An `info` diagnostic (`stage_instance_supplied`)
   records that the pipeline's generic knobs don't govern that stage.
4. a **dict** `{"name": ..., **options}` — name resolved via the registry,
   remaining keys passed to the backend constructor. This form is serialisable —
   the shape a saved-pipeline file or a future UI emits.

A small internal resolver (`_resolve_reduction` / `_resolve_clustering`) absorbs
the S1-vs-S2 registry difference (name→instance vs name→class) so the user-facing
convention is uniform. Precedence is explicit: `seed` threads to the default/name
paths (as `random_state` where the backend accepts it); `components` always
applies to reduction; `groups` sets `n_clusters` on the name/dict paths; a
hand-built instance carries its own params. Provenance records the chosen backend
name for each stage. Unknown names raise `BackendNotFoundError`; a spec that is
not name/instance/dict raises `PayloadValidationError` at config time.

Scope: reduction + clustering only. Quantification, reliability, and matching are
physics-bound and keep their existing typed configs; mapping/reporting is S4.

**Forward-compatible by design:** this builds the socket; when S6 registers new
backends (UMAP, HDBSCAN, …) under their names, they become selectable through the
exact same `reduction=` / `clustering=` fields with no pipeline change. For GMM,
the dict form reaches constructor arguments (`n_clusters`); deep GMM tuning lives
on `GMMConfig`, so that stays the instance path.

## 10. Deferred (not in this build)

A GUI/notebook UX on top; streaming/lazy execution for very large maps; a
full round-trip of the decomposition object (the manifest currently records it
by provenance + shapes); a class-resolving variant of the decomposition registry
(the pipeline currently derives the class from the registry's instance). These do
not change the meaning of a stored result.
