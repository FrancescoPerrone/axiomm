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
| `pymca_adapter.py` | C1 **secondary** diagnostic: PyMca Gefit within-window net (same support as AXIOMM + truth); verified on noiseless fixtures |
| `protocol.py` | sealed scenario grid, strata, seeds, pilot/held-out split (disjoint bases), overlap fixtures, manifest hash |
| `metrics.py` | signed rel error, 95% CI, margin rule, **locked C1 margin ±5%**, detection policy |
| `harness.py` | per-comparison runners (C1,C2,C3,C6,C7,C8); C1 adds the PyMca secondary (both vs truth); C2 records observation states + the unresolved-overlap case |
| `run_pilot.py` | runs an evaluation; writes `results/<mode>_results.json` + `<MODE>_SUMMARY.md` |
| `ENVIRONMENT.md` | pinned comparator versions + eXSpy convention |
| `results/` | pilot + held-out outputs (produced by the run, committed after) |

## Run

```
PYTHONPATH=src python validation/run_pilot.py pilot     # from the repo root, pinned env
PYTHONPATH=src python validation/run_pilot.py heldout   # disjoint seeds; C1 judged vs locked ±5%
```

The **pilot** estimates/verifies and proposes the margin; the **held-out** run uses
the disjoint held-out seed bases, includes the verified PyMca secondary, and judges
C1 against the LOCKED ±5% margin (`metrics.C1_LOCKED_MARGIN`). "Run once" = one
execution of the sealed held-out set.

## Scope / stop rule

Only the **ungated** comparisons run here. C4 (map-level spatial) and confirmatory
C5 (false-discovery/abstention) are gated on Tier-A independent references and are
not executed. The frozen scientific contract and the P0/P1 stop rule remain in
force; only a reproducible P0/P1 result may reopen the release candidate.
