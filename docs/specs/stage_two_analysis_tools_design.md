# AXIOMM Stage Two — Analysis-tool suite: architecture & inventory design

> **Status:** design approved 2026-07-16. This is the
> stage-two counterpart to `converter_tool_spec.md`: it maps the tool
> **inventory** and **architecture** for the analysis suite. It does
> **not** specify any single tool's full signatures yet — each tool gets
> its own spec → plan → implementation cycle, converter-style.

## 1. Context

Stage one delivered the **converter** (`axiomm.io.converters`): XRM-style
HDF5 → analysis-ready signal objects, with a headless pluggable core
(readers / signal builders / writers), a neutral in-memory payload
(`AxiommSignalPayload`), a registry with entry-point plugin discovery, a
calibration-resolution ladder, and a manifest sidecar.

Stage two extracts the **analysis tools** currently living as scripts in
`melt_data_explorer/refactoring/src/` and re-homes them in AXIOMM as
first-class, independently runnable tools that can also be **composed into
a user-defined pipeline**. Conversion concerns are explicitly out of scope
here — `.hspy` loading already belongs to stage one.

Source scripts surveyed (conversion excluded):

- `run_melts_pca_gmm_batch.py` — PCA decomposition + GMM clustering + plots.
- `hybrid_phase_pipeline.py` — atomic-fraction stoichiometry + mineral
  matching + compositional labelling.
- `eds_spectrum_plot_v3.py` — publication EDS spectrum plot (CLI + tkinter GUI).
- `phase_map_report_test_anim.py` — dataset validation + phase-map HTML report.
- `build_melts_report_hub.py` — multi-sample HTML index.

## 2. Locked decisions (this session)

1. **Session outcome:** inventory + architecture map. No tool is built in
   this session.
2. **Inter-tool data contract: hybrid.** Each tool operates on neutral
   **typed payloads** in-memory (the `AxiommSignalPayload` pattern) *and*
   can read/write today's file artifacts (`*_cluster_means*.json`,
   `*_cluster_map*.npy`, `*_metadata*.json`, summary/wt JSON) standalone.
   Pipelines compose payloads; isolated runs use files.
3. **Namespace: domain-grouped under `axiomm.analysis.*`.** Composition
   object at `axiomm.pipeline`. `axiomm.io` stays I/O-only. This resolves
   the reserved-name open decision in `docs/dev/STATE.md`.

## 3. Tool inventory

Four **headline tool domains**, each a subpackage under
`axiomm.analysis.*`, plus shared reference/validation pieces.

### ① `axiomm.analysis.decomposition` — dimensionality reduction
- Swappable backends behind one protocol: **PCA** first (from the batch
  script), **UMAP** pluggable later.
- In: a signal (converter payload / `.hspy`). Out: typed
  `DecompositionResult` (factors, loadings, explained-variance).

### ② `axiomm.analysis.clustering` — unsupervised clustering
- Swappable backends: **GMM** first, **HDBSCAN** later.
- In: loadings. Out: typed `ClusteringResult` (label map, per-cluster
  masks, cluster-mean spectra).

### ③ `axiomm.analysis.mineralogy` — one domain, two runnable units
- `stoichiometry` — peak-integrate cluster-mean spectra → atomic fractions.
- `matching` — mineral-library cosine match + soft wt% assignment +
  rule-based compositional label → hybrid label.
- Shared LOCKED constants (line energies, atomic weights, mineral library)
  become a **swappable reference library**, mirroring the converter's
  calibration-preset pattern.

### ④ `axiomm.analysis.reporting` — one domain, three units
- `spectrum` — the EDS spectrum plot.
- `phase_map` — the phase-map HTML report.
- `hub` — the multi-sample index.
- Report **visual restyling is deferred** to a later joint decision
  (per the stage-two kickoff); this stage only relocates and de-couples.

### Shared (not headline tools)
- `axiomm.analysis.validation` — dataset/schema checks extracted from the
  1234-line report script; an internal utility used by reporting.
- Reference-data tables (elements, line energies, atomic weights, mineral
  library) as **versioned config with provenance**.

### Boundary calls (approved)
- Decomposition and clustering are **separate tools** — required by the
  PCA↔UMAP / GMM↔HDBSCAN swap goal.
- Mineralogy is **one subpackage, two units** (quantify vs identify share
  all constants and are near-always run together).
- Reporting is **one subpackage, three units**; validation is a **shared
  utility**, not a headline tool.

## 4. Internal shape of each tool

Every tool follows the converter's proven skeleton, so the suite is
learnable once. Example (`axiomm.analysis.clustering`):

```
clustering/
  base.py     # runtime-checkable Clusterer protocol (fit/predict → ClusteringResult)
  models.py   # typed ClusteringResult (label_map, masks, cluster_means, diagnostics)
  gmm.py      # GMM backend (first)
  hdbscan.py  # HDBSCAN backend (later — drops in, no core change)
  errors.py   # tool-scoped exceptions (subclass shared AxiommAnalysisError)
  io.py       # file adapters: read/write .npy/.json artifacts standalone
```

## 5. Shared contracts (the hybrid seam)

Three shared pieces live at `axiomm.analysis`:

- **Typed payloads** — `DecompositionResult`, `ClusteringResult`,
  `MineralAssignment`, each carrying `diagnostics` and provenance the way
  `AxiommSignalPayload` does. This is the in-memory seam between tools.
- **Backend protocols + registry** — one ABC/Protocol per swappable domain
  (`Decomposer`, `Clusterer`), plus a registry mirroring the converter's
  reader/writer registry, so backends are runtime-selectable and
  entry-point discoverable.
- **File adapters** — each tool's `io.py` reads/writes the current
  artifacts, so any tool runs standalone from disk with no pipeline.

## 6. Hard rules carried over from stage one

1. **Headless core, UX on top.** The `eds_spectrum_plot_v3.py` tkinter GUI
   and `matplotlib.use()` juggling are split: a pure plotting core, a
   separate UX adapter. Same rule that gates the converter's UX chunks.
   No core tool imports Tkinter, calls `input()`, prints on import, or
   opens windows.
2. **LOCKED constants → versioned config.** Line energies, atomic weights,
   mineral library, GMM `n_components=7`, PCA `output_dimension=15`, energy
   calibration — all become named config/presets with provenance, never
   hidden magic numbers.
3. **Scientific-data safety.** Never silently overwrite outputs; no generic
   `Exception` from public functions; missing optional metadata is a
   diagnostic, missing required metadata is a named exception.
4. **Default to generality.** Every backend ships behind a protocol so
   future methods plug in alongside rather than replacing.

## 7. `axiomm.pipeline` — the composition object

A **Pipeline** is a user-composed, ordered list of steps; each step is
`(tool, backend choice, params)`. It is a first-class object and the UX
backbone.

- **Composition:**
  `Pipeline([Decompose(backend="pca", n=15), Cluster(backend="gmm", k=7),
  Label(reference="melts_v1"), Report("phase_map")])`. Order is the user's
  execution order.
- **Type-checked wiring:** each tool declares the typed payload it consumes
  and produces, so the pipeline validates step *N*'s output type against
  step *N+1*'s input **before running** — fail fast.
- **In-memory when composed, files at the seams:** composed steps hand
  payloads directly; a step run or resumed from disk uses the tool's file
  adapter. The same step works inside a pipeline or standalone on a folder.
- **Provenance:** a pipeline run emits a manifest (ordered steps, backend
  choices, params, per-step diagnostics) — descendant of the converter's
  manifest.
- **Isolation preserved:** the pipeline orchestrates; it never owns logic.
  Every tool stays independently runnable and testable.
- **Scope:** designed now, **built last** — it needs ≥2 real tools to
  compose. The deferred UX layer will eventually attach here.

## 8. Extraction sequence (roadmap)

Each item is its own chunk-driven mini-cycle (spec → plan → TDD →
verify → commit → STATE update), exactly as the converter was built.

| # | Chunk | Domain |
|---|-------|--------|
| S0 | Shared foundations: `axiomm.analysis` errors, base payloads, backend protocol + registry, reference-library config scaffolding | shared |
| S1 | `decomposition` — PCA backend | ① |
| S2 | `clustering` — GMM backend (first composable pair; exercises the typed seam) | ② |
| S3 | `mineralogy` — stoichiometry + matching (+ reference library) | ③ |
| S4 | `reporting` — spectrum → phase_map → hub, and extracted `validation` utility | ④ |
| S5 | `axiomm.pipeline` — composes S1–S4 | pipeline |
| S6 | Second backends: UMAP, HDBSCAN (slot in once protocols proven) | ①② |

## 9. Documentation deliverables (first-class)

- A **stage-two section in `docs/dev/STATE.md`** with a per-tool/per-chunk
  status table in the converter's format.
- A **GitHub wiki Roadmap** stage-two table kept in lockstep with STATE.
- This design doc, committed under `docs/specs/`.
- Report-visual restyling stays explicitly deferred to a later joint
  decision.

## 10. Non-goals / deferred

- Full per-tool signatures and defaults (each tool's own spec).
- Report visual restyling and the generic-font rethink.
- The UX layer (CLI / notebook / dialogs) — inherits the converter's
  deferred UX-layout open decision; the pipeline object is where it will
  eventually attach.
- Second backends (UMAP, HDBSCAN) beyond reserving their protocol slot.

## 11. Constraints reaffirmed

- PolyForm Noncommercial 1.0.0; no MIT headers in new source files.
- Small, self-contained, committable chunks; `docs/dev/STATE.md` updated
  after each.
