# Real sub-dataset readiness (paper-facing phase/composition maps)

**Status:** preparation. This document lists what must be **confirmed with the
data owner** before AXIOMM processes a real selected sub-dataset reproducibly to
generate paper-facing phase/composition maps. It fabricates **no** assumptions
about the dataset — every dataset-specific value below is a question to answer,
not a default to trust.

The overriding risk: **in the default `GENERIC` conversion mode the XRM-Map HDF5
reader will happily build an energy axis from APS legacy constants
(0.01 keV/channel, offset 0) for *any* `.h5` file**, emitting only a warning
diagnostic. A run therefore *succeeds and produces maps* even when the
calibration is wrong. For a paper we must supply explicit calibration and prefer
`STRICT` mode.

## Hard blockers — a run is wrong or impossible without these

1. **Energy scale (keV/channel).** Source-metadata extraction is *not yet
   implemented* (the `/xrmmap/config/mca_calib/*` path is deferred —
   `readers/hdf5_helpers.py:359-362`); in default mode the reader falls back to
   the APS legacy preset `0.01 keV/ch` (`readers/presets.py:135`) with only a
   warning. For any non-APS-13IDE detector this must be supplied via
   `XRMMapH5Calibration(energy_scale=...)`, or every peak identification is wrong.
   **Confirm the true per-channel width.**

2. **Energy offset (keV at channel 0).** Hardwired to `0.0` for the XRM reader
   (`readers/xrmmap_h5.py:611`) with **no override path**. If the real MCA has a
   nonzero offset the whole energy axis is shifted. **Confirm the offset is truly
   0**; if not, this is an un-plumbed gap requiring a small code change (add offset
   to `XRMMapH5Calibration`) or offset-corrected input. (BCF files get the offset
   from HyperSpy metadata, so this blocker is XRM-specific.)

3. **Beam / excitation energy (keV).** Required for quantification and the
   phase/composition maps. Default `None` → quantification, mineral matching and
   `phase_map` are **silently skipped** with a `minerals_skipped` diagnostic
   (`pipeline/core.py:80-86`); clusters and mean spectra still come out. It is
   **not** auto-read from BCF metadata. **Must be supplied** via
   `Pipeline(beam_energy_kev=...)`.

4. **Counts dataset path + array shape/orientation.** The reader hard-requires a
   3-D `(xdim, ydim, n_channels)` array at `/xrmmap/mcasum/counts`
   (`readers/hdf5_schema.py:93`, `readers/xrmmap_h5.py:377-392`). A different path
   must be given via `schema=`; a different axis order silently transposes the
   maps. **Confirm the counts path and that the axis order is (x, y, channels).**

5. **Reference library suitability.** Default `"minerals_default_v2"`
   (`pipeline/config.py:51`); `reference_element` default `"Si"` must have a line
   in the spectrum's energy range or `_quantify_and_match` raises
   (`pipeline/core.py:172-177`). **Confirm the library covers the sample's
   expected phases and the measured energy range.**

## Should confirm — a safe-ish default exists but it affects the figures

6. **Navigation pixel scale (µm).** Resolution ladder: environ beam-size key →
   `pixel_size_um` → `field_width_um/xdim` → legacy `500 µm/xdim` → 1.0 (warns).
   Wrong or absent → wrong scale bars. **Confirm pixel size / field width and the
   environ key name.**
7. **ROI limit units.** `centi_keV` / `keV` / `channel_index` (preset assumes
   `channel_index`). ROIs are stored as metadata only — not consumed by the
   analysis pipeline — so this is low priority, but confirm for a faithful manifest.
8. **Conversion mode.** Default `GENERIC` applies legacy presets with warnings.
   For a real, non-legacy dataset prefer **`STRICT`** so anything unresolved fails
   loudly instead of silently using APS constants.
9. **Memory footprint.** The whole cube is loaded into RAM eagerly and a second
   full-size `float64` `(pixels × channels)` copy is made; there is **no chunking,
   downsampling or memmap** (`readers/xrmmap_h5.py:385`, `analysis/.../reshape.py`,
   UMAP materialises too). A 512×512×4096 `int` map ≈ 4 GB raw + ~8 GB float64 copy
   → easily > 16 GB peak. **Confirm the sub-dataset dimensions; for a large map,
   pre-crop/bin to a subregion before running.**
10. **Reproducibility of custom stages.** Select stages by **name or dict**, not
    pre-built instances: if a decomposer/clusterer instance is passed, the pipeline
    seed is *not* applied (a `stage_instance_supplied` diagnostic warns). GMM is
    only deterministic when run through the Pipeline (which injects `seed`).

## Safe defaults (noted; no owner action strictly required)

- PCA and GMM are seeded to `0` through the Pipeline → reproducible.
- Missing environ / ROI / optional metadata → diagnostics, not failures.
- HDBSCAN is deterministic; UMAP is deterministic only when seeded.
- BCF axes/units/offset come straight from HyperSpy metadata (no preset guessing),
  so BCF calibration is generally trustworthy — but still pass `beam_energy_kev`
  explicitly.

## Confirm-with-owner checklist

| # | Item | Needed for | Blocker? |
|---|------|-----------|----------|
| 1 | Energy scale (keV/channel) | correct energy axis / peak IDs | **yes** |
| 2 | Energy offset (keV @ ch 0) | correct energy axis | **yes** (also code gap if ≠ 0) |
| 3 | Beam energy (keV) | any composition / phase map | **yes** |
| 4 | Counts path + (x,y,channel) order | correct, non-transposed maps | **yes** |
| 5 | Reference library + `reference_element` in range | quantification / matching | **yes** |
| 6 | Pixel size / field width (µm) + environ key | correct spatial scale | should |
| 7 | ROI limit units | faithful manifest | low |
| 8 | Conversion mode (prefer STRICT) | fail-loud on bad calibration | should |
| 9 | Sub-dataset dimensions / memory plan | avoid OOM | should |
| 10 | Stages by name/dict, seed set | reproducibility | should |

## Recommended run recipe (once the blockers are answered)

```python
from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Calibration, ConversionMode
from axiomm import Pipeline

# 1) Convert with EXPLICIT calibration in STRICT mode (fail loud on anything
#    unresolved) — values below are placeholders to be replaced by confirmed ones.
cal = XRMMapH5Calibration(energy_scale=<keV_per_channel>)   # offset currently 0-only
# ... convert_file(..., calibration=cal, mode=ConversionMode.STRICT)

# 2) Run the analysis with the confirmed beam energy and reference.
result = Pipeline(
    beam_energy_kev=<keV>,
    reference="minerals_default_v2",   # confirm coverage
    seed=0,
).run(<converted_or_payload>)

result.report_html("run_report.html")
result.save("run_out/")
```

If energy offset ≠ 0 is confirmed, plumb an `energy_offset` through
`XRMMapH5Calibration` before the run (small, well-scoped code change) rather than
accepting the hardwired 0.
