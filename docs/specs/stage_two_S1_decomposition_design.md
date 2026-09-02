# AXIOMM Stage Two · S1 — Decomposition tool design

> **Status:** design approved 2026-07-16. Per-tool spec
> for the first analysis tool. Parent: `stage_two_analysis_tools_design.md`.
> Foundations it builds on: `axiomm.analysis` (S0).

## 1. Goal

`axiomm.analysis.decomposition` — reduce a spectrum-image signal to a
small set of components. Backend-neutral by default (scikit-learn on the
neutral `AxiommSignalPayload`), with an optional HyperSpy backend
(fast-follow **S1b**) for legacy parity behind the same interface.

## 2. Guiding principles (this tool, and all stage-two work)

- **Full user parameter autonomy.** Values hard-coded in the original
  `run_melts_pca_gmm_batch.py` (`output_dimension=15`, etc.) were chosen
  for one situated dataset. **They are not defaults here.** No component
  count is baked in; the user chooses. Where a default is unavoidable it
  is principled/neutral, never the situated script value.
- **No silently locked behaviour flags.** In particular, laziness is the
  user's choice — we never hard-code `lazy=False`. If a backend must
  materialise a lazy array to run, it emits a diagnostic rather than
  forcing the choice quietly (mirrors the converter's
  `lazy_downgraded_to_eager`).
- **HyperSpy is optional.** The default path has no HyperSpy dependency.
- **Named errors, headless core, no import side effects** — inherited
  from S0 / the converter's §6 rules.

## 3. Components

### 3.1 `Decomposer` protocol — `decomposition/base.py`

```python
@runtime_checkable
class Decomposer(Protocol):
    name: str
    def decompose(
        self,
        payload: AxiommSignalPayload,
        *,
        n_components: int | None = None,
    ) -> DecompositionResult: ...
```

- Input is the converter's neutral `AxiommSignalPayload` (imported from
  `axiomm.io.converters.models`) — the shared interchange seam.
- Backends are **stateless**; the registry builds them with a no-arg
  factory. Parameters are per-call keyword-only.
- **`n_components=None`** means "no forced reduction": keep
  `min(n_pixels, n_channels)` components. The user sets an integer to
  reduce. There is no `15` default anywhere.

### 3.2 `DecompositionResult` — `decomposition/models.py`

```python
@dataclass
class DecompositionResult(AnalysisResult):  # AnalysisResult from S0
    factors: np.ndarray                    # (n_channels, n_components)
    loadings: np.ndarray                   # (n_pixels, n_components)
    explained_variance_ratio: np.ndarray   # (n_components,)
    nav_shape: tuple[int, ...]             # to reshape loadings into maps
    n_components: int                      # the resolved count actually used
```

- Keeps the geoscience/HyperSpy vocabulary (`factors` / `loadings`)
  users already know; `loadings` is exactly what clustering (S2)
  consumes. Carries S0's `provenance` + `diagnostics` (kw-only base
  fields).

### 3.3 `SklearnPCADecomposer` — `decomposition/sklearn_pca.py`

- `name = "pca"`.
- Locate the signal axis via `AxisSpec.role == "signal"` /
  `index_in_array`; `np.moveaxis` it last; reshape to
  `(n_pixels, n_channels)`. Does **not** assume the signal axis is
  already last.
- Import `sklearn.decomposition.PCA` **lazily inside `decompose`** so
  importing the package never requires scikit-learn (same pattern as the
  converter's lazy h5py/hyperspy).
- Compute: `pca = PCA(n_components=n_components)` (passing `None`
  through to sklearn keeps all components); `loadings =
  pca.fit_transform(X)`; `factors = pca.components_.T`;
  `explained_variance_ratio = pca.explained_variance_ratio_`.
- `n_components` on the result is the resolved integer
  (`pca.n_components_`).

### 3.4 Registry + convenience — `decomposition/__init__.py`

- Create `decomposers = Registry("decomposer")` (S0 `Registry`).
- Register `"pca"` via lazy string factory
  (`"...sklearn_pca:SklearnPCADecomposer"`), then
  `load_into(decomposers, "axiomm.decomposers")` for plugins.
- Expose `get_decomposer(name)` and a `decompose(payload, *,
  backend="pca", n_components=None)` convenience wrapper.
- Eager exports of the protocol, result, registry helpers; the concrete
  sklearn class is resolved lazily via the registry string factory so a
  bare `import axiomm.analysis.decomposition` does not import sklearn.

### 3.5 File adapters — `decomposition/io.py`

- `write_decomposition(result, dir, stem)` → `<stem>_decomposition.npz`
  (factors, loadings, explained_variance_ratio, nav_shape) +
  `<stem>_decomposition.json` (n_components, provenance, diagnostics).
  Refuses to silently overwrite (converter §6 safety).
- `read_decomposition(dir, stem)` → `DecompositionResult`.
- Delivers the "runnable in isolation / resume from disk" promise; the
  in-memory result is what S2 consumes directly.

## 4. Data flow

`AxiommSignalPayload` → `decompose(payload, backend="pca",
n_components=<user choice or None>)` → reshape to `(n_pixels,
n_channels)` (diagnostic if a lazy array is materialised) → sklearn PCA →
`DecompositionResult` (factors, loadings, evr, nav_shape, provenance,
diagnostics) → consumed in-memory by clustering (S2) or persisted via
`io.py`.

## 5. Error handling

- `n_components` greater than `min(n_pixels, n_channels)` →
  `PayloadValidationError` (S0), named and explicit.
- Payload with no `signal`-role axis, or with a non-2D-reshapeable
  shape → `PayloadValidationError`.
- A lazy/dask-backed `data` that sklearn cannot consume is materialised
  **with** a `warning` `Diagnostic` (code `lazy_materialized`), never
  silently and never by forcing `lazy=False` upstream.
- An `info` `Diagnostic` records total explained variance.

## 6. Testing

- `Decomposer` is runtime-checkable; `SklearnPCADecomposer` satisfies it.
- PCA on a synthetic `AxiommSignalPayload` with planted structure:
  assert `factors` `(n_channels, k)`, `loadings` `(n_pixels, k)`,
  `explained_variance_ratio` `(k,)`, correct `nav_shape`, and monotone
  non-increasing explained variance.
- `n_components=None` keeps `min(n_pixels, n_channels)` components.
- Signal axis **not** last is handled (moveaxis) and gives identical
  results to the last-axis case.
- `n_components` too large → `PayloadValidationError`.
- Registry resolves `"pca"` to a `Decomposer`.
- `io.py` round-trips a `DecompositionResult`.
- Provenance records `tool="decomposition"`, `backend="pca"`, the
  resolved `n_components`.
- All sklearn-dependent tests **skip** when scikit-learn is not
  installed, so the no-extras suite stays green (mirrors the hyperspy
  skips).

## 7. Dependencies

- Add `analysis = ["scikit-learn>=1.3"]` extra to `pyproject.toml`; fold
  into `all`. numpy is already a core dependency. scikit-learn is
  imported lazily, so it is required only when the PCA backend runs.

## 8. Deferred / follow-ups

- **S1b:** optional `HyperSpyPCADecomposer` behind the `Decomposer`
  protocol — materialises the payload into a HyperSpy signal (via the
  converter's builder) and delegates to `.decomposition()`, plus a
  legacy-parity test against the original script's numbers. Needs the
  `[hyperspy]` extra.
- **Component-count assessment tool (backlog):** a separate tool that
  mathematically *suggests* an appropriate number of components for a
  dataset (scree/elbow, explained-variance thresholds, broken-stick,
  cross-validated reconstruction error). It suggests; the user decides.
  Recorded here because we deliberately refuse to pick a default count.
