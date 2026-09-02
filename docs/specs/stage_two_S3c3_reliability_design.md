# AXIOMM Stage Two · S3c-3 — quantification reliability gate design

> **Status:** design approved 2026-09-02. Third of three S3c sub-chunks
> (S3c-1 k-factors · S3c-2 Cliff-Lorimer wt% · **S3c-3 reliability gate**).
> Homed in `axiomm.analysis.quant`; enriches S2's `compute_cluster_means`.

## 1. Goal

A GMM cluster mean is a statistical average over pixels that may mix
phases or sit on boundaries, so it is not automatically a valid
quantitative phase spectrum. This tool separates cluster summaries that
are trustworthy enough for quantitative reporting from exploratory-only
ones, and flags per-element results that fall below a reliable count —
without silently presenting a raw cluster mean as a validated composition.
It **flags and diagnoses; it never asserts a physical cause** (instrument
sensitivity vs pixel mixing), which is an open question for the
instrument/geoscience side.

## 2. Guiding principles

- **Overlay, not mutation.** The gate returns a separate report; the raw
  `QuantResult` numbers are untouched and remain available for exploration.
- **Generic.** Keyed by element symbol and cluster id — no hard-coded
  mineral names or cluster indices.
- **Parameter autonomy.** All thresholds are exposed configuration with
  documented example defaults; none is a baked situated value.
- Named exceptions, no import side effects, never silently overwrite,
  numpy only.

## 3. Components

### 3.1 S2 enrichment — `ClusterMeanSpectra` + `compute_cluster_means`

Add two per-cluster arrays to `axiomm.analysis.clustering.models.ClusterMeanSpectra`
(backward-compatible defaults so existing constructions keep working):

```python
    heterogeneity: np.ndarray | None = None   # per cluster; median cosine distance
    total_counts: np.ndarray | None = None    # per cluster; mean-spectrum total counts
```

`compute_cluster_means` fills them, aligned to `cluster_ids`:
- `heterogeneity[i]` = the **median over the cluster's member pixels** of
  `cosine_distance(pixel_spectrum, cluster_mean)` (shape-based,
  scale-invariant; 0 = homogeneous). An empty cluster → `NaN`.
- `total_counts[i]` = `sum(means[i])` (total counts of the mean spectrum).

`cosine_distance(a, b) = 1 − (a·b)/(|a||b|)`; a zero-norm vector → distance
0 contribution guarded.

### 3.2 `ReliabilityConfig` — `quant/reliability.py`

```python
@dataclass(frozen=True)
class ReliabilityConfig:
    min_pixel_count: int = 20        # clusters with fewer member pixels -> exploratory
    max_heterogeneity: float = 0.15  # median cosine distance above this -> exploratory
    min_total_counts: float = 1.0e4  # mean-spectrum total below this -> exploratory
    min_net_counts: float = 50.0     # per-element detection floor
```

Defaults are **documented examples**, not recommendations — every value is
the caller's to set for their instrument/dataset.

### 3.3 Status vocabulary + `ReliabilityReport` — `quant/reliability.py`

```python
ElementStatus = Literal["valid", "below_quantification_limit"]
ClusterStatus = Literal["quantitative", "exploratory_only"]

@dataclass
class ReliabilityReport:
    cluster_status: ClusterStatus
    element_status: Mapping[str, ElementStatus]
    reasons: tuple[str, ...]
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
```

### 3.4 `assess_reliability`

```python
def assess_reliability(quant, *, pixel_count, heterogeneity, total_counts,
                       config=ReliabilityConfig()) -> ReliabilityReport: ...
```

- **Per element:** for each `sym` in `quant.net_intensities`,
  `net < config.min_net_counts` → `"below_quantification_limit"`, else
  `"valid"`. The `QuantResult` wt% is left as-is; the flag is the signal
  not to report that element as a precise validated number.
- **Per cluster:** start `"quantitative"`; append a reason and switch to
  `"exploratory_only"` if `pixel_count < min_pixel_count`, or
  `heterogeneity` is `NaN` or `> max_heterogeneity`, or
  `total_counts < min_total_counts`. Each reason is a human-readable string
  (e.g. `"heterogeneity 0.34 > 0.15"`).
- A `warning` `Diagnostic` (`below_quantification_limit`) is added when any
  element is flagged; an `exploratory_cluster` diagnostic when the cluster
  is not quantitative. No physical cause is asserted.
- Provenance: `tool="quant"`, `backend="reliability"`, params record the
  config thresholds used.

### 3.5 Batch helper

```python
def assess_cluster_reliability(quant_results, cluster_means,
                               config=ReliabilityConfig()
                               ) -> tuple[ReliabilityReport, ...]: ...
```

Pairs each `QuantResult` with the corresponding cluster's
`pixel_counts[i]`, `heterogeneity[i]`, `total_counts[i]` from the enriched
`ClusterMeanSpectra` (order = `cluster_ids`). Raises `PayloadValidationError`
if `cluster_means.heterogeneity` / `total_counts` are `None` (not enriched)
or lengths disagree with `quant_results`.

### 3.6 File adapters — `quant/io.py` (extend)

`write_reliability` / `read_reliability` — versioned JSON (`schema_version`,
cluster_status, element_status, reasons, provenance, diagnostics).
`OutputExistsError`-guarded.

## 4. Data flow

Per cluster: `ClusterMeanSpectra` (means + pixel_counts + heterogeneity +
total_counts) → peaks → k-factors → `QuantResult`; then
`assess_reliability(QuantResult, pixel_count, heterogeneity, total_counts,
config)` → `ReliabilityReport`. Batched over clusters via
`assess_cluster_reliability`.

## 5. Error handling

- `assess_cluster_reliability` on un-enriched `ClusterMeanSpectra`
  (`heterogeneity`/`total_counts` is `None`) → `PayloadValidationError`.
- Length mismatch between `quant_results` and cluster arrays →
  `PayloadValidationError`.
- `NaN` heterogeneity (empty cluster) is not an error → `exploratory_only`
  with a reason.
- `OutputExistsError` on non-overwrite writes.

## 6. Testing

- **Enrichment:** a homogeneous cluster → `heterogeneity ≈ 0`; a cluster
  whose members are a planted two-phase mix → materially higher;
  `total_counts` equals the mean-spectrum sum; an empty cluster → `NaN`.
  Existing `ClusterMeanSpectra` without the fields still constructs
  (defaults `None`).
- **Per element:** a `QuantResult` with a low-net element (the K≈6-count
  case) → `below_quantification_limit`; a well-counted element → `valid`.
- **Per cluster:** high heterogeneity / low pixel count / low total counts
  each → `exploratory_only` with the matching reason; a clean cluster →
  `quantitative`.
- **Batch:** one `ReliabilityReport` per `QuantResult`, aligned; un-enriched
  input raises.
- **io** round-trips a `ReliabilityReport` with `schema_version`.

## 7. Deferred / follow-ups

- The heavier **per-pixel / trusted-mask / spatially-matched-ROI
  re-quantification** that actually *recovers* a diluted element (rather
  than flagging it) remains a separate backlog tool.
- Automatic artifact/void detection remains later work.

## 8. Constraints reaffirmed

PolyForm Noncommercial licence; headless core; named exceptions only;
never silently overwrite; small committable chunks; wiki roadmap kept in
lockstep and pushed per chunk; docs carry runnable examples with real
output.
