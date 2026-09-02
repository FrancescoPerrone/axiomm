# AXIOMM Stage Two · S3c-1 — k-factors (`axiomm.analysis.quant.kfactors`) design

> **Status:** design approved 2026-09-01. First of three S3c sub-chunks (S3c-1 k-factors · S3c-2
> Cliff-Lorimer quantification · S3c-3 reliability gate + S2 enrichment),
> homed in a new general `axiomm.analysis.quant` subpackage. Builds on S0
> and S3a; enriches S3a's `ElementRef`.

## 1. Goal

Compute **theoretical Cliff-Lorimer k-factors** from xraylib fundamental
parameters — a standalone quantification tool and the input S3c-2 needs.
Per the project ruling, k-factors are theoretical (xraylib FP); standards
are independent validation, never fitted here.

## 2. Guiding principles

- **General, not mineralogy-specific.** EDS/XRF quantification lives in
  `axiomm.analysis.quant`; it reads S3a element data but is not under
  `mineralogy` (which is matching/labels, S3d).
- **The reference owns element physics.** The per-element emission line
  (Kα/Lα) is element data → it goes into S3a's `ElementRef`, not a
  hardcoded heuristic in the k-factor tool.
- **Parameter autonomy.** `excitation_kev` is **required — no baked
  `18.0`** (beamline-specific). `reference` defaults to `"Si"` (a
  documented common Cliff-Lorimer reference), configurable.
- **No silent dependency fallback.** Missing xraylib raises a clear named
  error with an install hint, never a silent approximation.
- Named exceptions, no import side effects, never silently overwrite.

## 3. Components

### 3.1 S3a enrichment — `ElementRef.emission_line`

Add a field to `axiomm.analysis.mineralogy.reference.ElementRef`:

```python
@dataclass(frozen=True)
class ElementRef:
    symbol: str
    line_energy_kev: float
    atomic_weight: float
    atomic_number: int
    oxide_form: tuple[str, int, int] | None
    emission_line: str = "Ka"      # "Ka" or "La" — the detected characteristic line
```

The `minerals_default_v1` preset sets `emission_line="Ka"` for every
element except **I → `"La"`** (per `cliff_lorimer.py`: I Kα ≈ 28 keV is
above the excitation, so I Lα 3.94 keV is the detected line). Defaulting
to `"Ka"` keeps every existing `ElementRef(...)` construction valid.
`MineralogyReference.validate()` gains: `emission_line ∈ {"Ka","La"}`.

### 3.2 New subpackage `axiomm.analysis.quant`

`quant/__init__.py` exports the k-factor API (extended by S3c-2/3).

### 3.3 `KFactorSet` payload — `quant/models.py`

```python
@dataclass
class KFactorSet:
    k_factors: Mapping[str, float]       # k_{i,ref} per element symbol
    sensitivities: Mapping[str, float]   # S_i (cm^2/g)
    reference_element: str
    excitation_kev: float
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
```

Composition (explicit `provenance`/`diagnostics`), consistent with the
suite.

### 3.4 `compute_k_factors` — `quant/kfactors.py`

```python
def compute_k_factors(
    elements,                 # iterable of ElementRef
    *,
    excitation_kev: float,    # required, > 0
    reference: str = "Si",
) -> KFactorSet: ...
```

- Validates **before** importing xraylib: `excitation_kev > 0`;
  `reference` is among the element symbols — else `PayloadValidationError`.
- Imports xraylib via a small monkeypatchable helper `_import_xraylib()`;
  `ImportError` → `AnalysisDependencyError` with an install hint.
- Per `ElementRef`: line macro from `emission_line`
  (`"Ka"→xl.KA_LINE`, `"La"→xl.LA_LINE`); `S_i =
  CS_FluorLine_Kissel(Z, line, E0)` with fallback to `CS_FluorLine`.
- Reference sensitivity must be `> 0` else `PayloadValidationError`.
- `k_i = S_ref / S_i`; a non-positive `S_i` yields `k_i = nan` plus a
  `warning` diagnostic (`zero_sensitivity`), never a crash.
- Provenance: method `"theoretical (xraylib FP, Kissel cross-sections)"`,
  `xraylib_version`, `excitation_kev`, `reference`.

### 3.5 File adapters — `quant/io.py`

`write_kfactors` / `read_kfactors` — versioned JSON (`schema_version`,
k_factors, sensitivities, reference, excitation, provenance,
diagnostics). Scalars only, so JSON (no `.npz`). `OutputExistsError`-guarded.

### 3.6 Dependency — `[quant]` extra

`pyproject.toml`: `quant = ["xraylib"]`. **Not folded into `all`** —
xraylib is a C-library binding whose pip install is environment-sensitive
(often needs conda), and `pip install .[dev,all]` must stay robust.
xraylib is imported lazily; xraylib-dependent tests `importorskip`.

## 4. Data flow

S3a `MineralogyReference` element subset (Z + emission_line) +
`excitation_kev` → `compute_k_factors` → `KFactorSet` → consumed by S3c-2
(Cliff-Lorimer quantification).

## 5. Error handling

- Missing xraylib → `AnalysisDependencyError` (new, in
  `axiomm.analysis.errors`), with an install hint.
- `excitation_kev ≤ 0`, `reference` absent from `elements`, or
  non-positive reference sensitivity → `PayloadValidationError`.
- A non-positive non-reference sensitivity → `nan` k-factor +
  `zero_sensitivity` diagnostic (not fatal).
- `OutputExistsError` on non-overwrite writes.

## 6. Testing

- `ElementRef.emission_line` defaults to `"Ka"`; preset sets `I → "La"`,
  others `"Ka"`; `validate()` rejects an invalid `emission_line`.
  (Existing S3a tests stay green — the field has a default.)
- **Validation without xraylib** (run always): `excitation_kev ≤ 0` and
  `reference` not in `elements` raise `PayloadValidationError`.
- **Missing xraylib** → `AnalysisDependencyError`, via monkeypatching
  `_import_xraylib` to raise `ImportError`.
- **With xraylib** (`importorskip("xraylib")`): `k_factors[reference] ==
  1.0`; all sensitivities positive; provenance records an
  `xraylib_version` and the `excitation_kev`/`reference` used.
- io round-trips a `KFactorSet` with `schema_version`.

## 7. Deferred / follow-ups

- A `KFactorMethod` protocol + registry if empirical / standard-derived
  k-factor methods are ever wanted (project ruling is theoretical-only
  now).
- S3c-2 (Cliff-Lorimer quantification) consumes this; S3c-3 (reliability
  gate + S2 enrichment) follows.

## 8. Constraints reaffirmed

PolyForm licence; headless core; named
exceptions; small committable chunks; STATE.md + wiki roadmap kept in
lockstep and pushed per chunk; science-rich user docs deferred to after
S3 completes.
