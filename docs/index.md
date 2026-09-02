# AXIOMM

**AXIOMM** — *Automated X-ray Intelligence for Organising Mineral Mapping* —
is a Python package for spectroscopy.

```{warning}
**Pre-alpha.** AXIOMM is under active development. Public APIs may change
without notice. This documentation tracks the state of `main`; for the
current development plan and chunk-by-chunk progress see
[`docs/dev/STATE.md`](https://github.com/FrancescoPerrone/axiomm/blob/main/docs/dev/STATE.md)
in the repository.
```

## What's in AXIOMM today

AXIOMM is built as a collection of focused tools. As of Phase 0 of the
converter spec, exactly one tool is usable end-to-end:

- **{doc}`Converter <user/converter>`** — `axiomm.io.converters`. Reads
  instrument-specific data files (initial focus: XRM-map style HDF5) and
  produces analysis-ready HyperSpy signals via a single call:

  ```python
  from axiomm.io.converters import convert_file

  result = convert_file(
      input_path="A21_054_map.h5",
      output_path="A21_054_map.hspy",
      reader="xrmmap_h5",
  )
  ```

## Read this if you hit something surprising

Before debugging, check **{doc}`Known issues <user/known_issues>`**. It
documents the user-facing traps AXIOMM either guards against or wants
you to know about up front — including the silently-swapped x/y axis
labels in `.hspy` files produced by the legacy prototype.

## Installation

```bash
pip install -e ".[hdf5,hyperspy]"
# or for everything including dev tools and docs
pip install -e ".[dev,all,docs]"
```

AXIOMM requires Python ≥ 3.10. The HDF5 reader and the HyperSpy backend
are optional extras so the package stays installable in environments
that only need a subset.

## Project links

- **Repository:** <https://github.com/FrancescoPerrone/axiomm>
- **Wiki:** <https://github.com/FrancescoPerrone/axiomm/wiki>
- **Issue tracker:** <https://github.com/FrancescoPerrone/axiomm/issues>
- **Licence:** PolyForm Noncommercial 1.0.0 — free for research,
  teaching, and other noncommercial use; commercial use requires a
  separate licence from the author.

```{toctree}
:hidden:
:caption: User guide
:maxdepth: 2

user/converter
user/known_issues
```
