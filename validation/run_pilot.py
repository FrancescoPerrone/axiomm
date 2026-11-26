"""Run the ungated v0.1 validation pilot (C1, C2, C3, C6, C7, C8) and write results.

The sealed protocol (generator, metrics, oracle, scenario grid, seeds) is committed
before this produces any result. Outputs:
  results/pilot_results.json   — full machine-readable results
  results/PILOT_SUMMARY.md     — human summary: per-comparison pass, C1 margin, blockers
"""
from __future__ import annotations

import importlib.metadata as im
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import harness
import protocol

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def env_record() -> dict:
    pkgs = {}
    for p in ["PyMca5", "hyperspy", "exspy", "PyXRF", "numpy", "scipy", "xraylib", "fisx"]:
        try:
            pkgs[p] = im.version(p)
        except Exception:
            pkgs[p] = None
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(HERE)).decode().strip()
    except Exception:
        commit = None
    return {"axiomm_commit": commit, "python": sys.version.split()[0],
            "platform": platform.platform(), "machine": platform.machine(),
            "packages": pkgs, "manifest_hash": protocol.manifest_hash()}


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        results = {"environment": env_record()}
        results["C1"] = harness.run_c1()
        results["C2"] = harness.run_c2()
        results["C3"] = harness.run_c3()
        results["C6"] = harness.run_c6(tmp)
        results["C7"] = harness.run_c7()
        results["C8"] = harness.run_c8(tmp)
    (RESULTS / "pilot_results.json").write_text(json.dumps(results, indent=2))
    _write_summary(results)
    print("wrote", RESULTS / "pilot_results.json")
    return 0


def _write_summary(r: dict) -> None:
    env = r["environment"]
    L = []
    L.append("# v0.1 validation pilot — summary\n")
    L.append(f"AXIOMM commit `{env['axiomm_commit']}` · Python {env['python']} · "
             f"manifest `{env['manifest_hash'][:12]}`")
    L.append(f"Comparators: PyMca5 {env['packages'].get('PyMca5')}, "
             f"HyperSpy {env['packages'].get('hyperspy')}, eXSpy {env['packages'].get('exspy')}.\n")

    # C1
    c1 = r["C1"]
    L.append("## C1 — net line intensities vs synthetic truth")
    L.append("| stratum | injected area | mean signed rel err | 95% CI | mean |err| | RMSE |")
    L.append("|---|---|---|---|---|---|")
    for s, v in c1["per_stratum"].items():
        lo, hi = v["ci95_signed"]
        L.append(f"| {s} | {v['injected_area']:.0f} | {v['mean_signed_rel_err']:+.4%} | "
                 f"[{lo:+.4%}, {hi:+.4%}] | {v['mean_abs_rel_err']:.4%} | {v['rmse_signed']:.4%} |")
    margin = c1["proposed_margin"]
    L.append(f"\n**Proposed C1 margin:** "
             + (f"**{margin:.0%}** ({c1['margin_detail']})" if margin is not None
                else "**no margin supported** — return C1 results and leave the margin open.") + "\n")

    # C2
    c2 = r["C2"]
    L.append("## C2 — overlaps / missing / zero")
    for name, d in c2["deterministic"].items():
        L.append(f"- {name}: net={d['net']:.3f} → {'PASS' if d['pass'] else 'FAIL'}")
    nb = c2["noisy_blank"]
    L.append(f"- noisy blanks: {nb['false_detections']}/{nb['replicates']} false detections "
             f"(rate {nb['false_detection_rate']:.4f}, policy net≥{nb['detection_threshold']:.0f}) → "
             f"{'PASS' if nb['pass'] else 'FAIL'}")
    L.append(f"\n**C2: {'PASS' if c2['pass'] else 'FAIL'}**\n")

    # C3
    c3 = r["C3"]
    a = c3["analytic_fixture"]
    L.append("## C3 — Cliff–Lorimer arithmetic (numerical equivalence)")
    L.append(f"- analytic fixture I={a['intensities']}, k={a['kfactors']} → expected ratio "
             f"{a['expected_ratio_A_over_B']}; oracle {a['oracle_ratio']:.6f} "
             f"({'PASS' if a['oracle_pass'] else 'FAIL'}), eXSpy {a['exspy_ratio']:.6f} "
             f"({'PASS' if a['exspy_pass'] else 'FAIL'})")
    L.append(f"- rtol={c3['rtol']}, atol={c3['atol']}")
    for name, d in c3["named_ratios"].items():
        L.append(f"- {name}: AXIOMM {d['axiomm']:.10g} vs oracle "
                 f"({'PASS' if d['axiomm_vs_oracle_pass'] else 'FAIL'}) vs eXSpy "
                 f"({'PASS' if d['axiomm_vs_exspy_pass'] else 'FAIL'})")
    L.append(f"\n**C3: {'PASS' if c3['pass'] else 'FAIL'}**\n")

    # C6/C7/C8
    c6, c7, c8 = r["C6"], r["C7"], r["C8"]
    L.append("## C6 — reproducibility")
    L.append(f"- rerun identical: {c6['rerun_identical']}; save/load clusters: "
             f"{c6['saveload_clusters_identical']}; phase map: {c6['saveload_phase_map_identical']} → "
             f"**{'PASS' if c6['pass'] else 'FAIL'}**\n")
    L.append("## C7 — runtime & memory (descriptive)")
    L.append(f"- wall {c7['wall_seconds']} s, peak RSS {c7['peak_rss_mib']} MiB "
             f"({c7['clusters']} clusters)\n")
    L.append("## C8 — provenance")
    L.append(f"- top-level complete: {all(c8['top_level_present'].values())}; config complete: "
             f"{all(c8['config_present'].values())}; round-trip faithful: "
             f"{c8['roundtrip_faithful']} → **{'PASS' if c8['pass'] else 'FAIL'}**\n")

    # blockers
    L.append("## Evidence-backed release blockers")
    blockers = []
    if not c2["pass"]:
        blockers.append("C2: AXIOMM fabricated/suppressed evidence on a designed fixture (P1).")
    if not c3["pass"]:
        blockers.append("C3: Cliff–Lorimer arithmetic diverged from the oracle/eXSpy at the "
                        "locked numerical tolerance (P1).")
    if not c6["pass"]:
        blockers.append("C6: result/provenance not reproducible across rerun or save/load (P1).")
    if not c8["pass"]:
        blockers.append("C8: required provenance missing or not faithful after save/load (P1).")
    L.append("- " + ("\n- ".join(blockers) if blockers else "**None** among the ungated comparisons.")
             + "\n")
    L.append("C4/C5 remain gated on Tier-A independent references. Held-out confirmatory set "
             "NOT opened. Returned for sign-off before the held-out run.")
    (RESULTS / "PILOT_SUMMARY.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
