# AXIOMM examples

Runnable demonstrations. Install the extras they need:

```bash
pip install -e ".[all,quant,viz]"
```

Two clearly separate kinds of demo:

| Script | Kind | What it establishes |
|---|---|---|
| `phase_map_demo.py` | **synthetic self-consistency integration demo** | the pipeline stages fit together and are deterministic — **not** accuracy |
| `bcf_inspect.py` | **real-data** (STEM-EDS `.bcf`) | inspects a real Bruker spectrum image: facts, provenance, quick-look |
| `bcf_pipeline.py` | **real-data** (STEM-EDS `.bcf`) | runs the full pipeline on real measured data; abstains when chemistry is out of reference scope |
| `nist_pgm_realdata.py` | **real-data** (SEM/EDS, NIST) | downloader + inspection for the NIST PGM set (blocked upstream; see REALDATA.md) |

The synthetic and real-data demos are kept deliberately separate in code and
claims. Real datasets and every generated output stay **outside** the git
repository (licence + size).

---

## `phase_map_demo.py` — synthetic self-consistency integration demo

Runs the whole stage-two pipeline end to end on a **synthetic** map and renders
a mineral phase map beside each step:

```bash
python examples/phase_map_demo.py
# -> examples/output/axiomm_phase_map_demo.png
```

![AXIOMM synthetic self-consistency phase map](output/axiomm_phase_map_demo.png)

**The scene** is a petrographic texture, not a test pattern: an interlocking
Voronoi grain mosaic at a realistic modal abundance, a cross-cutting apatite
vein, and a compositionally zoned olivine phenocryst (forsterite core, fayalitic
rim).

**Pipeline exercised:** synthetic X-ray map → PCA → GMM clustering → cluster
mean spectra → peak net intensities → theoretical Cliff-Lorimer k-factors →
element/oxide wt% → reliability gate → mineral matching → phase map. The
recovered phase map reproduces the grain mosaic and vein and resolves the
phenocryst's zoning into separate Forsterite (core) and Fayalite (rim) phases;
a modal-area-fraction bar chart summarises the result.

**This is a self-consistency check, not validation.** The observations are
*generated* from the same reference compositions and fluorescence sensitivities
the quantifier and matcher later use, so recovering the input phases shows the
stages are internally consistent — it says nothing about measurement accuracy.
The reference *compositions* are scientifically grounded (idealised formulae +
GeoReM/EPMA-derived standards in `MINERALOGY_DEFAULT_V2`), but the *spectra
generated from them are synthetic observations*, not real chemistry, and the
modal fractions are **not** a standards-validated measurement. **Standards
validation remains mandatory** before any quantitative-accuracy or validated
mineral-identification claim. It doubles as a deterministic round-trip
integration test (`tests/analysis/test_phase_map_demo_integration.py`).

---

## `bcf_inspect.py` / `bcf_pipeline.py` — real STEM-EDS Bruker `.bcf`

Ingest a **real** STEM-EDS spectrum image (an open Bruker `.bcf`) via the
pluggable `bruker_bcf` reader — the same reader `convert_file` auto-detects.
`bcf_inspect.py` records the file's facts, provenance and a quick-look; then
`bcf_pipeline.py` runs the genuine pipeline (read → PCA → GMM → cluster spectra
→ peaks). Both are opt-in and gated by `AXIOMM_REALDATA_BCF`:

```bash
pip install -e ".[all,quant,viz]"
export AXIOMM_REALDATA_BCF=/abs/path/EDS_dataset.bcf
python examples/bcf_inspect.py "$AXIOMM_REALDATA_BCF"
python examples/bcf_pipeline.py "$AXIOMM_REALDATA_BCF"
pytest -m realdata            # opt-in; skips cleanly without the env var / data
```

This is **real-data pipeline evidence, not standards-based validation**: it is
STEM (not SEM), materials science (not mineral ground truth), and its chemistry
is outside AXIOMM's silicate/oxide reference — so quantification and mineral
matching **abstain**, which is the correct outcome. The `.bcf` is GPL-3.0; the
binary and all outputs are kept outside the repository. See `examples/REALDATA.md`.

## `nist_pgm_realdata.py` — SEM/EDS (NIST PGM), download blocked upstream

Runs AXIOMM on the NIST *SEM/EDS hyperspectral data set from platinum group
mineral ore embedded in epoxy* (DOI
[10.18434/mds2-2471](https://doi.org/10.18434/mds2-2471), NIST open licence).
See `examples/REALDATA.md` for the downloader, verification, what the run does
and does **not** establish (it is pipeline testing on real data, **not**
standards-based quantitative validation), and the exact reproducible commands.
