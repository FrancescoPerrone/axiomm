# XRM acquisition record — template (one per distinct acquisition/settings)

Fill one of these for each selected real dataset **before** a publication-facing
run, linking every value supplied to the converter/pipeline to its evidence.
This is a provenance record, not a validation: a value being `USER_CONFIG` (or in
this record) means it was *supplied*, **not** that it was measured, verified, or
scientifically appropriate. Mark anything unavailable as *unavailable* — never
substitute a nominal, typical, test-fixture, or unrelated-dataset value.

**Evidence category** for each value (from the metadata-readiness review):
`source-observed` (read from this file's own metadata) · `owner-confirmed`
(stated by the data owner for these files) · `nominal/configured` (a setting,
preset, or default) · `assumed` (filled by a default/fallback) · `unavailable`.

## File identity
- Exact filename(s) / sample ID(s):
- Covered by the 12 June 2026 legacy audit? (yes/no + how established):
- Software revision frozen for the run (git commit):
- Analysis config frozen (groups, components, seed, reduction, clustering):

## 1. Spectral calibration
| Value | Supplied | Evidence category | Source path / owner note |
|---|---|---|---|
| `energy_scale` (keV/channel) | | | e.g. `/xrmmap/config/mca_calib/slope` |
| `energy_offset` (keV @ ch 0) | | | e.g. `/xrmmap/config/mca_calib/offset` |
| n_channels | | | |
| stored energy vector first/last | | | reconcile with scale·i+offset |
| calibration date / method / known-line check | | | |
| per-detector gain/offset aligned before sum? | | | |
| rebinned? | | | |

## 2. Excitation
| Value | Supplied | Evidence category | Note |
|---|---|---|---|
| instrument / beamline | | | |
| acquisition date | | | |
| `beam_energy_kev` (incident photon energy) | | | **not derivable from stored spectral range** |
| monochromatic? | | | if polychromatic, single-energy k-factors may be inadequate |
| (tube source) anode / kV / filters / optics / incident spectrum | | | |

## 3. Counts layout & scan geometry
| Value | Supplied | Evidence category | Note |
|---|---|---|---|
| counts dataset path | | | e.g. `/xrmmap/mcasum/counts` |
| shape / dtype | | | |
| which array dim is x / y / energy | | | confirm, don't assume `(x,y,channel)` |
| x or y reversed / serpentine reordered? | | | |
| x step / y step (scan pitch) | | | **distinct from nominal spot size** |
| `pixel_size_um` supplied (and is it pitch?) | | | note: a file `beam_size` currently *outranks* this unless `beam_size_key=None` |
| anisotropic x/y? (field_height_um is NOT yet used) | | | |
| crop / bin / normalization already applied | | | a crop keeps original pitch — do not divide full width by cropped pixels |
| intended subregion + dimensions (memory plan) | | | |

## 4. Detector & acquisition conditions
| Value | Supplied | Evidence category | Note |
|---|---|---|---|
| detector model / config | | | |
| counts raw / corrected / summed | | | |
| dwell / live / real time, dead-time, pile-up | | | |
| geometry / sample thickness / prep | | | affects fluorescence interpretation |

## 5. Scientific coverage & validation
| Value | Supplied | Evidence category | Note |
|---|---|---|---|
| expected phases / elements | | | |
| `reference` library + coverage check | | | default lacks sphalerite/galena/Pb — confirm for the specimen |
| `reference_element` suitable? | | | default `"Si"` is an analysis default, not an acquisition result |
| ROI-limit units + ROI variant-axis meaning | | | |
| independent EPMA / standards measured | | | required before any quantitative/identification claim |

> **Boundary.** A completed record enables a *reproducible exploratory* run with
> correct coordinates. It does **not** validate quantitative composition or mineral
> identification: AXIOMM's wt% remain uncorrected theoretical sensitivity-ratio
> estimates and its matches remain candidate rankings. Matching results against the
> same reference library used to label them is not independent validation.
