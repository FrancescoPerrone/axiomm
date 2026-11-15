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

> **`STRICT` and `USER_CONFIG` are not validation.** `STRICT` only forces values to
> be supplied *explicitly* (fail-loud on anything unresolved); a `USER_CONFIG`
> provenance tag means a value was supplied, **not** that it was measured, verified,
> or scientifically appropriate. A `STRICT` conversion can complete with physically
> wrong numbers if wrong numbers are entered. Record each supplied value's evidence
> in an acquisition record — see
> [`acquisition_record_template.md`](acquisition_record_template.md) — and confirm
> which files (if any) are covered by the 12 June 2026 legacy audit; filename,
> directory, HDF5 structure, instrument family or beamline are **not** sufficient
> evidence of coverage on their own.

## Hard blockers — a run is wrong or impossible without these

1. **Energy scale (keV/channel).** Source-metadata extraction is *not yet
   implemented* (the `/xrmmap/config/mca_calib/*` path is deferred —
   `readers/hdf5_helpers.py:359-362`); in default mode the reader falls back to
   the APS legacy preset `0.01 keV/ch` (`readers/presets.py:135`) with only a
   warning. For any non-APS-13IDE detector this must be supplied via
   `XRMMapH5Calibration(energy_scale=...)`, or every peak identification is wrong.
   **Confirm the true per-channel width.**

2. **Energy offset (keV at channel 0).** Now a first-class parameter:
   `XRMMapH5Calibration(energy_offset=...)` (resolved user → preset → assumed 0.0;
   in **STRICT** mode an omitted offset is unresolved and the reader raises, like
   `energy_scale`). A nonzero intercept shifts the whole energy axis, so **confirm
   the real offset and pass it explicitly** — do not rely on the assumed 0.0. (BCF
   files get the offset from HyperSpy metadata, so this is XRM-specific.) Note:
   channel-index ROI bounds now include the intercept too; keV/centi_keV ROI limits
   do not.

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
   expected phases and the measured energy range.** Known coverage gap for ore
   material: the default includes **Pyrite and Pyrrhotite but no sphalerite,
   galena, or Pb** — if Zn/Pb sulfides are expected, the library is incomplete and
   matching will abstain on them (adding phases needs scientific grounding, not a
   quick edit). `reference_element="Si"` is an analysis default, not an acquisition
   result — confirm the Si line is excitable and reliably measured for this specimen.

## Should confirm — a safe-ish default exists but it affects the figures

6. **Navigation pixel scale (µm).** Resolution ladder: environ beam-size key →
   `pixel_size_um` → `field_width_um/xdim` → legacy `500 µm/xdim` → 1.0 (warns).
   Wrong or absent → wrong scale bars. **Confirm pixel size / field width and the
   environ key name.** Two scientific cautions (the reader now warns on the first):
   (a) a file's **`Experiment.Beam_Size__Nominal` is a nominal spot size, not the
   raster scan pitch** — and it currently *outranks* an explicit `pixel_size_um`
   (`SOURCE_METADATA` > `USER_CONFIG`); to use a confirmed pitch you must disable the
   lookup with a schema `beam_size_key=None`, then pass `pixel_size_um`. (b) the
   reader applies **one scale to both axes** — `field_height_um` is not yet used
   (it emits a `field_height_um_ignored` warning); anisotropic x/y is unsupported.
   Don't publish calibrated scale bars until pitch (and anisotropy) are confirmed.
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
| 2 | Energy offset (keV @ ch 0) | correct energy axis | **yes** (now a parameter; STRICT requires it) |
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
from axiomm.io.converters import convert_file
from axiomm.io.converters.calibration import ConversionMode
from axiomm.io.converters.presets import XRMMapH5Calibration
from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Reader
from axiomm import Pipeline

# 1) Convert with EXPLICIT calibration in STRICT mode (fails loud on anything
#    unresolved). convert_file takes a configured *reader instance* via reader=;
#    it has no calibration=/mode= kwargs. All values below are placeholders to be
#    replaced by independently confirmed dataset values (including energy_offset —
#    STRICT requires it explicitly; 0.0 is a valid explicit value).
reader = XRMMapH5Reader(
    calibration=XRMMapH5Calibration(
        energy_scale=confirmed_scale,
        energy_offset=confirmed_offset,
        roi_limit_units=confirmed_roi_units,
    ),
    mode=ConversionMode.STRICT,
)
result = convert_file(input_path, output_path=output_path, reader=reader)

# 2) Run the analysis with the confirmed beam energy and reference.
analysis = Pipeline(
    beam_energy_kev=confirmed_beam_kev,
    reference="minerals_default_v2",   # confirm coverage
    seed=0,
).run(result.output_path)

analysis.report_html("run_report.html")
analysis.save("run_out/")
```

Other STRICT requirements (navigation calibration, ROI units) still apply. The
snippet carries no real-dataset values — fill each from the owner's confirmation.
