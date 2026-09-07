# AXIOMM Stage Two · S4 — reporting

> Status: design accepted to start (2026-09-07), built in small reviewable
> chunks. Reporting content and style are expected to be revisited later; the
> architecture below is chosen so that revisiting is cheap — new report types,
> sections, formats, and themes plug in without touching the core.

## 1. Goal, in one sentence

Turn what a run produced — a `PipelineResult`, or any single stage's output —
into a readable report, so a user can see at each step whether the analysis is
heading the right way.

## 2. What it is / is not

- **Is:** a small, pluggable reporting subsystem — per-stage *sections*
  assembled by a *backend* (HTML first) into one artifact, plus a standalone
  EDS *spectrum* unit and a general multi-run *hub* index.
- **Is not:** a styling system (visual restyling stays explicitly deferred to a
  later joint pass), a validation/quality gate that halts a run (reporting is
  descriptive; the `reliability` gate remains the place for pass/fail on
  chemistry), or a UX layer (that sits on top later).

## 3. Core idea — sections + backends

A report is **composed of per-stage sections**. The `PipelineResult` already
carries every stage's output (decomposition, clustering, cluster means, peaks,
quantification, reliability, matches, phase map, diagnostics, provenance), so
each stage maps to one section. "Check at each step" is then intrinsic, and
"offer more reporting options" becomes "register another section or backend".

- A **section renderer** produces a `ReportSection` for one stage/aspect. It
  declares whether it `applies` to a given result (so a clusters-only run simply
  omits the mineral sections). Each is usable **standalone** on its stage's
  payload, per the suite's every-tool-runs-alone rule.
- A **backend** (in the `reporters` registry, mirroring `decomposers` /
  `clusterers`) assembles the selected sections into an output. `html` is the
  first backend: one **self-contained** page (matplotlib figures embedded as
  base64 data URIs, inline CSS — no external assets). Markdown / PDF /
  interactive backends can be added later under the same registry.

## 4. Flexibility (the part that must age well)

- **`reporters` registry** — report *formats* are named, swappable options.
- **`ReportConfig`** — which sections and in what order (`include` / `exclude` /
  `sections`), figure embed-vs-link, title/metadata, and a **theme hook** left
  as a seam for the deferred styling pass.
- **Sections are individually registered** — the number of reporting options
  grows by registration, never by editing the assembler.
- The **hub** is deliberately **general**: it indexes a list of reports plus
  arbitrary per-run metadata (flexible columns / grouping), to capture many
  samples, users, and data cases rather than one fixed layout.

## 5. Module layout

```
src/axiomm/analysis/reporting/
  __init__.py        # Reporter protocol, reporters registry, render_report, ReportConfig
  base.py            # Reporter + SectionRenderer protocols
  models.py          # ReportSection, ReportConfig, Report (+ provenance/diagnostics)
  registry.py        # reporters (name->backend) and sections registries
  io.py              # safe artifact writing (no silent overwrite)
  html.py            # the "html" backend: sections -> one self-contained page
  spectrum.py        # standalone EDS spectrum plot unit (legacy port)
  hub.py             # general multi-run index
  sections/          # one renderer per stage: overview, decomposition,
                     #   clustering, cluster_means, peaks, quant, reliability,
                     #   minerals, phase_map
  validation.py      # shared dataset/schema-check utility (extracted)
```

Integration: `PipelineResult.report_html(path=None, *, config=None)` and
`result.report(backend="html", config=...)`, plus a standalone
`render_report(result_or_stage, backend="html", ...)`.

## 6. Hard constraints

- **Headless core, UX on top.** Pure rendering: matplotlib forced to the `Agg`
  backend, figures serialized to data URIs; never import tkinter, open a window,
  call `matplotlib.use()` juggling at import, `input()`, or print on import.
- **matplotlib is a lazy optional dependency** (`viz` extra). Missing it raises
  `AnalysisDependencyError` with a clear install hint — never a hard import.
- **Never silently overwrite** an output (`OutputExistsError`); no generic
  `Exception` from public functions; missing optional stage data is a section
  that says "not run", not a crash.
- Every report records **provenance** (backend, config, source run) and carries
  diagnostics.

## 7. Chunk sequence (the review gates)

- **S4a — foundations:** `base` / `models` / `ReportConfig` / `reporters`
  registry + `Report` + safe `io` writer + the HTML skeleton assembler (a valid
  empty page from zero sections). Framework only, no science yet.
- **S4b — headline:** `overview` + `phase_map` sections → real HTML from a
  `PipelineResult`; `result.report_html`. The first openable artifact.
- **S4c — decomposition + clustering** sections (scree / explained variance;
  label map + cluster sizes).
- **S4d — cluster means + spectrum unit + quant / reliability / minerals**
  tables.
- **S4e — hub** (general multi-run index) + `validation` utility extraction.
- **S4f — docs / examples / README + wiki + STATE lockstep.**

Each chunk: acceptance tests pass, one clean commit, hand back for review.

## 8. Acceptance criteria

1. `from axiomm import Pipeline` and importing `axiomm.analysis.reporting` stay
   free of importing matplotlib until a report is actually rendered.
2. `result.report_html(path)` on a full run writes a **self-contained** HTML
   file (no external asset references) with one section per available stage.
3. A clusters-only result reports cleanly — mineral/quant sections are omitted
   (their renderers report `applies == False`), not errored.
4. Each section renderer runs **standalone** on its stage's payload.
5. Report **format is pluggable**: a backend registered under a new name in the
   `reporters` registry is selectable via `render_report(..., backend=name)`
   with no change to the assembler.
6. Writing never silently overwrites; provenance and diagnostics are recorded.
7. The hub builds an index over multiple runs with arbitrary per-run metadata.

## 9. Deferred (revisit later — expected)

Visual restyling and theming (the `ReportConfig` theme hook is the seam); report
content selection beyond the first section set; additional backends (markdown,
PDF, interactive); the breadth of the hub's grouping/metadata model; and the UX
layer that will drive report choices interactively. These do not change the
meaning of a produced report.
