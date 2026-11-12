# Quantification validation — freeze plan

**Status:** preparation. This document identifies the exact code path, inputs,
outputs, metadata and acceptance checks that must be **frozen** before
standards-based experimental validation of AXIOMM's quantification begins.

**Non-negotiable principle.** AXIOMM's current Cliff–Lorimer output is an
**uncorrected theoretical sensitivity-ratio estimate**, not a validated
quantitative measurement. Nothing in this plan changes that scientific meaning.
The purpose of freezing is so that a later standards comparison measures a fixed,
auditable pipeline — and so that any experimental corrections are added as *new,
clearly-versioned* code rather than by silently mutating the theoretical path.

## 1. The code path to freeze

All paths under `src/axiomm/analysis/quant/`.

| Stage | Public entry point | Returns |
|-------|--------------------|---------|
| k-factors | `compute_k_factors(elements, *, excitation_kev, reference="Si")` — `kfactors.py:43` | `KFactorSet` |
| quantify | `quantify(peaks, kfactors, elements, *, reference_name=None)` — `cliff_lorimer.py:42`; `quantify_cluster_means(...)` — `cliff_lorimer.py:207` | `QuantResult` |
| reliability | `assess_reliability(quant, *, pixel_count, heterogeneity, total_counts, config=None, cluster_id=None)` — `reliability.py:163`; `assess_cluster_reliability(...)` — `reliability.py:271`; `validate_reliability(report)` — `reliability.py:101` | `ReliabilityReport` |
| persistence | `write_/read_{kfactors,quant,reliability}` — `io.py` (`SCHEMA_VERSION = 3`, `io.py:41`) | `Path` / dataclass |

k-factor definition: `k_{i,ref} = S_ref / S_i` from theoretical fluorescence
cross-sections (`kfactors.py:117`).

## 2. Inputs, defaults and magic numbers

- **Excitation energy is required; there is no baked beamline value**
  (`kfactors.py:16,67`) — good, keep it that way.
- **Reference element default `"Si"`** lives only as a parameter default
  (`kfactors.py:43`). *Not covered by any test.*
- **`ReliabilityConfig` defaults** (`reliability.py:51-64`): `min_pixel_count=20`,
  `max_heterogeneity=0.15`, `min_total_counts=1.0e4`, `count_floor=50.0`,
  `element_count_floors={}`. **Only `count_floor==50.0` is pinned by a test**
  (`tests/analysis/test_quant_reliability.py:30`); the other three can drift
  silently.
- **Physical model omissions** (`kfactors.py:1-17`): detector efficiency and
  geometry, absorption / self-absorption, and secondary fluorescence are all
  omitted; oxygen is derived by stoichiometry (no measured-O mode). These
  omissions are exactly what standards validation will quantify.

## 3. Outputs and provenance

- `KFactorSet` (`models.py:11`): `k_factors`, `sensitivities` (Sᵢ), `reference_element`,
  `excitation_kev`, `provenance`, `diagnostics`.
- `QuantResult` (`models.py:23`): `wt_percent_element` (cation basis),
  `wt_percent_oxide`, `net_intensities`, `gross_intensities`,
  `background_per_channel`, `window_channels`, `observation_status`
  (`OBSERVATION_STATUSES`, `models.py:60`), `cluster_id`, `provenance`,
  `diagnostics`.
- `ReliabilityReport` (`reliability.py:89`): `cluster_status`, `element_status`,
  `reasons`, `cluster_id`, `provenance`, `diagnostics`.
- **Provenance** records the theoretical-model caveat and parameters:
  `kfactors.py:120-133` (incl. `_PHYSICAL_MODEL` caveat string, `xraylib_version`,
  `xraylib_backend`, `excitation_kev`, `reference`), chained through
  `cliff_lorimer.py:178-196` and `reliability.py:249-263` (all thresholds + inputs).

## 4. Theoretical-vs-validated boundary — currently documentation-only

The distinction is asserted in docstrings and the reliability vocabulary
(`kfactors.py:1-17`, `models.py:24-30`, `cliff_lorimer.py:6-10`,
`reliability.py:9-18`, and `docs/user/analysis.md` §§5–7 and "Scientific
assumptions & limitations"). **It is not enforced in code:** no field marks a
result as theoretical vs standards-validated, and nothing prevents a `QuantResult`
from being consumed as if validated. The only conservative guardrail is that a
cluster can earn at best `reportable_estimate`, never `"quantitative"`.

## 5. Freeze checklist (do before validation starts)

Pinning tests / changes required so the baseline cannot move under validation:

- [x] **Pin `reference="Si"` default** in `compute_k_factors` with an explicit test
      — done 2026-11-12 (`test_quant_kfactors.py::test_default_reference_is_si`,
      via the fake backend).
- [x] **Pin `ReliabilityConfig` defaults** `min_pixel_count=20`,
      `max_heterogeneity=0.15`, `min_total_counts=1.0e4` — done 2026-11-12
      (`test_quant_reliability.py`: defaults + inclusive-boundary tests).
- [ ] **Add a golden, xraylib-version-tagged k-factor value test.** The only
      xraylib-dependent test is `importorskip`'d and asserts structure, not
      numbers (`test_quant_kfactors.py:46`); k-factor values are xraylib-version
      sensitive. The CI `test-scientific` job now installs xraylib, so this test
      will actually run.
- [ ] **Assert a specific `xraylib_version`** in the validation baseline rather
      than accepting `getattr(xl, "__version__", "unknown")` (`kfactors.py:128`).
- [ ] **Freeze the provenance parameter schema** (exact key set + values) for
      k-factors/quantify/reliability so the audit trail cannot drift.
- [x] **Pin `OBSERVATION_STATUSES` assignment** (`measured_positive` /
      `measured_zero` / `not_measured`) — done 2026-11-12
      (`test_quant_cliff_lorimer.py::test_observation_status_distinguishes_...`).
      Note: `invalid` is vocabulary only — negative/non-finite/incoherent facts
      raise before a result is returned, so it is not a normal production branch.
- [ ] **Freeze the provenance parameter schema** (exact key set per kind) — still
      open; pin against the fake backend + a deterministic reliability fixture.
- [ ] **Add an explicit calibration-state field** on `KFactorSet`/`QuantResult`.
      **Deferred** (2026-11-12, Francesco): sound and matches this plan, but it
      changes no numbers and its schema-v4 persistence break is not on the critical
      path to the first-paper (Isra) deliverables. Do the lean in-memory version in
      a post-Isra chunk; only break persistence when a second calibration state
      actually exists (or decouple the shared quant schema first).
- [x] **Reconcile stale spec**: done 2026-11-12 — `stage_two_S3c3_reliability_design.md`
      §3.2–§3.4 snippets now carry a "superseded" marker pointing at the shipped
      vocabulary (`count_floor`, `reportable_estimate`, …).

## 6. Validation procedure (outline, after freeze)

1. Freeze the surface above (tests + the calibration-state field).
2. Acquire/measure known standards; record excitation energy, geometry, detector,
   and xraylib version alongside each result.
3. Run the frozen pipeline; compare `wt_percent_*` against standard compositions;
   define acceptance thresholds (e.g. relative error bounds per major element).
4. Only then introduce physical corrections (absorption/ZAF, detector efficiency)
   as **new, versioned** code paths and a new calibration state — never by editing
   the theoretical estimator in place.

## 7. What must NOT happen

- Do not relabel the current estimate as "validated" or "quantitative".
- Do not weaken the reliability gate or the abstention behaviour to make numbers
  look publishable.
- Do not bake a beamline excitation energy or detector correction into the
  theoretical path.
