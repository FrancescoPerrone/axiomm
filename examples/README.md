# AXIOMM examples

Runnable proof-of-concept scripts. Install the extras they need:

```bash
pip install -e ".[all,quant,viz]"
```

## `phase_map_demo.py` — spectra → mineral phase map

Runs the full stage-two pipeline end to end and renders the output AXIOMM is
built for — a **mineral phase map** — beside each intermediate step:

```bash
python examples/phase_map_demo.py
# -> examples/output/axiomm_phase_map_demo.png
```

![AXIOMM phase-map proof of concept](output/axiomm_phase_map_demo.png)

**The scene** is a petrographic texture, not a test pattern: an interlocking
Voronoi grain mosaic at a realistic modal abundance, a cross-cutting apatite
vein, and a compositionally **zoned olivine phenocryst** (forsterite core,
fayalitic rim).

**Pipeline shown:** synthetic X-ray map → PCA decomposition → GMM clustering →
per-cluster mean spectra → peak net intensities → theoretical Cliff-Lorimer
k-factors → element/oxide wt% → reliability gate → **mineral matching** →
phase map. The recovered phase map reproduces the grain mosaic and the vein,
and — notably — resolves the phenocryst's **zoning** into separate Forsterite
(core) and Fayalite (rim) phases (see the two olivine spectra: Mg-dominant vs
Fe-dominant). A matched modal-mineralogy bar chart gives a quantitative read-out.

**About the data.** Real hyperspectral geology maps are large and not
pip-installable, so the *spatial texture is simulated* while the *chemistry is
real and open*: every phase is drawn from the basis-audited
`MINERALOGY_DEFAULT_V2` endmembers (idealised formulae plus GeoReM/EPMA-derived
standards). Per-pixel peak areas are placed as `sensitivity × mass_fraction` so
the **actual** Cliff-Lorimer quantifier recovers the input chemistry — the real
pipeline runs; only the input image is synthetic. It is a proof of concept, not
measured data. **Standards validation remains mandatory** before any
quantitative-accuracy or validated mineral-identification claim.

> Want it run on a *real* open dataset instead of a synthetic texture? Point me
> at a redistributable source (e.g. a CC-licensed EDS/EPMA map on Zenodo) and I
> can wire an adapter — real hyperspectral maps just aren't pip-installable, so
> they can't be bundled here.
