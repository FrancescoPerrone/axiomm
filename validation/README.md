# AXIOMM v0.1 external validation — harness

Implements the ungated pilot comparisons (C1, C2, C3, C6, C7, C8) from
`docs/dev/v0.1_acceptance_criteria.md` and
`docs/dev/v0.1_external_validation_preregistration.md`. The frozen `src/axiomm`
is **not** modified; this harness only calls AXIOMM's public API and the pinned
comparators (`ENVIRONMENT.md`).

## Preregistration discipline

The **sealed protocol** — `generator.py`, `metrics.py`, `oracle.py` (C3 analytic
fixture), `protocol.py` (scenario grid, strata, seeds, pilot/held-out allocation,
`manifest_hash`) and the harness/metric code — is committed **before** any result.
`run_pilot.py` then produces `results/` in one execution. The **held-out** seed
range (`protocol.HELDOUT_SEED_BASE`) is reserved and untouched by the pilot; it is
opened only after the C1 margin is locked and signed off.

## Files

| file | role |
|---|---|
| `generator.py` | independent synthetic XRF generator; truth = within-window net |
| `metrics.py` | signed rel error, 95% CI of the mean, margin selection, detection policy |
| `oracle.py` | C3 hand-derived Cliff–Lorimer oracle + eXSpy + the analytic fixture |
| `protocol.py` | sealed scenario grid, strata, seeds, pilot/held-out split, manifest hash |
| `harness.py` | per-comparison runners (C1,C2,C3,C6,C7,C8) |
| `run_pilot.py` | runs the ungated pilot; writes `results/pilot_results.json` + `PILOT_SUMMARY.md` |
| `ENVIRONMENT.md` | pinned comparator versions + eXSpy convention |
| `results/` | pilot outputs (produced by the run, committed after) |

## Run

```
PYTHONPATH=src python validation/run_pilot.py     # from the repo root, in the pinned env
```

## Scope / stop rule

Only the **ungated** comparisons run here. C4 (map-level spatial) and confirmatory
C5 (false-discovery/abstention) are gated on Tier-A independent references and are
not executed. The frozen scientific contract and the P0/P1 stop rule remain in
force; only a reproducible P0/P1 result may reopen the release candidate. The
held-out confirmatory set is not opened without sign-off.
