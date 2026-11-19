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

## 7. Cross-energy normalization (the scientific crux — configurable, signed off)

Net intensities from different energy maps are **not directly comparable** (different
incident flux, dwell, cross-sections). Combining elements measured at different energies
requires an explicit cross-calibration. Candidate methods, selectable via a policy with
a documented default:

- **Internal-reference element** measured in two overlapping energy maps, used to scale
  one map's intensities onto the other's.
- **Edge-referenced / flux-referenced scaling** from recorded acquisition parameters.
- **User-supplied per-map scaling factors.**

Whichever is used, the method and the resulting factors are recorded in provenance, and
an unresolved cross-calibration is a diagnostic, not a silent guess. **This method is a
scientific decision requiring sign-off (Francesco / Isra); AXIOMM does not pick it
unilaterally.** Until a method is chosen, fusion can still produce *per-element presence
and ratios within each energy* with an explicit "cross-energy quantitative comparison not
calibrated" flag.

## 8. Where it fits in the pipeline

A **pre-quantification fusion step**: `MultiEnergyMapGroup` → verified registration →
per-element energy selection → cross-calibrated net intensities → the existing
`quantify` / reliability / match path, unchanged. For clustering, an optional fused
element-map feature set may be offered; the default remains per-map single-energy
clustering. Single payload ⇒ this step is a no-op.

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
5. The cross-calibration method and factors are recorded in provenance; an uncalibrated
   comparison is flagged, never silent.
6. **Test case (not a driver):** fusing Isra's 2.9 + 13.55 keV A21_066 maps recovers the
   light elements (P, Si) alongside Ca/Ti/Fe, enabling an apatite identification that the
   13.55 keV map alone cannot support.
7. General/unit tests cover registration, selection, and the no-op identity; the
   single-energy suite is unaffected.

## 12. Open scientific decisions

- **The cross-energy normalization method** (§7) — the one real scientific choice; needs
  Francesco/Isra sign-off before a default is fixed.
- Whether clustering should ever consume fused features by default (proposed: no).
