# Stage two — user-facing API ergonomics (plain-English naming)

**Status:** design, revised after the audited review (2026-11-23). Not implemented.
**Scope (Francesco):** the one-call `Pipeline` facade **and** the per-stage tools.
**Principle:** every change is **additive and non-breaking** — current names keep working as
aliases, so existing scripts, the notebook, and the runners run unchanged. The goal is that the
code a non-coding scientist reads scans like a sentence.

**Acceptance target:** the three worked examples in `examples/api/` (A one analysis, B importable
module, C per-stage walkthrough) + the baseline in `docs/specs/api_contract_inventory.md`. They
are written in the current API, run through the public entry points on a synthetic fixture, and
are the readability-review basis. After implementation they are rewritten to the new words and
re-verified for scientific equivalence (§4).

## 1. The facade — confirmed vocabulary

Plain-English argument/method names; **every current name stays as an alias**.

| What it does | Current (kept as alias) | New (documented) |
|---|---|---|
| acquisition energy | `beam_energy_kev=13.55` | `beam_energy="13.55 keV"` |
| number of clusters to find | `groups=7` | `clusters=7` |
| drop an element from quant+matching | `exclude_elements={"Ba"}` | `exclude_elements=["Ba"]` *(accept a plain list)* |
| which mineral library to match against | `reference="minerals_default_v2"` | `library="minerals_default_v2"` |
| the species/family/unresolved policy | `classification="family_aware"` | `naming_policy="family_aware"` |
| write the HTML report to a file | `result.report_html("x.html")` | `result.write_report("x.html")` |

Reads as:
```python
Pipeline(beam_energy="13.55 keV", library="minerals_default_v2",
         clusters=7, exclude_elements=["Ba"], naming_policy="family_aware"
         ).run("A21_066.h5").write_report("A21_066.html")
```

Notes from the review:
- **`clusters`, not phases.** `groups`/`clusters` sets the number of GMM clusters; it does not
  assert a phase count (several clusters can share one phase, others stay `unresolved`). Documented
  as such.
- **`exclude_elements` stays the word** (auditor); the gain is accepting a plain **list**. It drops
  the element from the cation list **before peak measurement, quantification and matching**, and
  **not** from PCA/clustering (verified, inventory §facade). A bare string `"Ba"` is **rejected**
  (never read as elements `B`,`a`); the current set/iterable input keeps working.
- **`result.report()` is already taken** — it returns a `Report` object. The new file-writing verb
  is **`write_report(path)`** (HTML; returns the written `Path`/`Report` per the kept
  `report_html` contract). `report_html` stays unchanged.

### 1.1 The energy value — explicit contract (one shared parser)
`beam_energy` accepts:

| input | result |
|---|---|
| `"13.55 keV"` | 13.55 keV |
| `"2900 eV"` | 2.9 keV |
| `13.55` (number) | 13.55 keV, by documented numeric convention |
| `"13.55"` (string, no unit) | `PayloadValidationError` — a string must carry a unit |

Accepted units `keV`/`eV` (case-insensitive, optional single space). **Reject** unknown units,
booleans, non-finite, and non-positive energies, with a named error. One routine
`parse_energy_kev(value)` normalises at each public boundary and passes the canonical keV value
downstream. `beam_energy_kev=` keeps its exact current numeric contract. **Multi-energy:** a
`MultiEnergyMapGroup` takes its energies from its members — `beam_energy` must **not** broadcast one
value across the group; existing precedence is preserved and the 2.9/13.55 keV path is exercised.

## 2. The per-stage tools
Verbs unchanged (`decompose`, `cluster`, `measure_peaks`, `quantify`, `compute_k_factors`,
`assess_reliability`, `match_minerals`). Three consistency fixes, all additive and all justified by
the inventory:

- **One energy word.** `compute_k_factors(excitation_kev=…)` also accepts `beam_energy=` (same
  parser); `excitation_kev` kept.
- **Disambiguate `reference`.** mineral library → **`library`** (alias `reference`) in
  `match_minerals`; reference element → **`reference_element`** (alias `reference`) in
  `compute_k_factors`. `reference` keeps its current meaning at each site.
- **`method=` for algorithm choice**, only where a stage truly selects an algorithm — verified:
  `decompose`/`cluster`'s `backend=` selects the algorithm (pca/gmm/…), so both gain `method=`
  (alias `backend`). No other stage has an algorithm selector, so none gains `method`.
- **Exclusion list** accepted wherever elements are dropped (coerced to a set, bare string
  rejected).
- The `get_*` accessors are left as-is but **documented accurately** (inventory): `get_decomposer`
  → instance, `get_clusterer` → class, `get_reference` → library data.

## 3. Alias mechanism (corrected per review)
Aliases are **not** resolved in `PipelineConfig.__post_init__`: `PipelineConfig` is a dataclass, so
an unknown keyword raises `TypeError` *before* `__post_init__`, and a value equal to a default is
indistinguishable from omission. Instead:
- **Facade** `Pipeline.__init__(**kwargs)` sees raw keywords — resolve there, mapping new→canonical
  into `PipelineConfig`'s canonical fields.
- **Stage functions / any direct boundary** use explicit keyword parameters with an **omission
  sentinel** (`_UNSET`) so "supplied" vs "equal to default" vs "omitted" are distinguishable.
- Passing **both** a word and its alias raises a named error that names both, even if the values
  agree or one equals the default.
- Canonical keywords stay visible in signatures/help/completion. Unknown keywords stay detectable
  (no silent swallowing). Direct `PipelineConfig(...)` construction, positional compatibility, and
  save/load keep working; the serialised representation is unchanged (no schema bump).

## 4. Equivalence contract (replaces blanket byte-identity)
For a legacy call and its new-word equivalent on the same input, same seed and execution settings:
- **scientific equivalence:** identical cluster assignments, matching evidence, classification
  outcomes, and resolved config/provenance;
- **byte-identity only for genuinely deterministic artifacts** (e.g. saved arrays); for reports,
  compare substantive content, excluding run-specific fields (timestamps, paths) — never normalise
  away a scientific difference.

Regressions to add: alias-only calls, canonical-only calls, both-spellings-at-once (named error),
malformed/unit-less/out-of-range energies, the direct `PipelineConfig` path, and the three worked
examples run through public entry points on the synthetic fixture (report created, result usable).

## 5. Acceptance criteria
1. The English-form call in §1 runs and is **scientifically equivalent** (§4) to the current-form call.
2. Every current name still works; a word + its alias together is a named error.
3. `beam_energy` honours the §1.1 table; bad units/booleans/non-finite/non-positive raise.
4. `library`/`reference_element` are unambiguous across facade and tools; `reference` still works at
   each site with its current meaning.
5. `method=` selects a backend in `decompose`/`cluster`; `backend=` still works; no spurious
   selector elsewhere.
6. `beam_energy` does not broadcast across a multi-energy group; the 2.9/13.55 keV path is exercised.
7. Docs (`docs/user/analysis.md`, the notebook) lead with the new words + a compact alias table.
8. Full suite green; changed scope ruff-clean.

## 6. Delivery order (reviewable chunks)
0. **Examples + inventory** (done): `examples/api/`, `docs/specs/api_contract_inventory.md`.
1. **Facade**: `clusters`, `library`, `naming_policy`, `write_report`, the energy parser +
   `exclude_elements` list, resolved in `Pipeline.__init__`.
2. **Energy + `library`/`reference_element`** across the stage tools.
3. **`method=`** in `decompose`/`cluster` + exclusion-list everywhere.
4. **Docs** rewritten to the new words from the exercised examples.

## 7. Out of scope
Deprecating old names; changing any result/return types; renaming internal functions; a schema
bump; the broader UX layer.
