# AXIOMM Stage Two · Multi-energy fusion (N-energy quantification) — design

> **Status:** proposed 2026-11, greenlit by Francesco. **Additive and optional:**
> the single-energy pipeline is the default and is unchanged. This capability
> engages only when a user explicitly supplies several co-registered maps of the
> same region at different excitation energies. It is **N-energy, not "dual-energy,"**
> and general: the Isra 2.9 + 13.55 keV pair is one *test case*, never the design driver.

## 1. Motivation

Some XRF/XRM experiments image the **same spatial region at several excitation
energies** to cover a wider element (Z) range than any single energy can — a low
energy to excite light elements near their edges, higher energies for heavier
elements. A single-energy map is then, by design, blind to the elements its energy
cannot excite.

This was verified concretely on A21_066: the same sample at **2.9 keV** vs **13.55 keV**
has a low-Z/mid-Z count ratio of **29.9 vs 0.01** — P/Si/Al are ~3000× stronger in the
low-energy map (see `melts/axiomm_figures/dual_energy_compare.png`). The 13.55 keV map
alone cannot support an apatite identification because P is barely excited. This is a
**property of the acquisition**, which AXIOMM already reports; multi-energy fusion is
how the analysis *uses* the complementary data to recover the full composition.

## 2. Scope and non-goals

**In scope:** combine N co-registered, energy-tagged maps of one region so each element
is measured from the energy that best excites it, producing a fused per-element
net-intensity set for quantification (and, optionally, fused element maps for clustering).

**Non-goals (explicitly):**
- Not a default and not required — single-energy stays the common path.
- Not 2-energy-specific — N energies, any element set.
- Not matrix/ZAF/absorption correction (separate, future).
- Not spatial resampling, stitching, or motion correction — fusion assumes (and
  **verifies**) co-registration; it does not create it.

## 3. Principles (govern the whole design)

1. **General** — N energies, arbitrary elements; no beamline/energy constants baked in.
2. **Optional / additive** — opt-in; absent multiple maps, nothing changes. Single
   payload ⇒ fusion is the identity.
3. **Pluggable** — the per-element energy-selection rule and the cross-energy
   normalization are **policy backends** (name / dict / instance), same socket pattern
   as `reduction=` / `clustering=`, with defensible, documented defaults.
4. **Honest** — registration is **verified, never assumed**; the cross-calibration
   method and factors, and which energy measured which element, are recorded as
   provenance + diagnostics. A limitation is a property of the *data*, surfaced by AXIOMM.

## 4. The N-energy model

A `MultiEnergyMapGroup`: an ordered set of `(excitation_kev, AxiommSignalPayload)` for
the **same spatial region**. Each payload is an ordinary converter output (so every
reader/format works). The group is constructed explicitly by the user (or, later, a UX
"map group"); AXIOMM never infers it from filenames.

## 5. Registration contract (verify, do not assume)

Before fusion AXIOMM checks the maps share a spatial grid: identical navigation shape
and matching nav scale/offset within a tolerance. Mismatches raise a named error (or,
per policy, emit a diagnostic and refuse). AXIOMM does not resample or align — that is
the user's responsibility upstream, and the contract makes any violation loud.

## 6. Fusion policy — per-element energy selection (pluggable)

For each element to quantify, choose the map that measures it best. **Default rule:**
pick the map whose excitation energy is **above the element's absorption edge** and
maximizes excitation efficiency (and, where several qualify, the better SNR for that
line). An element excited by no supplied energy is reported `not_excited` (a diagnostic),
not fabricated. Alternative policies (e.g. user-pinned element→energy map) plug into the
same seam.

## 7. Cross-energy normalization (DECIDED) — I0 + live-time + dead-time, then energy-specific k-factors

Net intensities from different energy maps are not directly comparable (different
incident flux, dwell, dead-time, cross-sections). The **decided default** is the
established synchrotron-XRF method, not an ad-hoc factor:

1. **Flux / time / dead-time normalization of each map.** Per pixel, normalize the
   spectrum by the **incident-flux monitor (I0)**, the **live-time**, and the
   **dead-time correction** — the standard pre-quantification normalization in PyMca,
   **Larch** (which produced these XRM-Map files), GeoPIXE and APS-MAPS. The GSECARS
   13-IDE files carry exactly these channels: `/xrmmap/scalars/I0` (+ `TSCALER`) and
   `/xrmmap/mcasum/{livetime, dtfactor}`. This removes the flux/dwell/dead-time
   differences between the two energy acquisitions and yields intensity **per incident
   photon per live second**.
2. **Measure each element from its best-excited, normalized map** (§6).
3. **Compute each element's k-factor at the energy it was measured** — AXIOMM's
   `compute_k_factors(excitation_kev=...)` is already energy-parameterised, so the
   energy-dependent fluorescence cross-section is carried per element.
4. **Cliff-Lorimer** with those per-element-energy k-factors on the I0-normalized
   intensities. **Physics justification (fundamental parameters / Sherman):**
   `I_i ∝ I0(E) · σ_i(E) · ω_i · ε_i · …`; dividing by `I0(E)·t` and dividing by the
   sensitivity `S_i(E)` (the k-factor at that energy) cancels the energy-dependent
   terms, so an element measured at 2.9 keV and one measured at 13.55 keV land on the
   **same mass-fraction footing without an arbitrary bridging factor.**
5. **Bridge-element consistency check (validation / optional refinement).** An element
   excited in ≥2 maps should yield the same concentration from either; the discrepancy
   is recorded as a diagnostic and may drive a residual correction factor. This
   validates the I0 normalization rather than replacing it.

The normalization channels used, the per-element source energy, the k-factor energies,
and any bridge-element residual are all recorded in provenance; an element excited by no
supplied energy, or a missing I0/live-time channel, is a diagnostic, never a silent
guess. **General corollary (broader than fusion):** I0 + live-time + dead-time
normalization is standard for *single-energy* quantification too; AXIOMM should read the
scaler channels and offer normalized intensities on the ordinary path, with raw-count
behaviour kept as an explicit fallback when the scalers are absent.

## 8. Where it fits in the pipeline

A **pre-quantification fusion step**: `MultiEnergyMapGroup` → verified registration →
per-element energy selection → cross-calibrated net intensities → the existing
`quantify` / reliability / match path, unchanged. For clustering, the default
(`fusion_clustering="primary"`) produces **one shared segmentation from the
highest-energy (primary) map** — a single-energy clustering basis, applied to every
map — not independent per-map clustering and not fused features. An optional fused
element-map feature set (`fusion_clustering="fused"`) may be opted into. Single
payload ⇒ this step is a no-op.

## 9. API sketch (additive)

- A constructor for the group and a `fuse_energies(group, *, selection=..., cross_cal=...)`
  returning fused per-element intensities + provenance/diagnostics.
- `Pipeline` optionally accepts a map group and a `fusion=` policy; with a single payload
  it behaves exactly as today.

## 10. Outputs & provenance

The fused result records, per element: the **source energy**, the **cross-calibration
method and factor**, and `not_excited` where applicable; plus registration and policy
diagnostics. Downstream quantification/matching consume the fused intensities as usual.

## 11. Acceptance criteria

1. Single-energy behaviour is byte-identical (fusion is a no-op for one payload).
2. Multi-energy engages only on an explicit group; nothing is inferred from filenames.
3. Registration is verified; mismatched grids raise/refuse with a named diagnostic.
4. Energy-selection and cross-calibration are pluggable policies with documented defaults.
5. Each map is normalized by I0 + live-time + dead-time (the scaler channels) before
   quantification; a missing scaler is a diagnostic with an explicit raw-count fallback.
   The normalization channels, per-element source energy, k-factor energies, and
   bridge-element residual are recorded in provenance.
6. **Test case (not a driver):** fusing Isra's 2.9 + 13.55 keV A21_066 maps recovers the
   light elements (P, Si) alongside Ca/Ti/Fe, enabling an apatite identification that the
   13.55 keV map alone cannot support.
7. General/unit tests cover registration, selection, and the no-op identity; the
   single-energy suite is unaffected.

## 12. Scientific decisions

- **Cross-energy normalization method — DECIDED (§7):** I0 + live-time + dead-time
  normalization, then per-element k-factors at the measurement energy, validated by a
  bridge-element consistency check. Grounded in fundamental-parameter XRF and standard
  synchrotron practice (PyMca / Larch / GeoPIXE / APS-MAPS); the required scaler channels
  are present in the GSECARS 13-IDE data. No external sign-off was available, so this is
  our best engineering + science judgment, documented for the record and revisable.
- **General I0-normalization on the single-energy path — adopted (§7 corollary):** read
  the scaler channels and quantify on normalized intensities, with raw counts as the
  explicit fallback when scalers are absent.
- Whether clustering should ever consume fused features by default — **no** (proposed and
  kept): clustering stays per-map; fusion acts at quantification.

## 13. Implemented multi-energy defaults (reconciled with the spec)

The shipped code had briefly drifted to `fusion_clustering="fused"` +
`fusion_cross_cal="bridge"` as the defaults. That is **reconciled back to the
conservative baseline this spec argued for** (§8, §12):

- **`fusion_clustering="primary"` (default)** — one shared segmentation from the
  highest-energy map; `"fused"` (cluster on standardized, concatenated per-energy
  loadings) is **opt-in**.
- **`fusion_cross_cal="none"` (default)** — no automatic bridge correction. The I0 +
  live-time + dead-time + per-element-k normalization (§7) already puts the maps on a
  common per-incident-photon footing; `"bridge"` (§7.5 consistency correction) is an
  **opt-in refinement**, not the default.
- **Cross-energy comparability guard (prerequisite).** The conservative `"none"` default
  is only safe because the fused quantification runs on a **cross-map** normalization
  (counts per raw I0, no per-map median) so exposure/monitor differences cancel; when a
  map lacks a usable `intensity_norm`, fused composition is **withheld** (clusters +
  per-acquisition evidence retained) rather than quantified on incomparable intensities.
- **Opting into `"fused"` and/or `"bridge"` is marked EXPERIMENTAL** — a loud
  `fusion_experimental` diagnostic, a report banner, and a provenance flag that travels
  through save/load — because a single per-energy bridge scalar is a coarse model and
  fused clustering mixes energies' features, so the cross-energy wt% is not guaranteed
  comparable. Phase *identification* is more robust than the cross-energy composition.
- Both clustering-mode and bridge-mode stay **independently user-selectable** for
  exploratory runs; the single-energy path is unchanged and does not read these fields.
