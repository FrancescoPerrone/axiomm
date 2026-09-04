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

**Pipeline shown:** synthetic X-ray map → PCA decomposition → GMM clustering →
per-cluster mean spectra → peak net intensities → theoretical Cliff-Lorimer
k-factors → element/oxide wt% → reliability gate → **mineral matching** →
phase map. The recovered phase map reproduces the ground-truth domains
(including the small phase inclusion), and one cluster's mean spectrum is shown
with its identified peaks.

**About the data.** Real hyperspectral geology maps are large and not
pip-installable, so the *spatial map is simulated* while the *chemistry is real
and open*: the four ground-truth phases are drawn from the basis-audited
`MINERALOGY_DEFAULT_V2` endmembers (idealised formulae plus GeoReM/EPMA-derived
standards). Peak areas are placed as `sensitivity × mass_fraction` so the
**actual** Cliff-Lorimer quantifier recovers the input chemistry — the real
pipeline runs; only the input image is synthetic. It is a proof of concept, not
measured data. **Standards validation remains mandatory** before any
quantitative-accuracy or validated mineral-identification claim.
