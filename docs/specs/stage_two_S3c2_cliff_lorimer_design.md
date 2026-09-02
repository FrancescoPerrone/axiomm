# AXIOMM Stage Two · S3c-2 — Cliff-Lorimer quantification design

> **Status:** design approved 2026-09-02. Second of three S3c sub-chunks
> (S3c-1 k-factors · **S3c-2 Cliff-Lorimer wt%** · S3c-3 reliability gate).
> Homed in `axiomm.analysis.quant`. Composes S3b peaks + S3c-1 k-factors +
> S3a element data.

## 1. Goal

`axiomm.analysis.quant.cliff_lorimer` — turn per-line net intensities into
element and oxide weight percents via the Cliff-Lorimer ratio, using
theoretical k-factors. A standalone quantification step and the input the
reliability gate (S3c-3) evaluates.

## 2. Guiding principles

- **Compose, don't recompute.** Net intensities come from S3b
  (`PeakMeasurementSet`); k-factors + reference element come from S3c-1
  (`KFactorSet`); oxide forms + atomic weights come from S3a (`ElementRef`).
- **No reliability judgments here.** S3c-2 reports the numbers;
  distinguishing quantitative from exploratory / below-limit is S3c-3.
- **Parameter autonomy.** The reference element is taken from the
  `KFactorSet` (already the user's choice at k-factor time); nothing new
  is baked.
- Named exceptions, no import side effects, never silently overwrite.
- numpy only — no xraylib at this layer (k-factors are precomputed).

## 3. Components

### 3.1 `QuantResult` payload — `quant/models.py` (extend)

```python
@dataclass
class QuantResult:
    net_intensities: Mapping[str, float]
    wt_percent_element: Mapping[str, float]   # metals / cation basis
    wt_percent_oxide: Mapping[str, float]
    reference_element: str
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
```

Composition (explicit `provenance`/`diagnostics`), consistent with the
suite.

### 3.2 `quantify` — `quant/cliff_lorimer.py`

```python
def quantify(peaks: PeakMeasurementSet, kfactors: KFactorSet,
             elements) -> QuantResult: ...
```

- `elements` = iterable of `ElementRef` (S3a) for `oxide_form` +
  `atomic_weight`; the element set to quantify is `kfactors.k_factors`
  keys.
- `reference = kfactors.reference_element`; must be in `kfactors.k_factors`
  else `PayloadValidationError`.
- `net_i = peaks.net_by_label().get(sym, 0.0)`; a k-factor element with no
  measured peak → net 0 + an `element_not_measured` info diagnostic.
- `conc_rel_i = k_i · net_i / net_ref`; if `net_ref == 0`, fall back to
  `k_i · net_i` + a `no_reference_intensity` warning diagnostic.
- `wt_percent_element_i = 100 · conc_rel_i / Σ conc_rel` (metals/cation
  basis); if `Σ conc_rel == 0`, all zero + a `no_signal` warning.
- **Oxide wt%**: for each element with an `oxide_form = (name, n_cat,
  n_O)` and `wt_element > 0`,
  `oxide_mass[name] += wt_element · oxide_mw / (n_cat · AW)` with
  `oxide_mw = n_cat · AW + n_O · AW(O)`; elements whose `oxide_form is
  None` (halogens) are carried as element mass; renormalize to 100%. Fe
  uses its `FeO` `oxide_form` by convention.
- Provenance: `tool="quant"`, `backend="cliff_lorimer"`, params record the
  reference element and the k-factor method/excitation (copied from the
  `KFactorSet` provenance for a full chain).

### 3.3 Batch helper — `quant/cliff_lorimer.py`

```python
def quantify_cluster_means(peak_sets, kfactors, elements
                           ) -> tuple[QuantResult, ...]: ...
```

Maps `quantify` over an ordered sequence of per-cluster
`PeakMeasurementSet`s (as produced by
`axiomm.analysis.peaks.measure_cluster_means`), preserving order so the
results align to the clustering's `cluster_ids`.

### 3.4 File adapters — `quant/io.py` (extend)

`write_quant` / `read_quant` — versioned JSON (`schema_version`,
net_intensities, wt_percent_element, wt_percent_oxide, reference_element,
provenance, diagnostics). Scalars/maps only. `OutputExistsError`-guarded.

## 4. Data flow

`PeakMeasurementSet` (S3b) + `KFactorSet` (S3c-1) + `ElementRef` set (S3a)
→ `quantify` → `QuantResult` (element + oxide wt%). Batched over clusters
for S3c-3, which applies the reliability gate.

## 5. Error handling

- `reference_element` absent from `kfactors.k_factors` →
  `PayloadValidationError`.
- `net_ref == 0` → unnormalized fallback + `no_reference_intensity`.
- all-zero signal → zeros + `no_signal`.
- k-factor element with no measured peak → net 0 + `element_not_measured`.
- `OutputExistsError` on non-overwrite writes.

## 6. Testing (all run without xraylib)

- **Hand-computed CL case:** two elements with known net + known k-factors
  → `wt_percent_element` matches the closed-form ratio; reference element
  is 100·k_ref·I_ref/Σ.
- **Oxide conversion:** a pure-Si spectrum → `SiO2 ≈ 100`; an Fe/Al mix →
  `FeO` + `Al2O3` masses match the closed-form (using `AW`, `n_cat`, `n_O`).
- **`net_ref = 0` fallback** → unnormalized path + `no_reference_intensity`
  diagnostic.
- **k-factor element absent from peaks** → net 0 + `element_not_measured`.
- **All-zero signal** → wt% all 0 + `no_signal`.
- **Batch** → one `QuantResult` per input peak-set, in order.
- **io** round-trips a `QuantResult` with `schema_version`.

## 7. Deferred / follow-ups

- S3c-3 (reliability gate + S2 cluster-quality enrichment) consumes
  `QuantResult` and adds per-element / per-cluster reliability status.

## 8. Constraints reaffirmed

PolyForm Noncommercial licence; headless core; named exceptions only;
never silently overwrite; small committable chunks; wiki roadmap kept in
lockstep and pushed per chunk; science-rich user docs deferred to after S3
completes.
