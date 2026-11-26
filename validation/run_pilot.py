"""Run a v0.1 validation evaluation (ungated: C1,C2,C3,C6,C7,C8) and write results.

Usage:  python run_pilot.py [pilot|heldout]   (default: pilot)

The sealed protocol (generator, metrics, oracle, scenario grid, seeds) is committed
before any result. The HELD-OUT run uses the disjoint held-out seed bases, includes
the verified PyMca secondary diagnostic, and judges C1 against the LOCKED margin.
Outputs results/<mode>_results.json and results/<MODE>_SUMMARY.md.
"""
from __future__ import annotations

import importlib.metadata as im
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import generator
import harness
import metrics
import protocol
import pymca_adapter

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


def main(mode: str = "pilot") -> int:
    RESULTS.mkdir(exist_ok=True)
    heldout = mode == "heldout"
    results = {"mode": mode, "environment": env_record()}

    if heldout:
        axis = generator.make_axis(**protocol.AXIS)
        vlines = [(lbl, e, protocol.LINE_SIGMA_KEV, 20000.0) for lbl, e in protocol.LINES]
        results["pymca_adapter_verification"] = pymca_adapter.verify_adapter(
            axis, vlines, protocol.BACKGROUND_PER_CH)
        results["C1"] = harness.run_c1(seed_base=protocol.HELDOUT_SEED_BASE,
                                       locked_margin=metrics.C1_LOCKED_MARGIN, with_pymca=True)
        results["C2"] = harness.run_c2(blank_seed_base=protocol.C2_BLANK_SEED_BASE_HELDOUT)
    else:
        results["C1"] = harness.run_c1(seed_base=protocol.PILOT_SEED_BASE)
        results["C2"] = harness.run_c2(blank_seed_base=protocol.C2_BLANK_SEED_BASE)

    results["C3"] = harness.run_c3()
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        results["C6"] = harness.run_c6(tmp)
        results["C7"] = harness.run_c7()
        results["C8"] = harness.run_c8(tmp)

    (RESULTS / f"{mode}_results.json").write_text(json.dumps(results, indent=2))
    _write_summary(results, mode)
    print("wrote", RESULTS / f"{mode}_results.json")
    return 0


def _write_summary(r: dict, mode: str) -> None:
    env = r["environment"]
    heldout = mode == "heldout"
    L = [f"# v0.1 validation — {mode} summary\n",
         f"AXIOMM commit `{env['axiomm_commit']}` · Python {env['python']} · "
         f"manifest `{env['manifest_hash'][:12]}`",
         f"Comparators: PyMca5 {env['packages'].get('PyMca5')}, "
         f"HyperSpy {env['packages'].get('hyperspy')}, eXSpy {env['packages'].get('exspy')}.\n"]

    if heldout:
        v = r["pymca_adapter_verification"]
        L.append(f"**PyMca adapter verification** (noiseless pilot fixtures): max rel diff "
                 f"{v['max_rel_diff']:.2e} → {'VERIFIED' if v['verified'] else 'NOT VERIFIED'}\n")

    c1 = r["C1"]
    L.append("## C1 — net line intensities vs synthetic truth")
    hdr = "| stratum | area | AXIOMM mean signed | AXIOMM 95% CI | AXIOMM |err| | RMSE |"
    if c1.get("pymca_secondary"):
        hdr += " PyMca mean signed | PyMca 95% CI |"
    L.append(hdr)
    L.append("|---|---|---|---|---|---|" + ("---|---|" if c1.get("pymca_secondary") else ""))
    for s, v in c1["per_stratum"].items():
        a = v["axiomm"]
        lo, hi = a["ci95_signed"]
        row = (f"| {s} | {v['injected_area']:.0f} | {a['mean_signed_rel_err']:+.4%} | "
               f"[{lo:+.4%}, {hi:+.4%}] | {a['mean_abs_rel_err']:.4%} | {a['rmse_signed']:.4%} |")
        if "pymca_diagnostic" in v:
            p = v["pymca_diagnostic"]
            plo, phi = p["ci95_signed"]
            row += f" {p['mean_signed_rel_err']:+.4%} | [{plo:+.4%}, {phi:+.4%}] |"
        L.append(row)
    if "locked_margin" in c1:
        L.append(f"\n**C1 vs LOCKED margin ±{c1['locked_margin']:.0%}: "
                 f"{'PASS' if c1['pass'] else 'FAIL'}** ({c1['detail']})\n")
    else:
        m = c1["proposed_margin"]
        L.append(f"\n**Proposed C1 margin:** "
                 + (f"{m:.0%} ({c1['margin_detail']})" if m is not None else "no margin supported") + "\n")

    c2 = r["C2"]
    L.append("## C2 — overlaps / missing / zero (with observation states)")
    for name, d in c2["deterministic"].items():
        L.append(f"- {name}: net={d['net']:.3f}, state=`{d['observation_state']}` → "
                 f"{'PASS' if d['pass'] else 'FAIL'}")
    ov = c2["overlap"]
    L.append(f"- unresolved_overlap: unresolved pair flagged={ov['unresolved_pair_flagged_unresolved']}, "
             f"resolved pair not flagged={ov['resolved_pair_not_flagged']} "
             f"(policy {ov['resolution_kev']} keV) → {'PASS' if ov['pass'] else 'FAIL'}")
    nb = c2["noisy_blank"]
    L.append(f"- noisy blanks: {nb['false_detections']}/{nb['replicates']} false detections "
             f"(net≥{nb['detection_threshold']:.0f}) → {'PASS' if nb['pass'] else 'FAIL'}")
    L.append(f"\n**C2: {'PASS' if c2['pass'] else 'FAIL'}**\n")

    c3 = r["C3"]
    a = c3["analytic_fixture"]
    L.append("## C3 — Cliff–Lorimer arithmetic (numerical equivalence)")
    L.append(f"- analytic fixture → expected {a['expected_ratio_A_over_B']}; oracle {a['oracle_ratio']:.6f} "
             f"({'PASS' if a['oracle_pass'] else 'FAIL'}), eXSpy {a['exspy_ratio']:.6f} "
             f"({'PASS' if a['exspy_pass'] else 'FAIL'}); rtol={c3['rtol']}, atol={c3['atol']}")
    for name, d in c3["named_ratios"].items():
        L.append(f"- {name}: AXIOMM vs oracle {'PASS' if d['axiomm_vs_oracle_pass'] else 'FAIL'}, "
                 f"vs eXSpy {'PASS' if d['axiomm_vs_exspy_pass'] else 'FAIL'}")
    L.append(f"\n**C3: {'PASS' if c3['pass'] else 'FAIL'}**\n")

    c6, c7, c8 = r["C6"], r["C7"], r["C8"]
    L.append(f"## C6 — reproducibility → **{'PASS' if c6['pass'] else 'FAIL'}** "
             f"(rerun {c6['rerun_identical']}, save/load {c6['saveload_clusters_identical']})")
    L.append(f"## C7 — runtime {c7['wall_seconds']} s, peak RSS {c7['peak_rss_mib']} MiB (descriptive)")
    L.append(f"## C8 — provenance → **{'PASS' if c8['pass'] else 'FAIL'}** "
             f"(round-trip faithful {c8['roundtrip_faithful']})\n")

    L.append("## Evidence-backed P0/P1 findings")
    blockers = []
    if not c2["pass"]:
        blockers.append("C2 (P1): AXIOMM fabricated/suppressed evidence or mis-handled an overlap.")
    if not c3["pass"]:
        blockers.append("C3 (P1): Cliff–Lorimer arithmetic diverged beyond the locked numerical tolerance.")
    if not c6["pass"]:
        blockers.append("C6 (P1): result/provenance not reproducible across rerun or save/load.")
    if not c8["pass"]:
        blockers.append("C8 (P1): required provenance missing or not faithful after save/load.")
    if heldout and "locked_margin" in c1 and not c1["pass"]:
        blockers.append("C1 (P1): systematic bias vs truth exceeds the locked ±5% margin.")
    L.append("- " + ("\n- ".join(blockers) if blockers else "**None** among the ungated comparisons.") + "\n")
    L.append("## Outstanding release gates")
    L.append("- C4 (map-level spatial) and confirmatory C5 (false-discovery/abstention) remain gated on "
             "Tier-A independent references (imaging/EPMA). The freeze and P0/P1 stop rule remain in force.")
    (RESULTS / f"{mode.upper()}_SUMMARY.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "pilot"))
