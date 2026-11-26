"""Per-comparison runners for the v0.1 validation pilot (ungated: C1,C2,C3,C6,C7,C8).

Calls only AXIOMM's public API and the pinned comparators; the frozen src/ is not
modified. Each runner returns a JSON-serialisable result dict.
"""
from __future__ import annotations

import time

import numpy as np

import generator
import metrics
import oracle
import protocol


# ---------------------------------------------------------------------------
# C1 — net line intensities vs synthetic truth (primary); margin by pilot rule
# ---------------------------------------------------------------------------
def run_c1(seed_base: int = protocol.PILOT_SEED_BASE, locked_margin=None,
           with_pymca: bool = False) -> dict:
    from axiomm.analysis.peaks import NetIntensityMeasurer
    from axiomm.analysis.peaks.net_intensity import PeakWindowConfig
    assert PeakWindowConfig().half_width_kev == generator.HALF_WIDTH_KEV, \
        "generator window must match the measurer window"
    axis = generator.make_axis(**protocol.AXIS)
    measurer = NetIntensityMeasurer()
    line_energies = {lbl: e for lbl, e in protocol.LINES}
    if with_pymca:
        import pymca_adapter

    per_stratum: dict[str, dict] = {}
    for si, (sname, area) in enumerate(protocol.HIGH_SIGNAL_STRATA.items()):
        lines = [(lbl, e, protocol.LINE_SIGMA_KEV, area) for lbl, e in protocol.LINES]
        ax_signed, ax_abs, py_signed = [], [], []
        for rep in range(protocol.N_REPLICATES):
            seed = protocol.stratum_seed(seed_base, si, rep)
            counts, truth = generator.generate(axis, lines, protocol.BACKGROUND_PER_CH, seed)
            pset = measurer.measure(counts, axis, line_energies)
            for m in pset.measurements:
                e = metrics.signed_rel_error(m.net, truth[m.label])
                ax_signed.append(e)
                ax_abs.append(abs(e))
            if with_pymca:
                for lbl, cen in protocol.LINES:
                    pn = pymca_adapter.pymca_net_in_window(counts, axis, cen)
                    if np.isfinite(pn):
                        py_signed.append(metrics.signed_rel_error(pn, truth[lbl]))
        a_mean, a_lo, a_hi, a_n = metrics.ci95_mean(ax_signed)
        entry = {"injected_area": area, "axiomm": {
            "n_obs": a_n, "mean_signed_rel_err": a_mean, "ci95_signed": [a_lo, a_hi],
            "mean_abs_rel_err": float(np.mean(ax_abs)), "rmse_signed": metrics.rmse(ax_signed)}}
        if with_pymca:
            p_mean, p_lo, p_hi, p_n = metrics.ci95_mean(py_signed)
            entry["pymca_diagnostic"] = {  # both vs injected truth; secondary (not margin-driving)
                "n_obs": p_n, "mean_signed_rel_err": p_mean, "ci95_signed": [p_lo, p_hi],
                "rmse_signed": metrics.rmse(py_signed)}
        per_stratum[sname] = entry

    ci_by = {s: tuple(v["axiomm"]["ci95_signed"]) for s, v in per_stratum.items()}
    out = {"primary_reference": "synthetic_truth", "per_stratum": per_stratum,
           "pymca_secondary": bool(with_pymca)}
    if locked_margin is not None:
        passed = metrics.within_margin(ci_by, locked_margin)
        out.update({"locked_margin": locked_margin, "pass": bool(passed),
                    "detail": f"every high-signal stratum CI within ±{locked_margin:.0%}"
                              if passed else "a stratum CI exceeds the locked margin"})
    else:
        margin, detail = metrics.select_margin(ci_by)
        out.update({"candidate_margins": list(metrics.C1_CANDIDATE_MARGINS),
                    "proposed_margin": margin, "margin_detail": detail})
    return out


# ---------------------------------------------------------------------------
# C2 — overlaps / missing / zero: exact state semantics + noisy-blank false detect
# ---------------------------------------------------------------------------
def _obs_state(m) -> str:
    """AXIOMM observation state from the measurer output: a line outside the axis is
    not_measured; otherwise net > 0 -> measured_positive, else measured_zero."""
    if not m.in_range:
        return "not_measured"
    return "measured_positive" if m.net > 0 else "measured_zero"


def run_c2(blank_seed_base: int = protocol.C2_BLANK_SEED_BASE) -> dict:
    from axiomm.analysis.peaks import NetIntensityMeasurer
    from axiomm.analysis.quant.overlaps import detect_line_overlaps
    from axiomm.pipeline import PipelineConfig
    axis = generator.make_axis(**protocol.AXIS)
    meas = NetIntensityMeasurer()
    res = PipelineConfig().line_resolution_kev   # AXIOMM's declared resolution policy
    deterministic: dict[str, dict] = {}

    # (a) clear peak (noiseless) -> measured_positive, a detection
    counts, _ = generator.generate(axis, [("Si", 1.740, 0.02, 20000.0)], 5.0, seed=42, poisson=False)
    m = meas.measure(counts, axis, {"Si": 1.740}).measurements[0]
    deterministic["clear_peak"] = {"net": m.net, "observation_state": _obs_state(m),
                                   "is_detection": metrics.is_detection(m.net),
                                   "pass": bool(_obs_state(m) == "measured_positive")}

    # (b) zero window (background only, noiseless) -> measured_zero, NOT a detection
    counts, _ = generator.generate(axis, [], 5.0, seed=42, poisson=False)
    m = meas.measure(counts, axis, {"Si": 1.740}).measurements[0]
    deterministic["zero_window"] = {"net": m.net, "observation_state": _obs_state(m),
                                    "is_detection": metrics.is_detection(m.net),
                                    "pass": bool(_obs_state(m) == "measured_zero"
                                                 and not metrics.is_detection(m.net))}

    # (c) line outside the axis (unavailable) -> not_measured, no fabricated net
    m = meas.measure(counts, axis, {"Zz": 99.0}).measurements[0]
    deterministic["unavailable_out_of_range"] = {"net": m.net, "observation_state": _obs_state(m),
                                                 "pass": bool(_obs_state(m) == "not_measured"
                                                              and m.net == 0.0)}

    # (d) unresolved overlap: two lines within the resolution policy must be flagged
    #     unresolved (AXIOMM must not claim to resolve them); a well-separated pair must not.
    unresolved = detect_line_overlaps(protocol.C2_OVERLAP_UNRESOLVED, res)
    resolved = detect_line_overlaps(protocol.C2_OVERLAP_RESOLVED, res)
    unres_flagged = bool(unresolved and set(unresolved[0]) == set(protocol.C2_OVERLAP_UNRESOLVED))
    res_not_flagged = bool(len(resolved) == 0)
    overlap = {"resolution_kev": res,
               "unresolved_pair_flagged_unresolved": unres_flagged,
               "resolved_pair_not_flagged": res_not_flagged,
               "pass": bool(unres_flagged and res_not_flagged)}

    # noisy blanks -> false-detection rate under the declared policy (net >= floor)
    false_det = 0
    for rep in range(protocol.C2_BLANK_REPLICATES):
        counts, _ = generator.generate(axis, [], 5.0, seed=blank_seed_base + rep, poisson=True)
        if metrics.is_detection(meas.measure(counts, axis, {"Si": 1.740}).measurements[0].net):
            false_det += 1
    noisy = {"replicates": protocol.C2_BLANK_REPLICATES, "false_detections": false_det,
             "false_detection_rate": false_det / protocol.C2_BLANK_REPLICATES,
             "detection_threshold": metrics.DETECTION_THRESHOLD, "pass": bool(false_det == 0)}

    ok = all(d["pass"] for d in deterministic.values()) and overlap["pass"] and noisy["pass"]
    return {"deterministic": deterministic, "overlap": overlap, "noisy_blank": noisy,
            "pass": bool(ok)}


# ---------------------------------------------------------------------------
# C3 — Cliff-Lorimer arithmetic: numerical equivalence vs hand oracle + eXSpy
# ---------------------------------------------------------------------------
def run_c3() -> dict:
    from axiomm.analysis.mineralogy.reference import ElementRef
    from axiomm.analysis.peaks.models import PeakMeasurement, PeakMeasurementSet
    from axiomm.analysis.quant.cliff_lorimer import quantify
    from axiomm.analysis.quant.kfactors import compute_k_factors
    rtol, atol = protocol.C3_RTOL, protocol.C3_ATOL

    # analytic fixture (recorded expected ratio): oracle + eXSpy vs expected
    fx = oracle.ANALYTIC_FIXTURE
    o_r = oracle.oracle_ratio(fx["intensities"], fx["kfactors"], 0, 1)
    ex = oracle.exspy_fractions(fx["intensities"], fx["kfactors"])
    ex_r = float(ex[0] / ex[1])
    analytic = {"intensities": fx["intensities"], "kfactors": fx["kfactors"],
                "expected_ratio_A_over_B": fx["expected_ratio_A_over_B"],
                "oracle_ratio": o_r, "exspy_ratio": ex_r,
                "oracle_pass": bool(np.isclose(o_r, fx["expected_ratio_A_over_B"], rtol=rtol, atol=atol)),
                "exspy_pass": bool(np.isclose(ex_r, fx["expected_ratio_A_over_B"], rtol=rtol, atol=atol))}

    # named-ratio equivalence on a preregistered positive vector, SAME nets + SAME k
    aw = {"Mg": 24.305, "Al": 26.982, "Si": 28.085, "Ca": 40.078, "Fe": 55.845}
    z = {"Mg": 12, "Al": 13, "Si": 14, "Ca": 20, "Fe": 26}
    le = {"Mg": 1.254, "Al": 1.486, "Si": 1.740, "Ca": 3.690, "Fe": 6.400}
    els = list(protocol.C3_NET_INTENSITIES)
    refs = [ElementRef(e, le[e], aw[e], z[e], None, "Ka") for e in els]   # cation k-factor elements
    kfs = compute_k_factors(refs, excitation_kev=protocol.C3_EXCITATION_KEV,
                            reference=protocol.C3_REFERENCE)
    k = dict(kfs.k_factors)
    nets = protocol.C3_NET_INTENSITIES
    pset = PeakMeasurementSet(tuple(PeakMeasurement(e, le[e], nets[e], nets[e], 0.0, 10, True)
                                    for e in els), cluster_id=0)
    # quantify requires O among the elements for oxide conversion; O is NOT a k-factor
    # element and is not measured — element wt% ratios are over the cations regardless.
    o_ref = ElementRef("O", 0.525, 15.999, 8, None, "Ka")
    axi = quantify(pset, kfs, [*refs, o_ref], reference_name="c3").wt_percent_element
    order = els
    I = [nets[e] for e in order]
    kk = [k[e] for e in order]
    ofr = oracle.oracle_fractions(I, kk)
    exfr = oracle.exspy_fractions(I, kk)

    ratios = {}
    all_pass = analytic["oracle_pass"] and analytic["exspy_pass"]
    for a, b in protocol.C3_RATIOS:
        ia, ib = order.index(a), order.index(b)
        axi_r = float(axi[a] / axi[b])
        o_r2 = float(ofr[ia] / ofr[ib])
        ex_r2 = float(exfr[ia] / exfr[ib])
        p_oracle = bool(np.isclose(axi_r, o_r2, rtol=rtol, atol=atol))
        p_exspy = bool(np.isclose(axi_r, ex_r2, rtol=rtol, atol=atol))
        ratios[f"{a}/{b}"] = {"axiomm": axi_r, "oracle": o_r2, "exspy": ex_r2,
                              "axiomm_vs_oracle_pass": p_oracle, "axiomm_vs_exspy_pass": p_exspy}
        all_pass = all_pass and p_oracle and p_exspy
    return {"rtol": rtol, "atol": atol, "k_factors": k, "analytic_fixture": analytic,
            "named_ratios": ratios, "pass": bool(all_pass)}


# -- small single-energy fixture for C6/C7/C8 --------------------------------
def _fixture():
    from axiomm.analysis.mineralogy.reference import (ElementRef, MineralEndmember,
                                                      MineralogyReference)
    from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
    ny, nx, ne = 6, 8, 400
    rng = np.random.default_rng(0)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)

    def add(sl, lines):
        for cen, amp in lines:
            cube[sl] += amp * np.exp(-((e - cen) ** 2) / (2 * 0.05 ** 2))
    add((slice(None, ny // 2),), [(1.254, 300), (1.740, 300), (3.690, 300)])  # Mg Si Ca
    add((slice(ny // 2, None),), [(1.254, 300), (1.740, 180)])                # Mg Si
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (AxisSpec("y", "navigation", ny, units="µm", scale=1.0, offset=0.0, index_in_array=0),
            AxisSpec("x", "navigation", nx, units="µm", scale=1.0, offset=0.0, index_in_array=1),
            AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2))
    payload = AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d",
                                  intensity_norm=np.full((ny, nx), 100.0))
    els = {"O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
           "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
           "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
           "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka")}
    minerals = (MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "i", basis="atom_counts"),
                MineralEndmember("Diopside", "pyroxene", {"Ca": 1, "Mg": 1, "Si": 2, "O": 6}, None, "i", basis="atom_counts"))
    ref = MineralogyReference(name="valref", version="1", elements=els, minerals=minerals,
                              structural_exclude=frozenset({"O"}), family_display={"olivine": "Ol", "pyroxene": "Px"})
    return payload, ref


def _run_pipeline():
    from axiomm.pipeline import Pipeline
    payload, ref = _fixture()
    return Pipeline(beam_energy_kev=13.55, reference=ref, reference_element="Si",
                    groups=2, components=4, seed=0).run(payload)


# ---------------------------------------------------------------------------
# C6 — reproducibility across reruns + save/load
# ---------------------------------------------------------------------------
def run_c6(tmp) -> dict:
    from axiomm.pipeline import load_result
    r1, r2 = _run_pipeline(), _run_pipeline()
    rerun_match = (r1.clusters == r2.clusters) and (r1.provenance == r2.provenance)
    out = tmp / "c6_bundle"
    r1.save(out)
    back = load_result(out)
    saveload_clusters = (back.clusters == r1.clusters)
    saveload_phase = np.array_equal(np.asarray(back.phase_map), np.asarray(r1.phase_map))
    return {"rerun_identical": bool(rerun_match),
            "saveload_clusters_identical": bool(saveload_clusters),
            "saveload_phase_map_identical": bool(saveload_phase),
            "pass": bool(rerun_match and saveload_clusters and saveload_phase)}


# ---------------------------------------------------------------------------
# C7 — runtime & memory (descriptive)
# ---------------------------------------------------------------------------
def run_c7() -> dict:
    import resource
    t0 = time.perf_counter()
    r = _run_pipeline()
    dt = time.perf_counter() - t0
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # Linux: KiB
    return {"wall_seconds": round(dt, 4), "peak_rss_mib": round(peak_kb / 1024.0, 1),
            "clusters": len(r.clusters), "pass": True}


# ---------------------------------------------------------------------------
# C8 — provenance completeness & round-trip
# ---------------------------------------------------------------------------
def run_c8(tmp) -> dict:
    from axiomm.pipeline import load_result
    r = _run_pipeline()
    prov = r.provenance
    required = ["tool", "software_version", "config", "reference_name", "reference_version",
                "beam_energy_kev"]
    present = {k: (k in prov) for k in required}
    cfg = prov.get("config", {})
    cfg_required = ["groups", "components", "reference", "beam_energy_kev", "reference_element",
                    "seed", "classification", "normalize", "exclude_elements", "line_resolution_kev"]
    cfg_present = {k: (k in cfg) for k in cfg_required}
    out = tmp / "c8_bundle"
    r.save(out)
    prov2 = load_result(out).provenance
    roundtrip = (prov2.get("reference_name") == prov.get("reference_name")
                 and prov2.get("beam_energy_kev") == prov.get("beam_energy_kev")
                 and prov2.get("config", {}).get("seed") == cfg.get("seed"))
    ok = all(present.values()) and all(cfg_present.values()) and roundtrip
    return {"top_level_present": present, "config_present": cfg_present,
            "roundtrip_faithful": bool(roundtrip), "pass": bool(ok)}
