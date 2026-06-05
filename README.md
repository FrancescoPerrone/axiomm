# AXIOMM

**AXIOMM** is a Python package for scientific microscopy and spectroscopy data
conversion and analysis.

> ⚠️ **Status: pre-alpha.** The package is under active design and only the
> converter scaffolding is in place. Public API may change without notice.

## What is AXIOMM?

AXIOMM aims to provide:

- robust readers for instrument-specific data formats (initial focus: XRM-map
  style HDF5);
- a neutral, backend-agnostic in-memory model for high-dimensional scientific
  signals;
- pluggable builders that turn that neutral model into analysis-ready signal
  objects (initial backend: [HyperSpy](https://hyperspy.org));
- writers and conversion manifests for reproducible scientific pipelines;
- composable CLI, notebook, and (optional) GUI helpers built on top of a
  headless core library.

The first tool delivered as part of AXIOMM is a **converter** that takes
XRM-style `.h5` maps and produces HyperSpy `.hspy` signals while preserving
provenance and metadata.

## Package layout

```text
src/axiomm/
  io/
    converters/
      models.py         neutral signal payload + conversion result
      errors.py         exception hierarchy
      readers/          format-specific readers (Reader protocol + impls)
      signals/          signal builders (SignalBuilder protocol + impls)
      writers/          output writers (Writer protocol + impls)
```

Concrete readers, builders, writers, the workflow orchestrator, the CLI, the
notebook helpers and the optional Tk dialogs are added incrementally — see
`docs/dev/STATE.md` for current progress.

## Installation (development)

AXIOMM requires Python **3.10+**.

```bash
# from the repository root
python -m pip install -e ".[dev]"
```

For the HDF5 reader and the HyperSpy backend, install the corresponding extras:

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

- `docs/specs/converter_tool_spec.md` — authoritative refactoring specification
  for the converter tool.
- `docs/dev/STATE.md` — current development state, chunk log, and the next
  task to pick up.
- `docs/user/` — user-facing documentation (populated as features land).

## Licence

AXIOMM is released under the **PolyForm Noncommercial License 1.0.0**.
Free for research, teaching, and other noncommercial use; commercial use
requires a separate licence — see `LICENSE` and contact the author.

## Author

Francesco Perrone.
