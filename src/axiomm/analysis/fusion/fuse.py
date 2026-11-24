"""Cross-energy fusion of net intensities + per-element-energy k-factors (S8.3).

Given which energy best excites each element (S8.2) and the per-energy net
intensities measured on each map, fusion does two things:

* :func:`fuse_net_intensities` — pick each element's net intensity from its
  best-excited energy, so every element is measured where it is strongest.
* :func:`fused_k_factors` — build a :class:`KFactorSet` whose each element's
  k-factor is computed **at the energy it was measured**. Per the fundamental-
  parameter model, dividing each normalized intensity by its sensitivity at its
  measurement energy puts an element measured at 2.9 keV and one at 13.55 keV on
  the **same mass-fraction footing** — so the existing single-energy
  :func:`~axiomm.analysis.quant.quantify` consumes the fused set unchanged.

The maps must already be I0 + live-time + dead-time normalized (the orchestration
does that, reusing the single-energy ``intensity_norm`` path). This module is the
energy-agnostic fusion maths; the pipeline hook and the bridge-element check live
in S8.4.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.errors import CrossCalibrationError, PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant import compute_k_factors
from axiomm.analysis.quant.models import KFactorSet


def fuse_net_intensities(per_energy_net, source_energy):
    """Select each element's net intensity from its best-excited energy.

    ``per_energy_net`` maps ``excitation_kev -> {cluster_id: {symbol: net}}``;
    ``source_energy`` maps ``symbol -> chosen_excitation_kev`` (``None`` =
    not excited by any supplied energy). Returns ``({cluster_id: {symbol: net}},
    diagnostics)``; not-excited elements are omitted with a diagnostic.
    """
    source = {s: e for s, e in source_energy.items() if e is not None}
    not_excited = sorted(s for s, e in source_energy.items() if e is None)
    diagnostics: list[Diagnostic] = []
    if not_excited:
        diagnostics.append(Diagnostic(
            "info", "fusion_not_excited",
            f"elements excited by no supplied energy, omitted from the fused "
            f"composition: {not_excited}."))
    clusters = sorted({c for d in per_energy_net.values() for c in d})
    fused: dict = {}
    for c in clusters:
        row: dict = {}
        for sym, e in source.items():
            v = per_energy_net.get(e, {}).get(c, {}).get(sym)
            if v is not None:
                row[sym] = float(v)
        fused[c] = row
    return fused, diagnostics


def fuse_peak_sets(per_energy_peak_sets, source_energy):
    """Build fused per-cluster peak sets: each element's measurement from its
    best-excited energy.

    ``per_energy_peak_sets`` maps ``excitation_kev -> tuple[PeakMeasurementSet]``
    (one per cluster, aligned by ``cluster_id``); ``source_energy`` maps
    ``symbol -> chosen_excitation_kev`` (``None`` elements are dropped). Returns a
    tuple of fused ``PeakMeasurementSet`` (one per cluster), each carrying only the
    elements excited by some energy, taken from the energy that measures them best.
    """
    from axiomm.analysis.peaks.models import PeakMeasurementSet

    source = {s: e for s, e in source_energy.items() if e is not None}
    index: dict = {}          # energy -> {cluster_id -> {label -> PeakMeasurement}}
    cluster_ids: list | None = None
    for e, psets in per_energy_peak_sets.items():
        index[e] = {ps.cluster_id: {m.label: m for m in ps.measurements} for ps in psets}
        if cluster_ids is None:
            cluster_ids = [ps.cluster_id for ps in psets]

    fused = []
    for cid in (cluster_ids or []):
        measurements = []
        for sym, e in source.items():
            m = index.get(e, {}).get(cid, {}).get(sym)
            if m is not None:
                measurements.append(m)
        fused.append(PeakMeasurementSet(measurements=tuple(measurements), cluster_id=cid))
    return tuple(fused)


def fused_k_factors(element_refs, source_energy, *, reference, scale=None,
                    cross_energy_status=None, _compute=None) -> KFactorSet:
    """A :class:`KFactorSet` with each element's k-factor at its measurement energy.

    ``source_energy`` maps ``symbol -> excitation_kev`` (``None`` elements are
    skipped). Each element's sensitivity is taken at its own energy, and
    ``k_i = S_ref(E_ref) / S_i(E_i)`` so all elements land on one footing.
    ``scale`` is an optional ``{energy: factor}`` cross-energy correction (from the
    bridge-element calibration) folded in as ``k_i *= scale[E_i]``, rebalancing the
    energies. The xraylib sensitivity source is injectable (``_compute``) so the
    logic tests without xraylib; per-element source energies are in provenance.
    """
    compute = _compute or compute_k_factors
    scale = scale or {}
    refs_by_sym = {r.symbol: r for r in element_refs}
    source = {s: float(e) for s, e in source_energy.items() if e is not None}
    if reference not in source:
        raise PayloadValidationError(
            f"reference element {reference!r} is not excited by any supplied energy; "
            "cannot form fused k-factors.")

    by_energy: dict[float, list[str]] = {}
    for sym, e in source.items():
        by_energy.setdefault(e, []).append(sym)

    sensitivities: dict[str, float] = {}
    diagnostics: list[Diagnostic] = []
    for e, syms in by_energy.items():
        els = [refs_by_sym[s] for s in syms]
        ks = compute(els, excitation_kev=e, reference=syms[0])
        sensitivities.update(ks.sensitivities)
        diagnostics.extend(ks.diagnostics)

    e_ref = source[reference]
    s_ref = sensitivities[reference]
    k_factors = {sym: (s_ref / sensitivities[sym]) * float(scale.get(source[sym], 1.0))
                 for sym in source}
    return KFactorSet(
        k_factors=k_factors, sensitivities=dict(sensitivities),
        reference_element=reference, excitation_kev=e_ref,
        provenance=AnalysisProvenance(
            tool="fusion", backend="cross_energy_kfactors",
            params={"source_energy_kev": {s: e for s, e in source.items()},
                    "reference_element": reference, "reference_energy_kev": e_ref,
                    "cross_energy_scale": {e: float(f) for e, f in scale.items()},
                    "cross_energy_status": (dict(cross_energy_status)
                                            if cross_energy_status is not None else None),
                    "method": "per-element k-factor at best-excited energy "
                              "(I0+live-time+dead-time normalized intensities)"}),
        diagnostics=diagnostics)


def bridge_cross_calibration(per_energy_net, element_refs, energies, *, reference_energy,
                             edge_fn, cluster_weights=None, dispersion_limit=2.0,
                             on_low_confidence="flag", eligible=None, _compute=None):
    """Cross-energy scale from **bridge elements** — those excited at ≥2 energies.

    An element measurable at two energies should report the same concentration from
    either; the disagreement sets a per-energy multiplicative scale (relative to
    ``reference_energy``) that rebalances the light-vs-mid-Z footing.

    The estimate is built from **shared spatial support**: for each bridge element
    and each cluster measured (net > 0) at *both* energies, one ratio
    ``(net_ref/S_ref)/(net_e/S_e)``, **weighted** by the cluster's pixel count
    (``cluster_weights``, ``{cluster_id: n_pixels}``; absent → unit weight). The
    per-energy scale is the **weighted median** of those points. Its adequacy is gated
    on a combined **dispersion** = ``max`` of (a) the ratios' interquartile ratio
    (p75/p25) and (b) how far the weighted estimate sits from the *unweighted* median —
    so neither a broad spread nor a single heavily-weighted outlier cluster can drive
    the scale while the gate reports agreement; a lone point establishes no consistency
    and is always low-confidence. When dispersion exceeds ``dispersion_limit`` the
    bridge is *low confidence* and ``on_low_confidence`` decides: ``"flag"`` applies it
    with a warning, ``"refuse"`` leaves the energy uncorrected (scale 1) with a warning,
    ``"raise"`` raises :class:`~axiomm.analysis.errors.CrossCalibrationError`. An energy
    with **no usable bridge link** is uncalibrated: it keeps scale 1 (warned), or raises
    under ``"raise"``.

    Returns ``({energy: scale}, {energy: status}, diagnostics)`` where ``status`` is one
    of ``reference`` / ``no_bridge_elements`` / ``no_usable_link`` /
    ``refused_low_confidence`` / ``applied_low_confidence`` / ``applied`` — so a scale of
    1.0 is never ambiguous. ``edge_fn(ref) -> edge_keV`` and the sensitivity source
    ``_compute`` are injectable so the logic tests without xraylib.

    The scale is a single per-energy *rebalancing* factor, not a per-element or
    matrix correction; a large dispersion signals the per-energy model is a poor
    fit, which is why it is reported and gated rather than hidden.

    ``eligible`` optionally restricts which bridge points are used to those that
    passed a reliability screen: a set of ``(symbol, energy, cluster_id)`` that
    cleared the net-count floor. A point contributes only when the element is
    eligible at *both* its energy and the reference energy for that cluster.
    ``None`` keeps the legacy behaviour (any shared-support point with net>0).
    """
    compute = _compute or compute_k_factors
    refs_by_sym = {r.symbol: r for r in element_refs}
    energies = sorted(float(e) for e in energies)
    reference_energy = float(reference_energy)
    weights = {int(c): float(w) for c, w in (cluster_weights or {}).items()}
    # Validate at the public computational boundary (a direct caller bypasses PipelineConfig).
    if not (isinstance(dispersion_limit, (int, float)) and not isinstance(dispersion_limit, bool)
            and np.isfinite(dispersion_limit) and dispersion_limit >= 1.0):
        raise PayloadValidationError(
            f"dispersion_limit must be a finite number >= 1.0; got {dispersion_limit!r}.")
    if on_low_confidence not in ("flag", "refuse", "raise"):
        raise PayloadValidationError(
            f"on_low_confidence must be 'flag', 'refuse', or 'raise'; got {on_low_confidence!r}.")
    if reference_energy not in energies:
        raise PayloadValidationError(
            f"reference_energy {reference_energy} keV is not among the supplied energies {energies}.")
    bad_w = sorted(c for c, w in weights.items() if not (np.isfinite(w) and w > 0))
    if bad_w:
        raise PayloadValidationError(
            f"cluster_weights must be finite and > 0; invalid for cluster(s) {bad_w}.")
    exciting = {r.symbol: [e for e in energies if e > float(edge_fn(r))] for r in element_refs}
    bridge = [s for s, es in exciting.items() if len(es) >= 2]
    diagnostics: list[Diagnostic] = []
    scale = {e: 1.0 for e in energies}
    # Per-energy outcome, so a scale of 1.0 is never ambiguous downstream: the reference is
    # 1.0 by definition, and every other way an energy ends at 1.0 (no bridge elements, no
    # usable link, refused for low confidence) is distinguished from an applied factor that
    # happens to be ~1.0. Carried into provenance.
    status = {e: ("reference" if e == reference_energy else "pending") for e in energies}
    if not bridge:
        for e in energies:
            if e != reference_energy:
                status[e] = "no_bridge_elements"
        diagnostics.append(Diagnostic(
            "info", "bridge_none",
            "no element is excited by more than one energy; cross-energy scale left at 1."))
        return scale, status, diagnostics

    sens: dict[tuple, float] = {}
    for e in energies:
        excited = [refs_by_sym[s] for s in exciting if e in exciting[s]]
        if excited:
            ks = compute(excited, excitation_kev=e, reference=excited[0].symbol)
            for sym, s in ks.sensitivities.items():
                sens[(sym, e)] = s

    def points_for(e):
        """``([(ratio, weight)], {contributing symbols})`` over shared-support clusters."""
        pts: list[tuple[float, float]] = []
        used: set[str] = set()
        net_e, net_r = per_energy_net.get(e, {}), per_energy_net.get(reference_energy, {})
        for sym in bridge:
            if not (e in exciting[sym] and reference_energy in exciting[sym]):
                continue
            s_e, s_r = sens.get((sym, e)), sens.get((sym, reference_energy))
            if not (s_e and s_e > 0 and s_r and s_r > 0):
                continue
            for c in set(net_e) & set(net_r):
                # Reliability screen (#4): a bridge point sets the cross-energy scale only
                # when the element clears its net-count floor at BOTH energies for that
                # cluster (not merely net>0), so a near-floor noisy measurement cannot drag
                # the rebalancing factor. ``eligible`` holds (symbol, energy, cluster) that
                # passed; ``None`` keeps the legacy net>0 behaviour.
                if eligible is not None and not (
                        (sym, e, int(c)) in eligible and (sym, reference_energy, int(c)) in eligible):
                    continue
                ne, nr = net_e[c].get(sym, 0.0), net_r[c].get(sym, 0.0)
                if ne > 0 and nr > 0:
                    ratio = (nr / s_r) / (ne / s_e)
                    if np.isfinite(ratio) and ratio > 0:
                        pts.append((ratio, weights.get(int(c), 1.0)))
                        used.add(sym)
        return pts, used

    for e in energies:
        if e == reference_energy:
            continue
        pts, used = points_for(e)
        if not pts:
            # No usable bridge link: this energy is uncalibrated.
            status[e] = "no_usable_link"
            msg = (f"no usable bridge pair links {e} keV to the {reference_energy} keV "
                   "reference; the energy is uncalibrated")
            if on_low_confidence == "raise":
                raise CrossCalibrationError(msg + " (bridge_low_confidence='raise').")
            diagnostics.append(Diagnostic(
                "warning", "bridge_unresolved_energy",
                msg + "; cross-energy scale left at 1.0 (uncorrected)."))
            continue
        est = _weighted_median(pts)
        ratios = [r for r, _ in pts]
        if len(ratios) >= 2:
            # (a) robust spread of the ratios, and (b) how far weighting moves the estimate
            # from the unweighted median — so a single heavily-weighted outlier cannot drive
            # the scale while the gate reports agreement.
            q1, q3 = (float(x) for x in np.percentile(ratios, [25, 75]))
            iqr = q3 / q1 if q1 > 0 else float("inf")
            umed = _weighted_median([(r, 1.0) for r in ratios])
            shift = max(est / umed, umed / est) if (est > 0 and umed > 0) else float("inf")
            dispersion = max(iqr, shift)
            detail = f"IQR {iqr:.2f}x, weighting-shift {shift:.2f}x"
            low = dispersion > dispersion_limit
        else:
            # one point establishes no measured consistency
            detail = "single point (no cross-check)"
            low = True
        base = (f"{len(pts)} bridge point(s) from {len(used)} element(s) ({sorted(used)}) "
                f"for {e}->{reference_energy} keV: weighted-median scale {est:.3f}; "
                f"{detail} (limit {dispersion_limit}).")
        if low and on_low_confidence == "raise":
            raise CrossCalibrationError(base + " Refusing per bridge_low_confidence='raise'.")
        if low and on_low_confidence == "refuse":
            status[e] = "refused_low_confidence"
            diagnostics.append(Diagnostic(
                "warning", "bridge_low_confidence",
                base + " Low confidence: correction refused, scale left at 1.0."))
            continue
        scale[e] = est
        status[e] = "applied_low_confidence" if low else "applied"
        diagnostics.append(Diagnostic(
            "warning" if low else "info",
            "bridge_low_confidence" if low else "bridge_cross_calibration",
            base + (" Low confidence: applied with caution." if low else " Applied.")))
    return scale, status, diagnostics


def _weighted_median(points):
    """Weighted median of ``[(value, weight)]``; averages the two central values
    when the cumulative weight splits exactly in half (so equal weights reproduce
    the ordinary median, incl. the even-count average)."""
    pts = sorted(points, key=lambda p: p[0])
    total = sum(w for _, w in pts)
    if total <= 0:
        vals = [v for v, _ in pts]
        n = len(vals)
        return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])
    half, acc = total / 2.0, 0.0
    for i, (v, w) in enumerate(pts):
        acc += w
        if acc > half:
            return v
        if acc == half:
            return 0.5 * (v + pts[i + 1][0]) if i + 1 < len(pts) else v
    return pts[-1][0]


__all__ = ["bridge_cross_calibration", "fuse_net_intensities", "fuse_peak_sets", "fused_k_factors"]
