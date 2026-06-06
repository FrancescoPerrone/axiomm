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
| 3 | `XRMMapH5Reader` (§7) + synthetic HDF5 fixture (§20.1) + tests       | ⬜ next    |
| 4 | `HyperSpyBuilder` (§8) + axis-order tests                            | ⬜ pending |
| 5 | `HSpyWriter` (§9.4) + `convert_file` (§11.2) + end-to-end test       | ⬜ pending |

### Phase 1 — usability

| # | Chunk                                                                | Status     |
|---|----------------------------------------------------------------------|------------|
| 6 | CLI `axiomm-convert` (§10.4) + `convert_many` + CLI tests            | ⬜ pending |
| 7 | Manifest writer (§9.5) + logging (§14) + provenance metadata (§15)   | ⬜ pending |
| 8 | Optional Tk dialogs (§10.5) + notebook helpers (§10.6)               | ⬜ pending |

### Phase 2 / 3 — configurability and extensibility

Tracked in spec §23. Pick up after Phase 1 lands.

## Current state (as of Chunk 2)

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

* Any concrete reader, builder, writer, or workflow function.
* The `workflows.py` and `registry.py` modules.
* The CLI entry point (commented out in `pyproject.toml`).
* The `ux/` subpackage (CLI, notebook, Tk dialogs).
* User-facing documentation under `docs/user/`.
* `CITATION.cff` and `ACKNOWLEDGEMENTS.md`.

## Next chunk: Chunk 3 — `XRMMapH5Reader` + synthetic HDF5 fixture

**Goal.** Implement spec §7 in full: the first concrete reader, plus the
synthetic-HDF5 test fixture from spec §20.1. The reader opens XRM-map style
HDF5 files and returns a populated `AxiommSignalPayload`, with all
scientific defaults parameterised through a frozen `XRMMapH5Config`
dataclass and missing optional metadata surfaced as `Diagnostic`s.

**New files (expected):**

* `src/axiomm/io/converters/readers/xrmmap_h5.py` — `XRMMapH5Reader` class
  (implementing the `Reader` protocol), `XRMMapH5Config` dataclass with
  spec §17 defaults, and helpers `decode_hdf5_string`,
  `decode_hdf5_string_array`, `parse_micrometre_value`.
* `tests/io/converters/fixtures.py` — synthetic-HDF5 builder helper that
  produces a minimal valid XRM-map file with shape `(4, 3, 16)`:
  `/xrmmap/mcasum/counts`, `/xrmmap/config/environ/{name,value}`,
  `/xrmmap/config/rois/{name,limits}`.
* `tests/io/converters/test_xrmmap_h5_reader.py` — the reader tests named
  in spec §20.2 plus the helper tests.

**Acceptance criteria for Chunk 3:**

1. `XRMMapH5Reader().read(path)` returns an `AxiommSignalPayload` whose
   axes match the data shape, `signal_kind == "signal1d"`, and whose
   `metadata` / `original_metadata` are populated from the HDF5 file.
2. Default `XRMMapH5Config` values match spec §17 (counts path, environ
   paths, ROI paths, beam-size key, `energy_scale = 40.96 / 4096`,
   `roi_limit_scale = 0.01`, `fallback_field_width_um = 500.0`).
3. `parse_micrometre_value` accepts the variants listed in spec §7.7
   (`"1um"`, `"1 um"`, `"1 µm"`, `"1 μm"`, `"1.0um"`, `"1.0 micrometer"`,
   `"1.0 micrometre"`) and raises `MetadataParseError` on malformed input.
4. `decode_hdf5_string` / `decode_hdf5_string_array` handle the variants
   listed in spec §7.6 (bytes, fixed-width byte strings, null-padded byte
   strings, NumPy bytes arrays, already-decoded strings).
5. Missing `/xrmmap/mcasum/counts` raises `DatasetNotFoundError` clearly.
6. Missing ROI metadata emits a `Diagnostic` but still produces a payload
   (spec §7.8).
7. Missing beam-size config emits a `Diagnostic` and falls back to
   `fallback_field_width_um` when configured (spec §7.8).
8. Importing `axiomm.io.converters.readers.xrmmap_h5` does not pull in
   tkinter; the side-effect tests from Chunks 1 and 2 still pass.
9. `pytest` is green overall.

**Out of scope for Chunk 3.**

* No HyperSpy build (Chunk 4).
* No writer (Chunk 5).
* No registry registration (Chunk 5+).
* No real-file tests — synthetic fixture only. Real-file validation lives
  in Chunk 4 once the builder exists.
* `lazy=True` may keep the dataset as an `h5py.Dataset` reference but
  does not need a full lazy-graph implementation; whatever choice is made
  must be documented in a `Diagnostic` and a docstring.

**Dependency note.** Chunk 3 introduces a real runtime dependency on
`h5py`. Either install it via `pip install -e ".[hdf5,dev]"` before
running the reader tests, or mark them with
`pytest.importorskip("h5py")` so a `h5py`-free environment still passes
the rest of the suite. The latter is preferred for the existing
side-effect tests; the former for the new reader tests.

## Verifying the current state (after Chunk 2)

In an environment with Python ≥ 3.10 and the dev extras installed, the
canonical chunk-verification commands are:

```bash
cd /home/francesco/Desktop/research/axiomm
python -m pip install -e ".[dev]"
pytest -q
```

Expected result: **23 tests pass**, 0 fail.

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
