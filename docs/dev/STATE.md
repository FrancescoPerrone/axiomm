# AXIOMM — development state

> **Read this file first if you are resuming AXIOMM development in a new
> session.** It is the single source of truth for what has been done, what
> the next chunk is, and which decisions have been made.
> See `CLAUDE.md` at the repo root for the working agreement and hard
> constraints, and `docs/specs/converter_tool_spec.md` for the authoritative
> specification of *the converter tool* (not of AXIOMM as a whole).

> **About AXIOMM's scope.** AXIOMM is a Python package for spectroscopy.
> The work in progress here is one **small utility tool** inside AXIOMM —
> the converter — not the package's headline. Don't describe AXIOMM more
> broadly than that in code or docs; Francesco will define the wider
> scope when he is ready.

## How development is organised

Work is split into **small, self-contained chunks**. Each chunk ends with:

1. The chunk's acceptance criteria verified locally (tests passing).
2. A clean git commit (no AI co-author trailer — see `CLAUDE.md`).
3. This file updated with the new state.
4. A hand back to Francesco.

Never start two chunks in one session without confirmation.

## Chunk plan

### Phase 0 — safe extraction (working end-to-end converter)

| # | Chunk                                                                | Status     |
|---|----------------------------------------------------------------------|------------|
| 1 | Skeleton + foundations (errors, models, protocols, handoff docs)     | ✅ done    |
| 2 | `discover_inputs` (§6) + unit tests                                  | ✅ done    |
| 3 | `XRMMapH5Reader` (§7) + synthetic HDF5 fixture (§20.1) + tests       | ✅ done    |
| 4 | `HyperSpyBuilder` (§8) + axis-order tests                            | ✅ done    |
| 5 | `HSpyWriter` (§9.4) + `convert_file` (§11.2) + end-to-end test       | ✅ done    |

**Phase 0 complete.** The converter has a working Python end-to-end API:
`from axiomm.io.converters import convert_file` accepts an XRM-style
`.h5` and produces an `.hspy` with correctly-labelled axes, AXIOMM
metadata namespace, and structured diagnostics. Verified against the
synthetic fixture and against the real
`IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5` test file.

### Phase 1 — usability

| # | Chunk                                                                | Status     |
|---|----------------------------------------------------------------------|------------|
| 6 | CLI `axiomm-convert` (§10.4) + `convert_many` + CLI tests            | ⛔ blocked* |
| 7 | Manifest writer (§9.5) + logging (§14) + provenance metadata (§15)   | ✅ done     |
| 8 | Optional Tk dialogs (§10.5) + notebook helpers (§10.6)               | ⛔ blocked* |

\* Chunks 6 and 8 are blocked on the **UX-layout decision** — see
"Open decisions" below. Chunk 7 (manifest + logging + provenance) does
not touch UX and can proceed without it; reorder Phase 1 accordingly
when the time comes.

### Phase 2 — configurability and validation (spec §23)

| # | Chunk                                                                | Status     |
|---|----------------------------------------------------------------------|------------|
| 9 | Stricter axis validation + `roi_variant_index` for real XRM files    | ✅ done    |
| 10 | Restructure `payload.metadata["AXIOMM"]` per spec §15 nested layout | ✅ done    |
| 11 | Real-file e2e regression fixture + scientific-constant justification | ✅ done    |

**Phase 2 complete.** The converter validates axes strictly, exposes
the ROI-variant choice, uses the nested AXIOMM metadata layout from
spec §15, ships a manifest schema (v2) that mirrors it, and carries
realistic-shape regression coverage. The three scientific constants
(`energy_scale`, `roi_limit_scale`, `fallback_field_width_um`) were
the Phase-2 residual and were resolved by Phase 4's resolution-ladder
architecture — see the Phase 4 section below.

### Phase 3 — extensibility (spec §23)

| #  | Chunk                                                              | Status     |
|----|--------------------------------------------------------------------|------------|
| 12 | Reader/writer registry (no plugin discovery yet)                   | ✅ done    |
| 13 | Plugin discovery via Python entry points                           | ✅ done    |
| 14 | Generic HDF5 schema-driven reader prototype                        | ✅ done    |

**Phase 3 complete.** "Additional output writers" — parked in the
*Backlog* section below until a concrete scientific need surfaces.

### Phase 4 — calibration provenance & resolution

Driven by the geology team's reply (2026-06-12) on the three legacy
scientific constants. They **did not confirm values**; they returned a
*policy*: treat all three as legacy beamline/sample-specific assumptions,
never apply silently as universal defaults, and build a
metadata-resolution layer with named modes (`legacy` / `generic` /
`strict` / `diagnostic`). Notes recorded at
`scientific_constant_domain_confirmation_notes.txt` at the repo root
(gitignored).

The five decisions locked in 2026-06-12 with Francesco:

1. Default mode stays `legacy` through Chunk 17; **flips to `generic`
   in Chunk 18** (single migration entry in Known-Issues).
2. Presets are code constants in `presets.py`. **The primary UX
   investment is making user-supplied calibration first-class** via
   `convert_file(..., calibration=...)`; the preset is the backstop
   for the known legacy dataset.
3. Split `XRMMapH5Config` → `XRMMapH5Calibration` + `XRMMapH5Schema`,
   mirroring Chunk 14's `HDF5MapConfig` / `HDF5MapSchema` split.
4. The same resolution layer applies to `HDF5MapConfig`.
5. No further deferral — implement + document in this phase.

| #  | Chunk                                                                  | Status     |
|----|------------------------------------------------------------------------|------------|
| 15 | Calibration provenance primitives (`CalibrationSource`, `ConversionMode`, `ResolvedValue`); extend `AxiommSignalPayload`; propagate through metadata + manifest | ✅ done    |
| 16 | Resolution ladder + mode plumbing in `XRMMapH5Reader` and `GenericHDF5MapReader`; new diagnostic codes | ✅ done    |
| 17 | Legacy preset extraction (`presets.py`, `XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1`); split `XRMMapH5Config` → `HDF5MapSchema` + `XRMMapH5Calibration`; resolution-ladder enforcement (`USER_CONFIG` > preset > `STRICT` raise) | ✅ done    |
| 18 | Explicit-units ROI (`roi_limit_units`) + explicit-geometry spatial (`field_width_um`, `field_height_um`, `pixel_size_um`); rename `HDF5MapConfig` → `HDF5MapCalibration` + `fallback_field_width_um` → `legacy_field_width_um`; **flipped default mode to `generic`**; shared `raise_if_strict_unresolved` helper applied to both readers | ✅ done    |
| 19 | Documentation + status closure: rewrite "Scientific assumptions" section → "Calibration resolution: precedence, modes, presets"; wiki Known-Issues entry; wiki Home status row ✅; wiki Roadmap Phase-4 section | ✅ done    |

**Phase 4 complete.** Every scientific calibration value flows
through the `source_metadata` → `user_config` → `legacy_preset` →
`inferred` → `unknown` ladder, gated by `ConversionMode`. Default
mode is `generic` (loud-fallback). Explicit `roi_limit_units` +
explicit-geometry fields give users a first-class way to supply
their own experimental calibration. See `docs/user/converter.md`
→ *Calibration resolution* for the canonical user-facing reference,
and the wiki Roadmap Phase-4 section for the dev-side narrative.

### Backlog (no chunk number assigned)

* **Additional output writers.** Was Phase 3's Chunk 15; parked
  until a specific scientific need surfaces. Reader/writer registry
  (Chunk 12) + entry-point discovery (Chunk 13) mean a future writer
  can drop in without changing AXIOMM.
* **True lazy execution.** The MVP reader materialises eagerly even
  when `lazy=True`; a `lazy_downgraded_to_eager` diagnostic records
  this. Real lazy support pending a concrete user request.
* **UX-blocked chunks (former 6 + 8).** CLI + Tk dialogs +
  notebook helpers. Still on hold pending Francesco's UX-layout
  decision (`axiomm.io.converters.ux.*` vs `axiomm.ux.*`).

## Current state (Phase 4 complete)

The per-chunk timeline is captured by the chunk-plan tables above
plus the git log. This section is the **current snapshot** of what
exists today; the chunk-by-chunk implementation diary that used to
live here has been retired (stale claims like a v1 manifest schema,
a "tiny built-in mapping" for reader lookup, a still-monolithic
`XRMMapH5Config`, and an unimplemented manifest writer were
accumulating without being pruned). Historical findings worth
preserving — the legacy x/y swap, the in-process module-drop test
gotcha, the real-file ROI shape — live in *Historical findings* at
the bottom of this file.

### Module map

* `errors.py` — exception hierarchy (`AxiommConverterError` and
  subclasses). Includes `CalibrationUnresolvedError` (Chunk 16,
  raised in strict mode from Chunk 17).
* `models.py` — `AxisSpec`, `Diagnostic`, `SourceProvenance`,
  `AxiommSignalPayload`, `ConversionResult`. Payload carries an
  optional `resolved_calibration: dict[str, ResolvedValue] | None`
  (Chunk 15).
* `calibration.py` — `CalibrationSource` / `ConversionMode` /
  `ResolvedValue` primitives (Chunk 15).
* `presets.py` — `XRMMapH5Calibration` dataclass +
  `XRMMAP_LEGACY_APS_13_ID_E_PRESET_V1` + minimal preset registry
  (`get_preset` / `iter_presets` / `register_preset`) — Chunk 17,
  audit-grounded Chunk 18 update.
* `metadata.py` — `build_axiomm_namespace` composer + the per-section
  transformers. The namespace gains an additive `calibration` subkey
  when the payload's `resolved_calibration` is populated (Chunk 15).
* `discovery.py` — `discover_inputs(...)` (spec §6).
* `registry.py` — full `Registry` class + `register_reader` /
  `get_reader` / `iter_readers` / `register_writer` / `get_writer` /
  `iter_writers` helpers + plugin discovery via `importlib.metadata`
  entry-points (`axiomm.readers` / `axiomm.writers`, Chunks 12–13).
  `convert_file` goes through this registry; the lookup is no longer
  a hand-rolled mapping.
* `readers/base.py`, `signals/base.py`, `writers/base.py` — runtime-
  checkable `Reader` / `SignalBuilder` / `Writer` protocols.
* `readers/hdf5_schema.py` — `HDF5MapSchema` + canonical
  `XRMMAP_H5_SCHEMA` constant (Chunk 14).
* `readers/hdf5_helpers.py` — shared HDF5 primitives
  (`read_environ_table`, `read_roi_table`, `resolve_navigation_scale`)
  plus the Phase-4 resolution helpers (`resolve_energy_scale`,
  `resolve_roi_limit_interpretation`,
  `resolve_navigation_scale_calibration`,
  `compute_roi_scale_from_units`, `raise_if_strict_unresolved`).
* `readers/xrmmap_h5.py` — `XRMMapH5Reader`. Kw-only constructor
  takes `schema: HDF5MapSchema | None`, `calibration:
  XRMMapH5Calibration | None`, and `mode: ConversionMode =
  GENERIC` (default flipped in Chunk 18). Walks the resolution
  ladder for `energy_scale`, `roi_limit_units`, and
  `navigation_scale`; raises `CalibrationUnresolvedError` in
  strict mode.
* `readers/hdf5_generic.py` — `GenericHDF5MapReader` +
  `HDF5MapCalibration` (renamed from `HDF5MapConfig` at Chunk 18).
  Same ladder, no named preset; same default mode (`GENERIC`).
* `signals/validation.py` — `validate_axes` (Chunks 4 + 9).
* `signals/hyperspy_builder.py` — `HyperSpyBuilder` +
  `build_hyperspy_signal`. Defends against the HyperSpy
  reverse-order navigation-axes gotcha by matching
  `AxisSpec.index_in_array` rather than tuple position (Chunk 4).
* `writers/hspy.py` — `HSpyWriter` (refuses to silently overwrite).
* `writers/manifest.py` — `ManifestWriter` + `build_manifest_dict`.
  Manifest schema **v2** (Chunk 10) — `axiomm_metadata` subkey
  mirrors `signal.metadata.AXIOMM` exactly. Carries the additive
  `calibration` subkey since Chunk 15.
* `workflows.py` — `convert_file`. Uses the full registry for
  named / `"auto"` reader dispatch. Writes the manifest sidecar by
  default (`manifest=True`). Output-path resolution per spec §11.2.
* `axiomm.io.converters.__init__` — eager exports
  (`convert_file`, `validate_axes`, registry helpers, calibration
  primitives, presets) + PEP 562 lazy attribute imports for the
  HDF5/HyperSpy-bearing concrete classes.

### Tests (current count)

**360 pass** with `[dev,all]` extras installed (Python 3.11,
hyperspy 2.4.0, h5py 3.16.0, pytest 9.0.3). Without hyperspy: 208
pass + 5 skipped (the hspy_writer, hyperspy_builder, workflows,
and realistic-fixture regression modules skip as one unit each;
`test_lazy_concrete_builder_exports` skips individually).

### What does **not** yet exist

* `convert_many` — Chunk 6 (UX-blocked).
* CLI entry point `axiomm-convert` — Chunk 6 (UX-blocked).
* `ux/` subpackage (CLI, notebook helpers, Tk dialogs) — Chunks
  6 / 8 (UX-blocked).
* True lazy execution beyond the accepted-but-downgraded
  `lazy=True` flag (a `lazy_downgraded_to_eager` diagnostic
  records every downgrade). Future work.
* Source-metadata extraction from `/xrmmap/config/mca_calib/*` /
  `/xrmmap/mcasum/energy` / `/xrmmap/config/scan/*` /
  `/xrmmap/roimap/mcasum/<ROI>/limits` — the audit-confirmed
  paths exist in the inherited files; the resolution ladder's
  `SOURCE_METADATA` branch currently consults only the environ
  table's beam-size key. Reading the other paths is the natural
  follow-up to Phase 4 when the need surfaces.
* Additional output writers — parked in Backlog above.
* `CITATION.cff` and `ACKNOWLEDGEMENTS.md`.

### Repository surface (non-source)

* `pyproject.toml` — src-layout, `requires-python = ">=3.10"`,
  optional extras for `hdf5`, `hyperspy`, `all`, `notebook`,
  `dev`, `docs`. Pytest configured with `pythonpath = ["src"]`.
* `LICENSE` — PolyForm Noncommercial 1.0.0.
* `README.md` — short package summary, Tools section, install
  instructions, wiki link, licence note.
* `docs/specs/converter_tool_spec.md` — the authoritative spec.
* `docs/specs/_legacy/converter_prototype.py` — the original
  prototype, reference-only. **Do not import or extend from
  package code.**
* `docs/user/converter.md` — comprehensive user guide
  (canonical, repo-shipped version; the wiki *Converter* page is
  the GitHub-side landing).
* `docs/user/known_issues.md` — comprehensive known-issues page.
* `docs/conf.py` + `docs/Makefile` — Sphinx project (furo theme,
  myst-parser, sphinx-autoapi, sphinx-copybutton, mathjax,
  intersphinx).
* `docs/dev/STATE.md` (this file) — single source of truth for
  *what AXIOMM has and what's next*.
* `.gitignore` — Python/scientific scratch outputs, the design
  identity working folder rules. Workflow-specific local
  ignores live in `.git/info/exclude` (per-clone, untracked).
* Public wiki at <https://github.com/FrancescoPerrone/axiomm/wiki>
  (Home, Tools, Converter, Converter-Architecture, Known-Issues,
  Roadmap, Development, Specification, Glossary; `_Sidebar` /
  `_Footer` shells).

## Historical findings (recorded by chunk)

> These notes captured one-off discoveries during specific chunks
> that are still useful long-term reference. They describe state
> **at the time of the chunk** — read with that disclaimer in mind
> if anything reads as out of date.

### Real-file findings from Chunk 3 (recorded for later chunks)

The reader was smoke-tested against the smallest real XRM file at
`/home/francesco/Desktop/research/melts/data/Maps-HDF5/IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5`
(not in the repo). Findings:

- **Counts shape** `(23, 21, 4096)` — `(xdim, ydim, n_channels)`. Reads
  cleanly; `energy_scale = 40.96 / 4096 = 0.01` keV/channel gives a
  reasonable 40.96 keV span.
- **Beam size** `"2um"` was parsed correctly → navigation scale 2.0 µm.
- **65 environ entries** were extracted without issue.
- **ROI limits shape** is `(35, 7, 2)`, *not* `(n_rois, 2)`. The real
  file stores multiple ROI variants per element (likely per-detector
  or per-fit-pass). The reader at the time emitted the
  `roi_limits_unexpected_shape` diagnostic and skipped ROI extraction.
  *Resolved in Chunk 9*: a `roi_variant_index` field on the
  calibration dataclass (originally on `XRMMapH5Config`, now on
  `XRMMapH5Calibration` after the Chunk 17 split) plus the
  `read_roi_table` helper accept both 2-D and 3-D limits arrays.

### Chunk 5 finding (recorded for future contributors)

The "no side effects" tests in `test_import_has_no_side_effects.py`
originally dropped cached `axiomm.*` modules from `sys.modules` and
re-imported them to observe import behaviour. Once enough downstream
code had been written (Chunks 3–5), those drops created **fresh class
objects** for the exception types (e.g. `OutputExistsError`) on
re-import, while older code paths (the writer, the builder) still held
references to the *original* classes. `pytest.raises(OutputExistsError)`
in test code then failed to match instances raised by the writer because
`isinstance(exc, OutputExistsError_new) == False`. The fix was to move
those tests into **subprocesses** via `_run_in_subprocess(...)` so the
import semantics are observed in true isolation, with no spillover into
the parent test session. The `_drop_axiomm_modules` helper was removed.
This is the canonical pattern for any future "test something at import
time" check in AXIOMM — don't mutate the parent process's `sys.modules`.

### Chunk 4 finding (recorded for future contributors)

HyperSpy's `axes_manager.navigation_axes` is ordered *reverse* to numpy
order within the navigation-role group. For a numpy array of shape
`(d0, d1, d2)` constructed as `hs.signals.Signal1D(data)`:

```
navigation_axes[0].index_in_array == 1   # numpy axis 1
navigation_axes[1].index_in_array == 0   # numpy axis 0
signal_axes[0].index_in_array == 2       # numpy axis 2
```

The prototype's `xrf_data.axes_manager.navigation_axes[0].name = 'x'`
therefore labelled what is actually numpy axis 1 (ydim, in our
convention) — silently swapping x and y. Our builder defends against
this by **matching `AxisSpec.index_in_array` to `hs_axis.index_in_array`
during assignment**, never relying on tuple position. The `Signal2D`
case has the same reversal within the signal-axes group.

Real-file e2e against
`IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5` (data shape `(23, 21, 4096)`)
produces a `Signal1D` whose axes label correctly: `idx=0 → 'x' size=23`,
`idx=1 → 'y' size=21`, `idx=2 → 'Energy' size=4096`, with
`signal.metadata.General.title` set from the file stem and
`signal.metadata.AXIOMM.{reader,provenance,diagnostics}` populated.

> Note: that Chunk-4 finding refers to the *flat* AXIOMM namespace
> that existed at the time. Chunk 10 nested it under `converter` /
> `axes` / `source` / `provenance_classification` / `diagnostics` —
> see the Chunk-10 entry in *Current state* and the migration guide
> in [`docs/user/known_issues.md`](../user/known_issues.md).

## Published docs — outstanding issues

First successful GitHub Pages deploy uncovered three issues. One
fixed now, two recorded for later:

* ✅ **Dark / light logo not loading.** Furo resolves `light_logo`
  and `dark_logo` *relative to* `_static/`, so paths like
  `"../identy/AXIOMM_Design/axiomm_wave_icon.svg"` produced
  broken `_static/../identy/...` URLs on the deployed site. Fixed
  by adding `html_static_path = ["../identy/AXIOMM_Design"]` in
  `docs/conf.py` and reducing the logo / favicon entries to bare
  filenames. Sphinx now copies the identity assets into
  `_build/html/_static/` at build time, and Furo's URL rewriting
  resolves cleanly. (Local builds also copy any other files
  currently in the identity folder, but `.gitignore` keeps the
  drafts out of the CI checkout, so the deployed site stays clean.)
* ⬜ **Table of contents under Furo.** Adding a `{toctree}` to a
  page surfaces an error / mis-render under the current style.
  Not investigated this turn — needs a specific reproduction
  (which page, which directive, exact error) before a fix. Pick
  up after Phase 3 land or whenever it becomes blocking.
* ⬜ **Dark-mode is the default; user reports it should be light.**
  Furo ships a built-in dark/light toggle in the top-right; the
  initial mode follows `prefers-color-scheme` from the browser /
  OS, so this might just be system-level rather than a Furo
  default. Re-check on a system with a light-mode browser before
  changing anything; if a default-light pin is needed, Furo
  supports `default_mode` in `html_theme_options`.

## Documentation publishing

The `docs/` Sphinx project is configured to publish via two
independent hosts. Pick whichever (or both):

* **GitHub Pages** — `.github/workflows/docs.yml`. The *build* job
  runs on every push to `main`, every PR, and on manual dispatch —
  so doc regressions are caught even when nobody intends to publish.
  The *deploy* job is **opt-in via manual dispatch only**: it runs
  exclusively when you click `Actions → docs → Run workflow` on the
  main branch. This deliberately stops push-to-main runs from
  emailing "deploy failed" while Pages is unavailable (the previous
  always-deploy behaviour produced silent noise on this private
  repo). To actually publish: enable
  `Settings → Pages → Source: GitHub Actions` (private repos need
  Pro / Team / Enterprise), then trigger the workflow manually.
* **Read the Docs** — `.readthedocs.yaml`. Sign in at
  readthedocs.org with the GitHub account and import the repo;
  RTD reads the config automatically. Public repos are free;
  private repos need an RTD subscription.

The CI build deliberately does not pass `-W` (warnings as errors)
because sphinx-autoapi's rendering of two XRMMapH5 docstrings trips
cosmetic docutils warnings; the HTML output is unaffected. Local
builds still surface them so the underlying docstring formatting
can be cleaned up when convenient.

## Next chunk

**Phase 4 closed.** Phases 0 → 4 are all complete; the converter
tool has reached the scope captured in `docs/specs/converter_tool_spec.md`
modulo the items listed under *Backlog* above (additional output
writers, true lazy execution) and the *UX-blocked chunks* (CLI,
`convert_many`, Tk dialogs, notebook helpers) waiting on Francesco's
UX-layout decision.

There is no single next chunk decided in this file. Plausible
moves, in no particular order:

* **Unblock the UX-layout decision** so former Chunks 6 / 8 can
  proceed (CLI = a meaningful step toward a pre-alpha PyPI
  release).
* **Source-metadata extraction** in the resolution ladder
  (`/xrmmap/config/mca_calib/*`, `/xrmmap/mcasum/energy`,
  `/xrmmap/config/scan/*`, `/xrmmap/roimap/mcasum/<ROI>/limits`)
  so `GENERIC` mode prefers file metadata over the legacy preset
  on inherited XRM files. Audit-confirmed paths exist; the work
  is bounded.
* **Begin the wider AXIOMM surface** (`axiomm.signal`,
  `axiomm.analysis`, …) — the converter is one small tool inside
  the broader spectroscopy package; Francesco will decide when /
  what to add next.
* **PyPI rehearsal** on TestPyPI (name claim, classifiers,
  `py.typed`, README banner) — see the discussion in the Phase 4
  closure session for the full readiness checklist.

## Verifying the current state (Phase 4 complete)

In an environment with Python ≥ 3.10 and the dev extras installed, the
canonical verification commands are:

```bash
cd /home/francesco/Desktop/research/axiomm
python -m pip install -e ".[dev,all]"
pytest -q
```

Expected result: **360 tests pass**, 0 fail. With only h5py installed
(no hyperspy): 208 pass, 5 skipped (the hspy_writer, hyperspy_builder,
workflows, and realistic-fixture regression modules skip as one unit
each; the lazy-export `test_lazy_concrete_builder_exports` skips
individually).

> Note: Francesco's `xrf` conda env has hyperspy 2.3.0 and h5py 2.10.0
> but is Python 3.9, below our declared `requires-python = ">=3.10"`,
> and lacks pytest. For dev/test runs use a Python 3.11+ environment
> with the `[dev,all]` extras installed. The author's ephemeral venv
> for this work is at `/tmp/axiomm-venv` — Python 3.11, hyperspy 2.4.0,
> h5py 3.16.0, pytest 9.0.3.

If the system pytest (`/usr/bin/pytest`, Python 3.11) is used without
installing the package, the `[tool.pytest.ini_options].pythonpath = ["src"]`
entry in `pyproject.toml` is enough — `pytest -q` from the repo root still
works.

## Open decisions

* **Licence (decided in Chunk 1).** PolyForm Noncommercial 1.0.0 was chosen
  because Francesco said: "we do not want to release it completely free just
  now". Researchers and academic institutions can use AXIOMM freely;
  commercial users need a separate licence from Francesco. The licence is
  easy to change later (re-licensing a project still owned by a single author
  is straightforward) — if Francesco prefers a different model (BUSL,
  source-available custom, "all rights reserved"), it can swap in one
  commit. Document any change in this file and update `LICENSE` and
  `README.md` in lockstep.
* **Repository hosting.** Local-only for now. When the package is ready to
  be published, Francesco will create the GitHub repository himself and
  push from his account.
* **Package name `axiomm`.** Not yet checked against PyPI. Verify before any
  publication attempt — if taken, decide an alternative early (e.g.
  `axiomm-tools`, `pyaxiomm`) and update `pyproject.toml`,
  `README.md`, and the import root.
* **`axiomm.io` namespace.** Reserved for I/O subpackages (`converters/`
  today, possibly `formats/`, `streaming/` later). Don't put non-I/O code in
  `axiomm.io`. The broader AXIOMM analysis pipeline will live in sibling
  packages (`axiomm.signal`, `axiomm.analysis`, …) — names TBD with
  Francesco when scope expands beyond the converter.
* **UX layout (deferred by Francesco).** Spec §10 places all UX under
  `axiomm.io.converters.ux.*`. That made sense when AXIOMM ≈ the
  converter; it is less clearly right now that AXIOMM is a broader
  spectroscopy package with future tools. The three candidates are:
  (a) *Hybrid* — generic Tk and notebook helpers under `axiomm.ux.*`,
  converter-specific CLI under `axiomm.io.converters.ux.*`;
  (b) *Spec-literal* — everything under `axiomm.io.converters.ux.*`
  as written; (c) *Defer* — pick once the second AXIOMM tool's UX
  needs are visible. Francesco chose **(c) Defer**. **Do not start
  Chunks 6 or 8** until either Francesco specifies the layout or a
  second tool's needs make the right answer obvious. Chunk 7 (manifest
  + logging + provenance) is independent of UX and can proceed.
* **Documentation tooling (decided, post-Phase 0).** Two surfaces:
  (a) the **GitHub wiki** for landing pages, navigation, and quick
  orientation; (b) **Sphinx + sphinx-autoapi + furo theme + myst-parser**
  in `docs/` for the canonical user guide and the auto-generated Python
  API reference. Both are maintained for now; once the API stabilises
  (Phase 2+) and the Sphinx HTML is published (GitHub Pages or RTD),
  the wiki pages can shrink and point at the published docs. Build
  locally with `cd docs && make html`. Install the build toolchain via
  `pip install -e ".[docs]"`.

## Notes for resuming work

* Real XRM test data lives at
  `/home/francesco/Desktop/research/melts/data/Maps-HDF5/` (~900 MB,
  267 files). The smallest single file
  (`IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5`, ~950 KB) is the
  canonical out-of-band smoke-test target for the readers. **Do
  not commit** any real `.h5` file (the `*.h5` rule in
  `.gitignore` already excludes them; the `!tests/**/*.h5`
  exception is reserved for tiny test fixtures generated under
  `tmp_path`).
* The 2026-06-12 metadata audit on that folder produced
  `metadata_audit_report.md` (alongside an HTML version) at the
  Maps-HDF5 directory's parent. That report confirms the
  source-metadata paths the resolution ladder's `SOURCE_METADATA`
  branch will eventually read from (see Phase 4 → *Next chunk*).
* The author's ephemeral verification venv is at
  `/tmp/axiomm-venv` (Python 3.11, hyperspy 2.4.0, h5py 3.16.0,
  pytest 9.0.3, sphinx 9.0.4 + furo + myst-parser + sphinx-autoapi
  + sphinx-copybutton). Recreate with
  `python3.11 -m venv /tmp/axiomm-venv && /tmp/axiomm-venv/bin/pip
  install -e ".[dev,all,docs]"` if `/tmp/` was cleared.
