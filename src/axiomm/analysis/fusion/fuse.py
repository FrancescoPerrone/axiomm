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

from axiomm.analysis.errors import PayloadValidationError
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
                    _compute=None) -> KFactorSet:
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
                    "method": "per-element k-factor at best-excited energy "
                              "(I0+live-time+dead-time normalized intensities)"}),
        diagnostics=diagnostics)


def bridge_cross_calibration(per_energy_net, element_refs, energies, *, reference_energy,
                             edge_fn, _compute=None):
    """Cross-energy scale from **bridge elements** — those excited at ≥2 energies.

    An element measurable at two energies should report the same concentration from
    either; the ratio sets a per-energy multiplicative scale (relative to
    ``reference_energy``) that rebalances the light-vs-mid-Z footing. Returns
    ``({energy: scale}, diagnostics)``. ``per_energy_net`` maps
    ``energy -> {cluster_id: {symbol: net}}``; ``edge_fn(ref) -> edge_keV`` and the
    sensitivity source ``_compute`` are injectable so the logic tests without xraylib.
    """
    compute = _compute or compute_k_factors
    refs_by_sym = {r.symbol: r for r in element_refs}
    energies = sorted(float(e) for e in energies)
    exciting = {r.symbol: [e for e in energies if e > float(edge_fn(r))] for r in element_refs}
    bridge = [s for s, es in exciting.items() if len(es) >= 2]
    diagnostics: list[Diagnostic] = []
    scale = {e: 1.0 for e in energies}
    if not bridge:
        diagnostics.append(Diagnostic(
            "info", "bridge_none",
            "no element is excited by more than one energy; cross-energy scale left at 1."))
        return scale, diagnostics

    sens: dict[tuple, float] = {}
    for e in energies:
        excited = [refs_by_sym[s] for s in exciting if e in exciting[s]]
        if excited:
            ks = compute(excited, excitation_kev=e, reference=excited[0].symbol)
            for sym, s in ks.sensitivities.items():
                sens[(sym, e)] = s

    def concentration(sym, e):
        vals = [per_energy_net[e][c][sym] for c in per_energy_net.get(e, {})
                if per_energy_net[e][c].get(sym, 0.0) > 0]
        s = sens.get((sym, e))
        return (sum(vals) / len(vals)) / s if vals and s and s > 0 else None

    for e in energies:
        if e == reference_energy:
            continue
        ratios = []
        for sym in bridge:
            if e in exciting[sym] and reference_energy in exciting[sym]:
                cr, ce = concentration(sym, reference_energy), concentration(sym, e)
                if cr and ce and ce > 0:
                    ratios.append(cr / ce)
        if ratios:
            scale[e] = _median(ratios)               # true median bridge ratio
            spread = max(ratios) / min(ratios) if min(ratios) > 0 else float("inf")
            diagnostics.append(Diagnostic(
                "info", "bridge_cross_calibration",
                f"{len(ratios)} bridge element(s) set the {e}->{reference_energy} keV cross-energy "
                f"scale to {scale[e]:.3f} (raw spread {spread:.2f}x before correction)."))
        else:
            # bridge elements exist in the group, but none has a usable measured pair
            # at BOTH this energy and the reference energy — scale stays 1 (uncorrected).
            diagnostics.append(Diagnostic(
                "warning", "bridge_unresolved_energy",
                f"no usable bridge pair links {e} keV to the {reference_energy} keV reference; "
                f"its cross-energy scale is left at 1.0 (uncorrected)."))
    return scale, diagnostics


def _median(values):
    """True median: the average of the two middle values for an even count."""
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else 0.5 * (s[mid - 1] + s[mid])


__all__ = ["bridge_cross_calibration", "fuse_net_intensities", "fuse_peak_sets", "fused_k_factors"]
