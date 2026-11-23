# AXIOMM public-contract inventory (for the API-ergonomics pass)

Verified against the repository at commit `694204f`. This is the factual surface the
ergonomics pass (`stage_two_api_ergonomics_design.md`) must preserve — one row per public
entry point, with its real signature, what it returns, what each selector controls, and the
naming facts a reader needs. **No behaviour changes here; this is the baseline.**

## Facade

| Entry point | Signature (current) | Returns |
|---|---|---|
| `Pipeline(...)` | `Pipeline(config=None, **kwargs)` → builds `PipelineConfig` | a `Pipeline` |
| `Pipeline.run(source)` | `source` = a path, an `AxiommSignalPayload`, or a `MultiEnergyMapGroup` | `PipelineResult` |
| `PipelineResult.clusters` | property | list of row dicts (`cluster_id`, `pixels`, `best_match`, `score`, `label`, `level`, …) |
| `PipelineResult.phase_map` | attribute | per-pixel object array of phase names |
| `PipelineResult.summary()` | — | `str` |
| `PipelineResult.report(*, backend="html", config=None)` | **returns a `Report` object** (does not write) | `Report` |
| `PipelineResult.report_html(path=None, *, config=None, overwrite=False)` | writes HTML **iff** `path` given, else returns the `Report` | `Report` |
| `PipelineResult.save(dir, *, overwrite=False)` | writes a self-describing directory | `Path` |

**`PipelineConfig` is a `@dataclass`** (fields: `groups`, `components`, `reduction`, `clustering`,
`reference`, `beam_energy_kev`, `reference_element`, `seed`, `match`, `reliability`,
`exclude_elements`, `line_resolution_kev`, `normalize`, `classification`, `fusion_cross_cal`,
`fusion_clustering`, `bridge_dispersion_limit`, `bridge_low_confidence`, `extra`). Consequence for
aliasing: **an unknown keyword raises `TypeError` at construction, before `__post_init__`** — so
aliases cannot be resolved in `__post_init__`. `Pipeline.__init__(**kwargs)` is the boundary that
sees raw keywords.

### What the facade settings control (verified)
- **`groups`** → the clusterer's `n_clusters` (number of **GMM clusters**, `core.py` → clusterer).
  It is a clustering resolution knob; it does **not** assert a phase count (several clusters can
  share one phase name, and some stay `unresolved`). New plain word: **`clusters`**.
- **`exclude_elements`** → in `_cations_for_quant` (`core.py:271-273`) the listed symbols are
  dropped from the **cation list before peak measurement, quantification and matching**; they are
  **not** removed from the raw spectrum that drives PCA/clustering. So excluding `Ba` means "Ba is
  not measured/quantified/matched" (the Ba Lα/Ti Kα interferent case), while clustering is
  unaffected. Currently accepts any iterable of symbols; the pass must **accept a plain list and
  reject a bare string** (`"Ba"` must not be read as elements `B`,`a`).
- **`beam_energy_kev`** → required before quantification/matching; for a `MultiEnergyMapGroup` the
  energies come from the **group members**, not this field (fusion path). A `beam_energy` alias
  must **not broadcast** one value across a multi-energy group.
- **`reference`** → the **mineral library** name/object (resolved via `get_reference`).
- **`reference_element`** → the k-factor normalising **element** (default `"Si"`).
- **`classification`** → selects the species/family/unresolved **decision policy**.

## Stage tools (public verbs)

| Verb (top-level export) | Signature | Returns | Selector |
|---|---|---|---|
| `decompose` | `decompose(payload, *, backend="pca", n_components=None)` | `DecompositionResult` | `backend` = **algorithm** (pca/…) |
| `cluster` | `cluster(features, *, backend="gmm", n_clusters=None, config=None)` | `ClusteringResult` | `backend` = **algorithm** (gmm/hdbscan) |
| `compute_cluster_means` | `compute_cluster_means(clustering, payload)` | `ClusterMeanSpectra` | — |
| `measure_peaks` | `measure_peaks(means, energy_axis, reference=None, *, lines=None, measurer=None)` | `tuple[PeakMeasurementSet]` | `measurer` = object |
| `compute_k_factors` | `compute_k_factors(elements, *, excitation_kev, reference="Si")` | `KFactorSet` | — (`reference` = **element**) |
| `quantify` (`quantify_cluster_means`) | `quantify_cluster_means(peak_sets, kfactors, elements, *, reference_name=None)` | `tuple[QuantResult]` | — |
| `assess_reliability` (`assess_cluster_reliability`) | `assess_cluster_reliability(quant_results, cluster_means, config=None)` | `tuple[ReliabilityReport]` | — |
| `match_minerals` (`match_clusters`) | `match_clusters(quant_results, reference, *, reliabilities=None, config=None, allow_ungated=False, rank_exploratory=False)` | `tuple[MineralMatchResult]` | — (`reference` = **library**) |

### Accessor inconsistency (verified — document, don't silently change)
- `get_decomposer(name)` → a fresh **Decomposer instance**.
- `get_clusterer(name)` → the **clusterer class** (caller constructs it).
- `get_reference(name)` → **library data** (a `MineralogyReference`).

### Naming collisions the pass resolves
- **`reference`** means *mineral library* in `Pipeline`/`match_minerals`, but *reference element*
  in `compute_k_factors`. → `library` (library) vs `reference_element` (element); `reference`
  kept at both with its current meaning.
- **energy** is `beam_energy_kev` (facade) vs `excitation_kev` (`compute_k_factors`). → one
  `beam_energy` word, old names aliased.
- **`backend`** selects an algorithm in both `decompose`/`cluster` → `method` (alias `backend`).
  No other stage has an algorithm selector, so none gains `method`.
