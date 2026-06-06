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
| 5 | `HSpyWriter` (§9.4) + `convert_file` (§11.2) + end-to-end test       | ⬜ next    |

### Phase 1 — usability

| # | Chunk                                                                | Status     |
|---|----------------------------------------------------------------------|------------|
| 6 | CLI `axiomm-convert` (§10.4) + `convert_many` + CLI tests            | ⛔ blocked* |
| 7 | Manifest writer (§9.5) + logging (§14) + provenance metadata (§15)   | ⬜ pending |
| 8 | Optional Tk dialogs (§10.5) + notebook helpers (§10.6)               | ⛔ blocked* |

\* Chunks 6 and 8 are blocked on the **UX-layout decision** — see
"Open decisions" below. Chunk 7 (manifest + logging + provenance) does
not touch UX and can proceed without it; reorder Phase 1 accordingly
when the time comes.

### Phase 2 / 3 — configurability and extensibility

Tracked in spec §23. Pick up after Phase 1 lands.

## Current state (as of Chunk 4)

What exists in this repository:

* Package skeleton under `src/axiomm/io/converters/` with sub-packages for
  `readers/`, `signals/`, `writers/`.
* `errors.py` — full exception hierarchy from spec §13.
* `models.py` — `AxisSpec`, `Diagnostic`, `SourceProvenance`,
  `AxiommSignalPayload`, `ConversionResult` plus the `AxisRole`,
  `SignalKind`, `Severity` type aliases (spec §8.3, §9.6).
* `readers/base.py`, `signals/base.py`, `writers/base.py` — runtime-checkable
  `Protocol`s for `Reader`, `SignalBuilder`, `Writer`. Generality is built in
  from the start: HyperSpy is one possible builder, not an assumption.
* **`discovery.py` — `discover_inputs(...)`** implementing spec §6: file or
  directory input, optional extension filter (case-insensitive), optional
  sample-substring filter on file names, optional recursion, deterministic
  ordering, `InputDiscoveryError` on missing path / non-file-non-dir input
  / no matches with `require_non_empty=True`. Pure pathlib, no HDF5, no GUI.
* `tests/io/converters/test_import_has_no_side_effects.py` — guards spec
  §24.1 (silent import) plus a "models stay backend-neutral" check.
* **`tests/io/converters/test_discovery.py`** — 18 tests covering every
  spec §6 behavioural requirement plus determinism and a "no h5py / no
  tkinter import" check specific to `discover_inputs`.
* **`readers/xrmmap_h5.py` — first concrete reader.** `XRMMapH5Reader`
  implements the `Reader` protocol; every HDF5 path is a field of the
  frozen `XRMMapH5Config` (spec §7.5) so XRM-style files with different
  paths can be read by passing a configured reader. Missing optional
  metadata becomes structured `Diagnostic`s on the payload; only a
  missing primary counts dataset raises (`DatasetNotFoundError`, with an
  actionable message naming the path and the config field to override).
  Includes spec §7.6 string-decoding helpers (`decode_hdf5_string`,
  `decode_hdf5_string_array`) and the spec §7.7 beam-size parser
  (`parse_micrometre_value`). MVP reads eagerly; `lazy=True` is accepted
  and produces a `lazy_downgraded_to_eager` diagnostic.
* **`tests/io/converters/conftest.py`** — `synthetic_xrmmap_h5` factory
  fixture (spec §20.1): builds minimal valid XRM-map HDF5 files in
  `tmp_path` with switches to omit each dataset group so the reader's
  missing-metadata branches can be exercised.
* **`tests/io/converters/test_xrmmap_h5_reader.py`** — 59 tests covering
  `XRMMapH5Config` defaults (spec §17), the protocol attributes,
  `can_read` (extension + signature peek), happy-path `read`, every
  missing-metadata branch, the `lazy` flag, the config-override
  "different paths" use case, and an `import` hygiene check.
* `axiomm.io.converters.__init__` re-exports `XRMMapH5Reader` and
  `XRMMapH5Config` lazily via PEP 562 `__getattr__`, so package import
  still does not pull in `h5py`.
* **`signals/validation.py` — `validate_axes`**: structural-then-semantic
  checks per spec §8.6 (axis count vs. `data.ndim`; every axis declares
  a valid in-bounds `index_in_array`; the indices form a complete
  permutation of `[0, ndim)`; axis sizes match the data shape;
  signal-axis count matches the requested `SignalKind`). Eagerly
  re-exported from the converters package — it has no heavy deps.
* **`signals/hyperspy_builder.py` — first concrete `SignalBuilder`.**
  `HyperSpyBuilder.build(payload)` validates the payload, resolves
  `signal_kind="auto"` from the count of signal axes, optionally
  transposes the data so signal axes are trailing (HyperSpy's
  expectation), constructs the right `hs.signals.*` class, and assigns
  axis name/units/scale/offset by matching `AxisSpec.index_in_array` to
  HyperSpy's `axis.index_in_array` — *not* by tuple position, which is
  how the prototype's axis-labelling bug came in (HyperSpy reverses
  `navigation_axes` order relative to numpy). Metadata is copied into
  `signal.metadata.AXIOMM`, including provenance and diagnostics;
  `payload.title` becomes `signal.metadata.General.title`;
  `payload.original_metadata` carries over verbatim.
  `build_hyperspy_signal(payload)` is a convenience wrapper.
  Lazily re-exported from the converters package via `__getattr__`.
* **`tests/io/converters/test_hyperspy_builder.py`** — 26 tests covering
  signal-kind resolution (signal1d/signal2d/base/auto), every
  `validate_axes` failure mode, axis-name correctness (the test that
  catches the prototype bug), non-canonical axis order (signal axis at
  numpy index 0 → transparently transposed), every metadata-propagation
  branch, the convenience function, an end-to-end synthetic-fixture
  round trip, and the no-tkinter-on-import check. Module-level
  `pytest.importorskip("hyperspy.api")` so the suite still passes
  cleanly in environments without HyperSpy.
* `pyproject.toml` with src-layout, `requires-python = ">=3.10"`, optional
  extras for `hdf5`, `hyperspy`, `all`, `notebook`, `dev`. Pytest configured
  with `pythonpath = ["src"]` so tests run without an install.
* `LICENSE` — PolyForm Noncommercial 1.0.0.
* `README.md` — short package summary (with AXIOMM acronym expansion),
  Tools section, dev install, wiki link, licence note.
* `CLAUDE.md` at repo root — hard constraints and working agreement;
  spells out the AXIOMM acronym and warns the M's are *Mineral Mapping*,
  not Microscopy.
* `docs/specs/converter_tool_spec.md` — the authoritative spec (copy of the
  original from `docs_refactoring/`).
* `docs/specs/_legacy/converter_prototype.py` — the original converter
  prototype, reference-only. **Do not import or extend it from package code.**
* `.gitignore` tuned for Python + scientific scratch outputs.
* Public wiki at <https://github.com/FrancescoPerrone/axiomm/wiki>
  (Home, Tools, Converter, Converter-Architecture, Roadmap, Development,
  Specification, Glossary, plus `_Sidebar` / `_Footer`).

What does **not** yet exist (deferred to later chunks):

* Any concrete writer, or workflow function.
* The `workflows.py` and `registry.py` modules.
* The CLI entry point (commented out in `pyproject.toml`).
* The `ux/` subpackage (CLI, notebook, Tk dialogs).
* User-facing documentation under `docs/user/`.
* `CITATION.cff` and `ACKNOWLEDGEMENTS.md`.

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
  or per-fit-pass). The reader currently emits the
  `roi_limits_unexpected_shape` diagnostic and skips ROI extraction — a
  safe MVP behaviour but a real schema-conformance issue. To recover
  ROI metadata from real files, one of:
  1. Add a `roi_variant_index: int = 0` (or similar) to
     `XRMMapH5Config` in Phase 2 and use `limits[:, roi_variant_index, :]`.
  2. Use the generic HDF5 schema-driven reader (Phase 3, spec §23).

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

## Next chunk: Chunk 5 — `HSpyWriter` + `convert_file` + end-to-end test

**Goal.** Implement spec §9.4 (`HSpyWriter`) and spec §11.2
(`convert_file`) so the converter has a working end-to-end Python API:
`axiomm.io.converters.convert_file(...)` takes a path in, writes a
`.hspy` file out, and returns a `ConversionResult`.

**New files (expected):**

* `src/axiomm/io/converters/writers/hspy.py` — `HSpyWriter` class
  implementing the `Writer` protocol. Default extension `.hspy`. Raises
  `OutputExistsError` when the target exists and `overwrite=False`;
  delegates the actual write to `signal.save(...)`.
* `src/axiomm/io/converters/workflows.py` — `convert_file(...)` per
  spec §11.2, returning a `ConversionResult`. A small built-in
  reader/writer name-to-class lookup is acceptable (the full
  `registry.py` lands in Phase 3); `reader="auto"` should dispatch via
  `Reader.can_read(path)` against the built-in mapping and fail with
  `ReaderDetectionError` when ambiguous or unsupported.
* `tests/io/converters/test_hspy_writer.py` — writer behaviour
  (writes a usable file; refuses to overwrite by default; respects
  the `overwrite` flag).
* `tests/io/converters/test_workflows.py` — `convert_file` happy path
  end-to-end on the synthetic fixture; `OutputExistsError` enforcement;
  `reader="auto"` dispatch.

**Acceptance criteria for Chunk 5:**

1. `HSpyWriter()` advertises `name="hspy"` and
   `supported_extensions=(".hspy",)`.
2. `HSpyWriter().write(signal, output_path)` writes a `.hspy` file at
   `output_path` and returns the resolved `Path`. The written file is
   loadable back by `hyperspy.api.load(...)` with the same shape and
   the same `AXIOMM` metadata namespace.
3. `HSpyWriter().write(signal, output_path)` raises `OutputExistsError`
   when the file already exists and `overwrite=False`. Passing
   `overwrite=True` replaces the file.
4. `convert_file(input_path, output_path=...)` returns a
   `ConversionResult` whose `input_path`, `output_path`, `reader_name`
   and `writer_name` fields are populated. `manifest_path` is `None`
   (manifest is Chunk 7, not Chunk 5).
5. Output-path resolution rules:
   - explicit `output_path=...` wins;
   - otherwise `output_dir + input_path.stem + ".hspy"`;
   - otherwise `input_path.with_suffix(".hspy")`.
6. `reader="xrmmap_h5"` resolves through a tiny built-in mapping to
   `XRMMapH5Reader()`; `reader="auto"` iterates the built-in mapping,
   accepts the first reader whose `can_read(path)` is `True`, and
   raises `ReaderDetectionError` if none or multiple do.
7. End-to-end test on the synthetic fixture: `convert_file(...)`
   produces a `.hspy` file that loads back with shape `(4, 3, 16)` and
   the AXIOMM metadata namespace intact.
8. Importing `workflows.py` and `writers/hspy.py` does not pull in
   tkinter; the side-effect tests from all earlier chunks still pass.
9. `pytest` is green overall, both with and without HyperSpy
   installed (HyperSpy-requiring tests use `pytest.importorskip`).

**Out of scope for Chunk 5.**

* Manifest writer (`<output>.axiomm.json`) — Chunk 7.
* `convert_many` — Chunk 6.
* CLI entry point — Chunk 6 (blocked on the UX-layout decision).
* Real lazy execution — still future.
* Full plugin registry (entry points) — Phase 3.
* Provenance classification (observed vs. inferred vs. assumed) — Chunk 7.

**New files (expected):**

* `src/axiomm/io/converters/signals/hyperspy_builder.py` —
  `HyperSpyBuilder` class implementing `SignalBuilder`, plus the
  convenience function `build_hyperspy_signal(payload)`.
* `src/axiomm/io/converters/signals/validation.py` — `validate_axes(...)`
  helper used by the builder (spec §8.6).
* `tests/io/converters/test_hyperspy_builder.py` — tests covering:
  - signal-kind resolution (`signal1d`, `signal2d`, `auto`, `base`);
  - axis count vs. `data.ndim`;
  - axis sizes vs. data shape;
  - axis name/units/scale/offset propagation;
  - **HyperSpy axis-order correctness** — given a payload with
    `AxisSpec.index_in_array=(0=x, 1=y, 2=Energy)`, the resulting
    HyperSpy `axes_manager` must label the axes correctly *despite*
    HyperSpy reversing navigation-axis order relative to numpy;
  - metadata namespacing under `signal.metadata.AXIOMM`;
  - real-file round-trip with `XRMMapH5Reader → HyperSpyBuilder` on
    the smallest local XRM file
    (`IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5`).

**Acceptance criteria for Chunk 4:**

1. `HyperSpyBuilder().build(payload)` returns a `hs.signals.Signal1D`
   for `signal_kind="signal1d"`, `Signal2D` for `"signal2d"`,
   `BaseSignal` for `"base"`, and auto-infers from the count of signal
   axes when `signal_kind="auto"`.
2. Axis validation raises `SignalValidationError` when:
   - the number of `AxisSpec` entries does not match `data.ndim`;
   - any axis size does not match the corresponding data dimension;
   - the number of signal axes is wrong for the chosen signal kind.
3. Axis names, units, scales, and offsets propagate correctly into
   the HyperSpy `axes_manager`, with the navigation/signal split
   determined by `AxisSpec.role` and the array-order mapping driven by
   `AxisSpec.index_in_array` (not by tuple position).
4. `payload.metadata`, `payload.original_metadata`, `payload.title`,
   `payload.provenance`, and `payload.diagnostics` are all preserved on
   the resulting signal under a stable `signal.metadata.AXIOMM`
   namespace.
5. End-to-end test against the local real XRM file produces a
   `Signal1D` whose `axes_manager` has the expected x / y / Energy
   axes in the correct positions (this is the test that catches the
   prototype's axis-labelling bug).
6. Importing `axiomm.io.converters.signals.hyperspy_builder` does not
   pull in tkinter; all earlier side-effect tests still pass.
7. Tests are skipped cleanly with `pytest.importorskip("hyperspy")` when
   HyperSpy is not installed.
8. `pytest` is green overall.

**Out of scope for Chunk 4.**

* No writer (Chunk 5).
* No workflow orchestration (Chunk 5).
* No registry (Phase 1+).
* No alternative builder backends (xarray, RosettaSciIO, etc.) — the
  `SignalBuilder` protocol is already in place; new builders ship as
  separate chunks when needed.

**Dependency note.** Chunk 4 introduces `hyperspy` as a real runtime
dependency. Install with `pip install -e ".[dev,hyperspy]"` (or `[all]`).
HyperSpy's reversed axis convention vs. numpy is the *single biggest
risk* in this chunk — invest the time to assert axis labels and sizes
explicitly against the constructed `axes_manager`, not just against the
payload's `AxisSpec` tuple.

## Verifying the current state (after Chunk 4)

In an environment with Python ≥ 3.10 and the dev extras installed, the
canonical chunk-verification commands are:

```bash
cd /home/francesco/Desktop/research/axiomm
python -m pip install -e ".[dev,all]"
pytest -q
```

Expected result: **108 tests pass**, 0 fail. With `h5py` only (no
hyperspy): 82 pass, 26 skipped. With neither: 23 pass, the rest skipped.

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
* **Documentation tooling.** Initial choice is the **GitHub wiki**, seeded
  with `Home`, `Tools`, `Converter`, `Converter-Architecture`, `Roadmap`,
  `Development`, `Specification`, `Glossary` plus `_Sidebar` / `_Footer`.
  Live at <https://github.com/FrancescoPerrone/axiomm/wiki>. Wiki pages
  live in a separate git repo (`axiomm.wiki.git`) and must be edited there,
  not in `docs/`. Heavier tooling (Sphinx / MkDocs with API autodoc) is
  still on the table for later, once the public API stabilises.

## Notes for resuming work

* If `pyproject.toml` was edited to add the CLI entry point earlier than
  Chunk 6, revert — the chunk plan keeps things working in order.
* The synthetic HDF5 fixture in Chunk 3 should live at
  `tests/io/converters/fixtures.py` and produce a `(4, 3, 16)` array per
  spec §20.1.
* When implementing Chunk 4 (HyperSpy builder), use the real
  `IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5` at
  `/home/francesco/Desktop/research/melts/data/Maps-HDF5/` (≈ 950 KB,
  smallest available) to verify axis order matches the prototype's output.
  Do **not** commit that file or any other real `.h5` to the repo.
