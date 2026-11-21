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


def fused_k_factors(element_refs, source_energy, *, reference, _compute=None) -> KFactorSet:
    """A :class:`KFactorSet` with each element's k-factor at its measurement energy.

    ``source_energy`` maps ``symbol -> excitation_kev`` (``None`` elements are
    skipped). Each element's sensitivity is taken at its own energy, and
    ``k_i = S_ref(E_ref) / S_i(E_i)`` so all elements land on one footing. The
    xraylib sensitivity source is injectable (``_compute``) so the logic tests
    without xraylib. Per-element source energies are recorded in provenance.
    """
    compute = _compute or compute_k_factors
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
    k_factors = {sym: s_ref / sensitivities[sym] for sym in source}
    return KFactorSet(
        k_factors=k_factors, sensitivities=dict(sensitivities),
        reference_element=reference, excitation_kev=e_ref,
        provenance=AnalysisProvenance(
            tool="fusion", backend="cross_energy_kfactors",
            params={"source_energy_kev": {s: e for s, e in source.items()},
                    "reference_element": reference, "reference_energy_kev": e_ref,
                    "method": "per-element k-factor at best-excited energy "
                              "(I0+live-time+dead-time normalized intensities)"}),
        diagnostics=diagnostics)


__all__ = ["fuse_net_intensities", "fused_k_factors"]
