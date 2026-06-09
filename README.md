<p align="left">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="identy/AXIOMM_Design/axiomm_wave_lockup_dark.svg">
    <img src="identy/AXIOMM_Design/axiomm_wave_lockup.svg" alt="AXIOMM" width="360">
  </picture>
</p>

**AXIOMM** — *Automated X-ray Intelligence for Organising Mineral Mapping* — is a
Python package for spectroscopy. It targets workflows that begin with
high-dimensional X-ray spectroscopy data acquired as spatial maps (one
energy spectrum per point on the sample) and produce analysis-ready,
provenance-tracked signal objects suitable for downstream quantitative
work.

> ⚠️ **Status: pre-alpha.** Public API may change without notice. A
> full description of AXIOMM — its analyses, workflows, and
> user-facing APIs — will be added by the author as the package
> matures.

## Scientific scope

AXIOMM converts and structures X-ray spectroscopy maps. A typical
input is a 3-D dataset $C \in \mathbb{Z}^{x \times y \times n}$ where
$x,y$ index spatial pixels on the sample and $n$ indexes MCA channels
of an energy-dispersive detector. The channel-$i$ energy is
$E_i = E_\text{scale} \cdot i + E_0$, with $E_\text{scale}$ the
detector gain (keV / channel) — configurable per file. Each
$(x, y)$ pixel carries the spectrum $\{C_{xy0}, C_{xy1}, \dots, C_{xy(n-1)}\}$
from which element abundances can be quantified downstream.

The package is currently focused on the **XRM-Map / Larch** HDF5
layout (a 3-D `(x, y, channel)` counts dataset alongside an
`environ` configuration table and an ROI-limits table). The
architecture is pluggable end-to-end — readers, signal builders, and
writers are protocols, not a hard-wired pipeline — so additional
instrument formats and analysis backends drop in alongside the
existing ones rather than replacing them.

## What's in AXIOMM today

One tool, exposed at `axiomm.io.converters`. It

* reads an XRM-Map HDF5 file and extracts the counts dataset, the
  environ configuration table, and the ROI table (3-D `(n_rois,
  n_variants, 2)` shape included);
* assembles a backend-neutral in-memory **`AxiommSignalPayload`** —
  data, axis specs, source provenance, diagnostics, and a
  three-bucket *observed / inferred / assumed* metadata
  classification per spec §15;
* builds a HyperSpy `Signal1D` from the payload, with axes labelled
  correctly under HyperSpy's reversed `axes_manager` convention (the
  legacy prototype's silent *x / y* swap is fixed — see the wiki
  [Known Issues](https://github.com/FrancescoPerrone/axiomm/wiki/Known-Issues));
* writes the result as a `.hspy` file plus an `<output>.axiomm.json`
  sidecar manifest (schema v2) that records the input/output paths,
  the reader's configuration, the axes summary, every diagnostic,
  and the provenance classification. The manifest mirrors
  `signal.metadata.AXIOMM` so the in-memory and on-disk views agree
  exactly.

### One-call end-to-end example

```python
from axiomm.io.converters import convert_file

result = convert_file(
    input_path="A21_054_map.h5",
    output_path="A21_054_map.hspy",
    reader="xrmmap_h5",   # or "auto" — the registry picks
)

print(result.output_path)        # PosixPath('A21_054_map.hspy')
print(result.manifest_path)      # PosixPath('A21_054_map.hspy.axiomm.json')
for d in result.diagnostics:
    print(f"[{d.severity}] {d.code}: {d.message}")
```

The output `.hspy` loads back through HyperSpy with the full AXIOMM
metadata namespace intact:

```python
import hyperspy.api as hs

signal = hs.load("A21_054_map.hspy")
print(signal.metadata.AXIOMM.converter.reader)   # 'xrmmap_h5'
print(signal.metadata.AXIOMM.source.path)        # original .h5 path
print(signal.axes_manager)                       # x, y in µm; Energy in keV
```

## Tools

Per the AXIOMM convention each tool lives under its own subpackage:

| Tool      | Module                    | Status                                           |
|-----------|---------------------------|--------------------------------------------------|
| Converter | `axiomm.io.converters`    | Phases 0–2 complete; reader registry (Phase 3.1) in place. CLI / notebook helpers still blocked on a UX-layout decision. |

## Installation (development)

AXIOMM requires Python **3.10+**.

```bash
python -m pip install -e ".[dev]"
```

For the HDF5 reader and the HyperSpy backend:

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

- **Wiki**: <https://github.com/FrancescoPerrone/axiomm/wiki> —
  landing pages, architecture, known issues, glossary.
- **Sphinx user guide + API reference**: `docs/`. Build locally with
  `cd docs && make html`. The same Sphinx project is wired to both
  GitHub Pages (`.github/workflows/docs.yml`) and Read the Docs
  (`.readthedocs.yaml`); Pages deployment is opt-in via the
  *Actions → docs → Run workflow* button.
- **Converter specification**:
  `docs/specs/converter_tool_spec.md` — the authoritative design
  document for the converter tool.
- **Development state**: `docs/dev/STATE.md` — chunk-by-chunk
  progress, blockers, and the next planned move.

## Licence

**PolyForm Noncommercial 1.0.0.** Free for research, teaching, and
other noncommercial use; commercial use requires a separate licence
— see `LICENSE` and contact the author.

## Author

Francesco Perrone.
