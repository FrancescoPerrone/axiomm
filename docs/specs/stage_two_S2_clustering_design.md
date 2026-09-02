# AXIOMM Stage Two · S2 — Clustering tool design

> **Status:** design approved 2026-07-16, subject to the
> seven refinements recorded below. Per-tool spec. Parent:
> `stage_two_analysis_tools_design.md`. Builds on S0 (`axiomm.analysis`)
> and S1 (`axiomm.analysis.decomposition`).

## 1. Goal

`axiomm.analysis.clustering` — assign each pixel of a decomposition to a
cluster. Backend-neutral by default (scikit-learn Gaussian Mixture on the
`DecompositionResult` feature seam), with HDBSCAN as a future backend
(S6). Per-cluster **mean spectra** are produced by a *separate*
aggregation over the source signal, never by the clusterer.

## 2. Guiding principles

- **Domain separation, pipeline composition.** The clusterer is a pure
  clustering operation (features → labels). Averaging original spectra
  by label is a separate function. Composition of the two is the
  pipeline's job (S5); the clusterer must never own or depend on the
  source signal.
- **Parameter autonomy.** No situated value is baked in. `n_clusters`
  is **required** (the legacy `k=7` is gone). `random_state` defaults to
  `None` (no baked `42`). `covariance_type` defaults to `"full"` —
  scikit-learn's own default, not a situated choice.
- **Composition over inheritance.** Result payloads carry `provenance`
  and `diagnostics` as explicit fields rather than inheriting a base
  introduced for metadata uniformity alone (see §8 follow-up on
  harmonising S1).
- **Labels are identifiers, not a contiguous range.** Everything aligns
  to an explicit `cluster_ids` ordering, so HDBSCAN noise (`-1`) and
  future backends fit without change.
- Named errors, headless core, no import side effects, never silently
  overwrite — inherited from S0 / the converter's §6 rules.

## 3. Components

### 3.1 Validating reshape helper — `axiomm/analysis/reshape.py`

```python
@dataclass(frozen=True)
class FlattenedSignal:
    matrix: np.ndarray          # (n_pixels, n_channels)
    nav_shape: tuple[int, ...]  # navigation dims in array order
    n_pixels: int
    n_channels: int
    signal_index: int           # signal axis' index_in_array

def pixels_by_channels(payload) -> FlattenedSignal: ...
```

Validates, not merely reshapes. Raises `PayloadValidationError` when:
exactly one `signal`-role axis is not present; the signal axis has no
`index_in_array`; navigation-axis sizes' product disagrees with the
flattened pixel count; the data dtype is non-numeric; the data contains
non-finite values; or there is more than one signal dimension. Returns
enough structure (`nav_shape`, `signal_index`) to rebuild
navigation-shaped outputs safely.

**DRY refactor:** S1's `SklearnPCADecomposer` currently inlines this
reshape + signal-axis validation. It is refactored to call
`pixels_by_channels`, leaving one implementation. S1's tests are the
regression guard.

### 3.2 `Clusterer` protocol — `clustering/base.py`

```python
@runtime_checkable
class Clusterer(Protocol):
    name: str
    def cluster(self, features: DecompositionResult) -> ClusteringResult: ...
```

The operation takes **only** the feature seam (`DecompositionResult`,
which carries `loadings` + `nav_shape`). All backend parameters live on
the instance (construction), so the protocol stays backend-agnostic and
HDBSCAN-compatible.

### 3.3 `GMMClusterer` — `clustering/gmm.py`

```python
@dataclass(frozen=True)
class GMMConfig:
    covariance_type: str = "full"   # sklearn default, not situated
    random_state: int | None = None # no baked 42
    n_init: int = 1
    max_iter: int = 100
    tol: float = 1e-3
    reg_covar: float = 1e-6

class GMMClusterer:
    name = "gmm"
    def __init__(self, n_clusters: int, config: GMMConfig | None = None): ...
    def cluster(self, features: DecompositionResult) -> ClusteringResult: ...
```

- `n_clusters` is **required, validated** (`>= 1`, `<= n_pixels`) →
  `PayloadValidationError` otherwise.
- Validates the feature matrix (`loadings`): 2-D and finite.
- `sklearn.mixture.GaussianMixture` imported **lazily** inside
  `cluster`. Fits on `features.loadings`, predicts labels.
- `cluster_ids = np.arange(n_clusters)` — GMM declares all requested
  components, so an empty component is representable (count 0).
- Provenance: `AnalysisProvenance(tool="clustering", backend="gmm",
  params={"n_clusters": k, "covariance_type": ..., "random_state": ...})`.

### 3.4 `ClusteringResult` — `clustering/models.py`

```python
@dataclass
class ClusteringResult:
    labels: np.ndarray        # (n_pixels,) raw label per pixel
    label_map: np.ndarray     # nav_shape
    cluster_ids: np.ndarray   # ordered identifiers (may include -1)
    n_clusters: int
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def masks(self) -> np.ndarray:  # (n_clusters, *nav_shape) bool, aligned to cluster_ids
        ...
```

- **No `means`** — that is the separation.
- `masks` is a computed property (single source of truth = `label_map` +
  `cluster_ids`), so it is never serialized redundantly and cannot drift.
- Composition, not inheritance: `provenance`/`diagnostics` are explicit
  fields.

### 3.5 `compute_cluster_means` — `clustering/means.py`

```python
def compute_cluster_means(result: ClusteringResult, source) -> ClusterMeanSpectra: ...
```

- Reshapes `source` via `pixels_by_channels` (so the source is validated
  identically to PCA input).
- **Consistency check:** the source pixel count must equal
  `result.labels.size` → `PayloadValidationError` on mismatch.
- Iterates `result.cluster_ids` **in order**; for each id, averages the
  source spectra whose label equals that id. Means and `pixel_counts`
  are aligned to that same ordering.
- **Empty clusters:** an id with zero pixels yields a `NaN` mean row,
  `pixel_count = 0`, and a `warning` `Diagnostic` (`empty_cluster`).
- Provenance references the clustering it aggregated (carries the
  clustering backend + params), so the two are not ambiguous after
  serialization.

### 3.6 `ClusterMeanSpectra` — `clustering/models.py`

```python
@dataclass
class ClusterMeanSpectra:
    means: np.ndarray         # (n_clusters, n_channels), row i ↔ cluster_ids[i]
    pixel_counts: np.ndarray  # (n_clusters,), aligned to cluster_ids
    cluster_ids: np.ndarray   # copied from the source clustering
    n_clusters: int
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
```

Carries `cluster_ids` so the relationship to the clustering survives
serialization (adjustment #2/#3).

### 3.7 Registry — `clustering/__init__.py`

Configured backends do **not** fit S0's instance-returning `Registry`
(which builds components with a no-arg factory). So the clusterers
registry resolves a name to the **backend class**:

- `clusterers = Registry("clusterer")`; `clusterers.register("gmm",
  lambda: GMMClusterer)` (factory returns the class).
- `get_clusterer(name) -> type[Clusterer]` returns the class; the caller
  constructs it with its typed config:
  `get_clusterer("gmm")(n_clusters=7, config=GMMConfig(random_state=0))`.
- No generic `cluster(...)` dispatch convenience with `n_clusters` (that
  would bake a GMM-shaped signature into a backend-agnostic layer and
  break for HDBSCAN). Ergonomic composition is the pipeline's job (S5).
- **Entry-point discovery deferred:** S0's string-factory instantiates
  (wrong for configured classes). Class-resolving discovery is a small
  registry enhancement, tackled when a second backend/plugin actually
  arrives (S6). Recorded in §8.

### 3.8 File adapters — `clustering/io.py`

`write_clustering` / `read_clustering` and `write_cluster_means` /
`read_cluster_means`, each `.npz` (numerics, dtype-preserving) +
`.json` sidecar. The sidecar carries a **`schema_version`** and records
shapes, `cluster_ids` ordering, backend metadata, and provenance. This
is an **internal adapter (v1), not a stable public persistence
contract** — the versioned schema lets it evolve. `OutputExistsError`
(from S0/S1) guards silent overwrite.

## 4. Data flow

`DecompositionResult` → `GMMClusterer(n_clusters=k, config).cluster(...)`
→ `ClusteringResult` (labels/label_map/cluster_ids). Separately,
`compute_cluster_means(clustering_result, source_payload)` →
`ClusterMeanSpectra`. The pipeline (S5) composes the two when a source is
supplied; standalone callers make the two calls explicitly.

## 5. Error handling

- Feature/source validation via `pixels_by_channels` — all failures are
  named `PayloadValidationError` (no bare `Exception`).
- `n_clusters` out of range (`< 1` or `> n_pixels`) →
  `PayloadValidationError`.
- Non-finite features or source values → `PayloadValidationError`.
- Empty clusters → not an error: `NaN` mean, `pixel_count 0`, and an
  `empty_cluster` diagnostic.
- `OutputExistsError` on non-overwrite writes.

## 6. Testing

All backend-run tests use `pytest.importorskip("sklearn")`.

- **GMM happy path:** planted-cluster `DecompositionResult`; assert
  `labels`/`label_map`/`cluster_ids`/`n_clusters` shapes and that
  `masks` partition the map.
- **Determinism / label-equivalence:** two runs with the same
  `random_state` give the *same partition* — compared by grouping
  equivalence (e.g. adjusted Rand index `== 1`), **not** exact integer
  label identity.
- **Invalid `n_clusters`:** `0`, negative, and `> n_pixels` each raise
  `PayloadValidationError`.
- **`compute_cluster_means`:** hand-built source + known labels →
  `means` `(n_clusters, n_channels)` and `pixel_counts` match by hand,
  aligned to `cluster_ids`.
- **Empty clusters:** a `cluster_id` with no pixels → `NaN` mean row,
  `pixel_count 0`, `empty_cluster` diagnostic present.
- **One-pixel clusters:** a singleton cluster's mean equals that pixel's
  spectrum exactly.
- **Mismatched navigation sizes:** nav-axis sizes whose product ≠ pixel
  count → `PayloadValidationError` from `pixels_by_channels`.
- **Non-finite values:** NaN/inf in source or features →
  `PayloadValidationError`.
- **Reshape helper:** signal-axis validation and non-last-axis handling
  (S1's PCA tests remain green against the refactor).
- **Registry:** `get_clusterer("gmm")` returns the `GMMClusterer` class;
  unknown name → `BackendNotFoundError`.
- **io:** round-trip `ClusteringResult` and `ClusterMeanSpectra`,
  asserting `schema_version`, dtype, shapes, and `cluster_ids` preserved.

## 7. Dependencies

scikit-learn is already covered by the `[analysis]` extra (added in S1).
No `pyproject.toml` change.

## 8. Deferred / follow-ups

- **HDBSCAN backend (S6):** `HDBSCANClusterer` behind the same protocol;
  `cluster_ids` from observed unique labels including `-1` noise; its own
  typed config.
- **Clusterer entry-point discovery:** needs a class-resolving registry
  variant (S0's instantiates). Tackled with the second backend/plugin.
- **Cluster-count suggestion:** BIC/silhouette-based `k` suggestion folds
  into the existing component-count assessment backlog tool — AXIOMM
  won't pick `k` for the user.
- **Harmonise result-metadata approach:** S1's `DecompositionResult`
  inherits `AnalysisResult`; S2 composes. Revisit whether
  `AnalysisResult` should remain an inheritance base or become a composed
  record across the suite. Not done here to avoid retro-refactoring
  shipped S1 code.

## 9. Constraints reaffirmed

PolyForm licence; headless core; named
exceptions only; never silently overwrite; small committable chunks with
`docs/dev/STATE.md` + wiki roadmap kept in lockstep and pushed per chunk.
