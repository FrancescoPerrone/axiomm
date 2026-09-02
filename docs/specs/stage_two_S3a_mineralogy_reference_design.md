# AXIOMM Stage Two · S3a — Mineralogy reference library design

> **Status:** design approved 2026-07-17. First of four
> S3 sub-chunks (S3a reference · S3b peak identification · S3c
> Cliff-Lorimer quantification · S3d structural matching + layered
> labels). Parent: `stage_two_analysis_tools_design.md`. Builds on S0
> (`axiomm.analysis.reference`).

## 1. Goal

`axiomm.analysis.mineralogy.reference` — the named, versioned science
bundle every mineralogy tool reads: per-element X-ray + chemical data and
a provenance-tagged mineral-endmember library. First real consumer of
S0's `references` scaffolding. Pure data + validation; no heavy
dependencies.

## 2. Guiding principles

- **The reference owns the science.** Line energies, atomic weights,
  oxide forms, mineral compositions, families, and the structural
  exclusion set live here once; S3b–S3d consume them rather than
  re-deriving. Downstream tools never hard-code element or mineral data.
- **Physics constants are legitimate defaults** (Kα line energies, atomic
  weights, atomic numbers) — universal, not situated. The *tuning*
  constants of later tools (`half_width`, `tau`, `E0`) stay explicit
  config in those tools, never here.
- **Structural matching excludes O** (findings §1.1): oxygen is below the
  usable EDS window and, being shared across an all-oxide library, drowns
  the discriminating cations. `structural_exclude = {"O", "Br", "I"}`.
  Consequence: oxidation-only pairs (Magnetite/Hematite) become identical
  cation vectors — S3d must return `ambiguous`, and S3a's vectors make
  that property explicit and testable.
- Named exceptions only; frozen dataclasses; no import side effects.

## 3. Components

### 3.1 `ElementRef`

```python
@dataclass(frozen=True)
class ElementRef:
    symbol: str
    line_energy_kev: float                     # principal detected line (Kα; Lα for I)
    atomic_weight: float
    atomic_number: int
    oxide_form: tuple[str, int, int] | None    # (oxide_name, n_cation, n_O); None = reported as element
```

Ported from `refactoring_meta/cliff_lorimer.py` (`LINE_KEV`, `Z`,
`ATOMIC_WEIGHTS`, `OXIDE_FORM`). Halogens (F, Cl, Br, I) and O carry
`oxide_form = None` (reported as element). Fe uses `("FeO", 1, 1)` by
convention — EDS cannot resolve Fe²⁺/Fe³⁺.

### 3.2 `MineralEndmember`

```python
@dataclass(frozen=True)
class MineralEndmember:
    name: str
    family: str
    composition: Mapping[str, float]                 # cation counts by element
    family_element_weights: Mapping[str, float] | None
    provenance: str                                  # EPMA table / standard source
```

### 3.3 `MineralogyReference`

```python
@dataclass(frozen=True)
class MineralogyReference(ReferenceLibrary):   # name/version/description from S0 base
    elements: Mapping[str, ElementRef]
    minerals: tuple[MineralEndmember, ...]
    structural_exclude: frozenset[str]         # {"O","Br","I"}
    family_display: Mapping[str, str]

    def element_order(self) -> tuple[str, ...]: ...
    def mineral_vectors(self) -> tuple[tuple[str, np.ndarray], ...]: ...
```

- `element_order()` — a stable ordering of `elements` keys (matching
  vector construction).
- `mineral_vectors()` — for each endmember, a **normalized cation vector**
  over `element_order()` with `structural_exclude` elements zeroed, then
  L1-normalized (counts → fractions summing to 1 over the retained
  cations). This is exactly what S3d's cosine matching consumes.

### 3.4 Validation

A `validate()` (called by the preset constructor and available to users)
raises `PayloadValidationError` when:
- a `structural_exclude` symbol is not a known element;
- any `line_energy_kev` or `atomic_weight` is non-positive;
- a mineral's `family` has no `family_display` entry.

**Out-of-set composition elements are tolerated, not fatal.** Real
endmembers carry trace elements outside the detected-line set (e.g. Ba
0.6% in a glass standard). Matching the reference implementation, such
elements are **dropped from vector construction** and surfaced as a
`Diagnostic` (`unknown_composition_element`) rather than raising — so a
provenance-tagged library is not rejected over a trace element.

### 3.5 Default preset

`MINERALOGY_DEFAULT_V1: MineralogyReference` — the **44 provenance-tagged
endmembers** (incl. a silicate-glass endmember; measured
phosphate/mica/amphibole/Fe-Ti-oxide) + element data + `FAMILY_DISPLAY`,
ported from `refactoring_meta/hybrid_phase_pipeline.py`
(`MINERAL_LIBRARY`, `FAMILY_DISPLAY`) and `cliff_lorimer.py`. Registered
in S0's `references` registry as `"minerals_default_v1"` via
`register_reference`. Users register their own libraries alongside.

## 4. Data flow

`get_reference("minerals_default_v1")` → `MineralogyReference` →
consumed by S3b (element line energies for peak windows), S3c (atomic
weights, oxide forms, atomic numbers/Z for k-factors), S3d
(`mineral_vectors()`, families, `family_display`).

## 5. Error handling

All validation failures are `PayloadValidationError` (S0). No bare
`Exception`. Missing optional data (e.g. an endmember without
`family_element_weights`) is allowed — S3d falls back to unweighted.

## 6. Testing

- `get_reference("minerals_default_v1")` returns a `MineralogyReference`.
- Endmember count matches the ported library (incl. the silicate-glass
  endmember by name); every mineral element is in `elements`.
- `structural_exclude == {"O", "Br", "I"}`.
- `mineral_vectors()` rows sum to 1.0 and have zero weight on O/Br/I.
- **Oxidation degeneracy:** Magnetite and Hematite yield identical cation
  vectors (the property S3d turns into `ambiguous`).
- `validate()` rejects: unknown-element composition; non-positive weight;
  family without a `family_display`.
- `family_display` covers every family used by the endmembers.
- Import guard: importing the module has no side effects.

## 7. Dependencies

numpy only (core). No h5py/hyperspy/sklearn/xraylib at this layer.

## 8. Deferred / follow-ups

- **JSON loading** of a user `MineralogyReference` (round-trip with a
  versioned schema) — strengthens the "standalone" story; a follow-up.
- xraylib-based **k-factors** live in S3c, not here.
- The **glass/K non-monomineralic** problem and **artifact detection**
  are in the deferred tool-expansion backlog, not S3.

## 9. Constraints reaffirmed

PolyForm licence; headless core; named
exceptions; small committable chunks; STATE.md + wiki roadmap kept in
lockstep and pushed per chunk.
