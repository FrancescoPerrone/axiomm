# AXIOMM

**AXIOMM** — *Automated X-ray Intelligence for Organising Mineral Mapping* —
is a Python package for spectroscopy.

```{warning}
**Pre-alpha.** AXIOMM is under active development. Public APIs may change
without notice. This documentation tracks the state of `main`; for the
current roadmap and milestone state see the
[Roadmap](https://github.com/FrancescoPerrone/axiomm/wiki/Roadmap) in the wiki.
```

## What's in AXIOMM today

AXIOMM is built as a collection of focused tools. Usable end-to-end today:

- **{doc}`Converter <user/converter>`** — `axiomm.io.converters`. Reads
  instrument-specific data files (XRM-map style HDF5 and Bruker `.bcf`) and
  produces analysis-ready HyperSpy signals via a single call:

  ```python
  from axiomm.io.converters import convert_file

  result = convert_file(
      input_path="A21_054_map.h5",
      output_path="A21_054_map.hspy",
      reader="xrmmap_h5",   # or "auto"
  )
  ```

- **{doc}`Analysis suite & pipeline <user/analysis>`** — `axiomm.analysis.*`
  and the one-call `axiomm.Pipeline` front door: decomposition (PCA/UMAP),
  clustering (GMM/HDBSCAN), peak identification, theoretical Cliff-Lorimer
  quantification with a reliability gate, exploratory mineral matching, and a
  self-contained HTML report. See the guide for runnable examples.

## Read this if you hit something surprising

Before debugging, check **{doc}`Known issues <user/known_issues>`**. It
documents the user-facing traps AXIOMM either guards against or wants
you to know about up front — including the silently-swapped x/y axis
labels in `.hspy` files produced by the legacy prototype.

## Installation

```bash
pip install -e ".[hdf5,hyperspy]"
# or a full dev setup (common runtime + dev tools + docs + UMAP)
pip install -e ".[dev,all,umap,docs]"
```

AXIOMM requires Python ≥ 3.10. Backends are optional extras so the package
stays installable in environments that only need a subset. `[all]` is the
common scientific runtime; `[quant]` (xraylib, usually conda-only), `[umap]`,
and `[vtk]` are heavier/fragile extras added explicitly — see the README's
installation table.

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
user/analysis
user/known_issues
```
