# AXIOMM — development state

> **Read this file first if you are resuming AXIOMM development in a new
> session.** It is the single source of truth for what has been done, what
> the next chunk is, and which decisions have been made.
> See `CLAUDE.md` at the repo root for the working agreement and hard
> constraints, and `docs/specs/converter_tool_spec.md` for the authoritative
> specification.

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
| 2 | `discover_inputs` (§6) + unit tests                                  | ⬜ next    |
| 3 | `XRMMapH5Reader` (§7) + synthetic HDF5 fixture (§20.1) + tests       | ⬜ pending |
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

## Current state (as of Chunk 1)

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
* `tests/io/converters/test_import_has_no_side_effects.py` — guards spec
  §24.1 (silent import) plus a "models stay backend-neutral" check.
* `pyproject.toml` with src-layout, `requires-python = ">=3.10"`, optional
  extras for `hdf5`, `hyperspy`, `all`, `notebook`, `dev`. Pytest configured
  with `pythonpath = ["src"]` so tests run without an install.
* `LICENSE` — PolyForm Noncommercial 1.0.0 (decision made in Chunk 1; see
  *Open decisions* below if you want to revisit).
* `README.md` — short package summary, dev install, licence note.
* `CLAUDE.md` at repo root — hard constraints and working agreement.
* `docs/specs/converter_tool_spec.md` — the authoritative spec (copy of the
  original from `docs_refactoring/`).
* `docs/specs/_legacy/converter_prototype.py` — the original converter
  prototype, reference-only. **Do not import or extend it from package code.**
* `.gitignore` tuned for Python + scientific scratch outputs.

What does **not** yet exist (deferred to later chunks):

* Any concrete reader, builder, writer, or workflow function.
* The `discovery.py`, `workflows.py`, and `registry.py` modules.
* The CLI entry point (commented out in `pyproject.toml`).
* The `ux/` subpackage (CLI, notebook, Tk dialogs).
* User-facing documentation under `docs/user/`.
* `CITATION.cff` and `ACKNOWLEDGEMENTS.md`.

## Next chunk: Chunk 2 — `discover_inputs`

**Goal.** Implement spec §6 in full: a pure pathlib-based input resolver that
takes a file or directory and returns a deterministic list of input paths,
with extension filtering, substring sample filtering, and optional recursion.
No HDF5 logic. No GUI.

**New files (expected):**

* `src/axiomm/io/converters/discovery.py` — `discover_inputs(...)`.
* `tests/io/converters/test_discovery.py` — at least the two cases named in
  spec §20.2 (`test_discover_single_file`,
  `test_discover_directory_sample_filter`) plus tests for: no matches +
  `require_non_empty=True` raising `InputDiscoveryError`; case-insensitive
  extension matching; deterministic ordering; recursive vs. non-recursive.

**Acceptance criteria for Chunk 2:**

1. `discover_inputs(file_path)` returns `[file_path]` if the file exists.
2. `discover_inputs(dir_path, extensions=(".h5",), sample="A21_054")` returns
   only matching files, sorted, deterministic across runs.
3. `discover_inputs(...)` raises `InputDiscoveryError` (not a generic
   exception) when no files match and `require_non_empty=True`.
4. Extensions are matched case-insensitively.
5. `recursive=True` walks subdirectories; `recursive=False` does not.
6. `discover_inputs` never opens any HDF5 file, never imports `h5py`, never
   imports `tkinter`, never prints, never calls `input()`.
7. The "no side effects on import" test from Chunk 1 still passes.
8. New tests pass, plus `pytest` overall is green.

**Out of scope for Chunk 2.** No regex filtering yet — substring only.
Spec §6.4 says "the implementation should allow future regex matching",
meaning leave the door open in the signature, not implement it now.
No registry integration yet. No reader auto-detection.

## Verifying Chunk 1

In an environment with Python ≥ 3.10 and the dev extras installed, the
canonical chunk-verification commands are:

```bash
cd /home/francesco/Desktop/research/axiomm
python -m pip install -e ".[dev]"
pytest -q
```

Expected result: 5 tests pass, 0 fail.

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
* **Documentation tooling.** Not yet chosen (Sphinx vs. MkDocs vs. just a
  GitHub wiki). Decide before Chunk 7/8 when the docs surface starts to grow.

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
