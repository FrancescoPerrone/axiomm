# AXIOMM — guidance for AI coding agents

This file is the entry point for any AI coding agent (Claude Code, Codex, etc.)
that is asked to work on the AXIOMM repository. **Read this entire file before
making any change.**

## What AXIOMM is

AXIOMM is a Python package for scientific microscopy and spectroscopy data
conversion and analysis. The author and sole owner of the package is
**Francesco Perrone**. The package is under active development.

The first tool being built inside AXIOMM is a **converter** for XRM-map style
HDF5 files into HyperSpy `.hspy` signals. The converter is intentionally
designed as a pluggable system (format-agnostic readers, backend-agnostic
signal builders, pluggable writers) so future formats and backends can be
added without touching the core.

## Authoritative documents

Read these before changing code:

1. `docs/specs/converter_tool_spec.md` — the full refactoring specification for
   the converter tool. **This is the source of truth for module layout,
   function signatures, defaults, error classes, and acceptance criteria.**
2. `docs/dev/STATE.md` — the current development state. Lists chunks done,
   what the next chunk is, its acceptance criteria, and any open decisions.
3. `README.md` — short package description and dev install instructions.

If `docs/dev/STATE.md` disagrees with `docs/specs/converter_tool_spec.md`,
trust the spec for *what* to build and `STATE.md` for *what's next* in the
working sequence.

## Working agreement

Francesco wants development driven as **small, self-contained, committable
chunks**. After each chunk:

1. Verify the chunk's acceptance criteria pass (run the relevant tests).
2. Commit the chunk with a clean conventional commit message.
3. **Update `docs/dev/STATE.md`** to record what was done and what's next.
4. Stop and hand back to Francesco.

This lets him pause and resume the work across sessions and across machines.

## Hard constraints

These must be honoured by every contributor, human or AI:

- **No Claude / AI co-author attribution.** Do not add
  `Co-Authored-By: Claude …` or any "Generated with Claude Code" footer to
  commits, PR bodies, code headers, docstrings, `README` contributor sections,
  `CITATION.cff` authors, `ACKNOWLEDGEMENTS.md`, or `pyproject.toml`
  authors. Commit messages should be clean conventional commits — nothing
  more. Francesco owns the package and will publish under his name only.
- **Headless core, UX on top.** The four core converter components
  (discovery, readers, signal builders, writers) must never import Tkinter,
  call `input()`, print on import, or open windows. UX adapters (CLI,
  notebook helpers, Tk dialogs) wrap the core; they are never imported by it.
  See spec §10 and §24 acceptance criteria.
- **Default to generality.** When adding a reader/builder/writer, also add or
  honour a protocol/ABC so future formats and backends plug in alongside
  rather than replacing. HyperSpy is one possible signal backend, not an
  assumption baked into the package. HDF5 is one possible source format, not
  an assumption baked into the package.
- **Preserve current XRM-map conversion defaults**, but expose them as
  configuration rather than hidden magic numbers (spec §17, §24 criterion 13).
- **Scientific-data safety.** Never silently overwrite outputs. Never raise a
  generic `Exception` from a public function. Missing optional metadata is a
  diagnostic, not a crash. Missing required metadata is an explicit, named
  exception.
- **Licence header inconsistency in the prototype is a known release blocker
  (spec §18).** The new package is licensed under **PolyForm Noncommercial
  1.0.0**; do not reintroduce MIT headers in new source files.

## Environment

- Python **3.10+**. The user's `xrf` conda environment is Python 3.9 and is
  too old; use the system Python 3.11 or a fresh `>=3.10` environment for
  development.
- `pip install -e ".[dev,all]"` from the repo root sets everything up.
- `pytest` runs the test suite. Pytest is configured via `pyproject.toml`
  (`testpaths = ["tests"]`, `pythonpath = ["src"]`).

## Where reference material lives

- The original prototype that the converter refactor replaces is preserved at
  `docs/specs/_legacy/converter_prototype.py`. It is reference material only —
  it is *not* the public implementation and its licence header (MIT + special
  clause) is part of the blocker described in spec §18.

## When in doubt

- Ask Francesco before changing scope. The chunk boundaries in
  `docs/dev/STATE.md` are deliberate.
- Prefer reading the spec over inferring intent from code.
- Prefer adding tests before changing behaviour.
