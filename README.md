# AXIOMM

**AXIOMM** — *Automated X-ray Intelligence for Organising Mineral Mapping* —
is a Python package for spectroscopy.

> ⚠️ **Status: pre-alpha.** A full description of AXIOMM — its goals,
> analyses, workflows, and user-facing APIs — will be added by the author
> as the package matures. This README is intentionally a placeholder for
> the package-level description.

## Tools

This section lists the tools currently available inside AXIOMM. It is the
right place to document each tool's purpose, scope, and entry points.

### Converter (`axiomm.io.converters`)

The converter is a small utility for turning instrument-specific data files
into analysis-ready signal objects. It is the first tool implemented in
AXIOMM. It is **not** what AXIOMM is for — it is one of the package's
utilities.

**What it does today.** The first concrete reader handles XRM-map style
HDF5 files (the prototype's original target). The first concrete signal
builder targets [HyperSpy](https://hyperspy.org); the first concrete writer
saves `.hspy`.

**Why it is designed the way it is.** The converter is intentionally split
into pluggable pieces so future formats and backends drop in alongside,
rather than replacing, the originals:

- **Readers** (`axiomm.io.converters.readers`) — format-specific. HDF5 is
  one possible source format; others can be added later.
- **Signal builders** (`axiomm.io.converters.signals`) — backend-specific.
  HyperSpy is one possible backend; xarray, RosettaSciIO dicts, plain
  numpy, etc. can be added later.
- **Writers** (`axiomm.io.converters.writers`) — output-specific.
- A neutral, backend-agnostic in-memory model
  (`axiomm.io.converters.models.AxiommSignalPayload`) is what travels
  between readers and builders, so the four components stay decoupled.

**How to use it.** The converter is being implemented incrementally; the
intended public surface is documented in `docs/specs/converter_tool_spec.md`
and `docs/user/` (to be populated as features land). The current chunk in
progress is tracked in `docs/dev/STATE.md`.

**Package layout for the converter.**

```text
src/axiomm/
  io/
    converters/
      models.py         neutral signal payload + conversion result
      errors.py         exception hierarchy
      readers/          Reader protocol + concrete readers
      signals/          SignalBuilder protocol + concrete builders
      writers/          Writer protocol + concrete writers
```

## Installation (development)

AXIOMM requires Python **3.10+**.

```bash
# from the repository root
python -m pip install -e ".[dev]"
```

For the HDF5 reader and the HyperSpy backend, install the corresponding
extras:

```bash
python -m pip install -e ".[dev,hdf5,hyperspy]"
# or
python -m pip install -e ".[dev,all]"
```

## Running the tests

```bash
pytest
```

## Documentation

- **Wiki**: <https://github.com/FrancescoPerrone/axiomm/wiki> — public
  documentation entry point (Home, Tools, Converter, Architecture,
  Roadmap, Development, Specification, Glossary).
- `docs/specs/converter_tool_spec.md` — authoritative specification for the
  converter tool. (For the converter only; not a description of AXIOMM as
  a whole.)
- `docs/dev/STATE.md` — current development state, chunk log, and the next
  task to pick up.
- `docs/user/` — user-facing documentation, populated as features land.

## Licence

AXIOMM is released under the **PolyForm Noncommercial License 1.0.0**.
Free for research, teaching, and other noncommercial use; commercial use
requires a separate licence — see `LICENSE` and contact the author.

## Author

Francesco Perrone.
