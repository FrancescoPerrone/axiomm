"""Cliff-Lorimer quantification: net intensities + k-factors -> wt%.

Composes S3b peaks, S3c-1 k-factors, and S3a element data. Reports the
numbers only; reliability judgments belong to S3c-3.
"""

from __future__ import annotations

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.models import QuantResult


def quantify(peaks, kfactors, elements) -> QuantResult:
    """Cliff-Lorimer element + oxide wt% for one spectrum's peaks."""
    k = dict(kfactors.k_factors)
    reference = kfactors.reference_element
    if reference not in k:
        raise PayloadValidationError(
            f"reference element {reference!r} not in k-factors {sorted(k)}."
        )
    el_by_sym = {e.symbol: e for e in elements}
    net_map = peaks.net_by_label()

    diagnostics: list[Diagnostic] = []
    net: dict[str, float] = {}
    for sym in k:
        net[sym] = float(net_map.get(sym, 0.0))
        if sym not in net_map:
            diagnostics.append(
                Diagnostic("info", "element_not_measured",
                           f"element {sym!r} has no measured peak; net set to 0.")
            )

    net_ref = net[reference]
    if net_ref > 0:
        conc_rel = {sym: k[sym] * net[sym] / net_ref for sym in k}
    else:
        conc_rel = {sym: k[sym] * net[sym] for sym in k}
        diagnostics.append(
            Diagnostic("warning", "no_reference_intensity",
                       f"reference {reference!r} net intensity is 0; using unnormalized k*I.")
        )

    total = sum(conc_rel.values())
    if total > 0:
        wt_element = {sym: 100.0 * conc_rel[sym] / total for sym in k}
    else:
        wt_element = {sym: 0.0 for sym in k}
        diagnostics.append(
            Diagnostic("warning", "no_signal",
                       "no net signal in any element; weight percents are 0.")
        )

    if "O" not in el_by_sym:
        raise PayloadValidationError(
            "element 'O' must be among elements for oxide conversion."
        )
    aw_o = el_by_sym["O"].atomic_weight
    oxide_mass: dict[str, float] = {}
    for sym, w in wt_element.items():
        er = el_by_sym.get(sym)
        if w <= 0 or er is None:
            continue
        if er.oxide_form is not None:
            name, n_cat, n_o = er.oxide_form
            ox_mw = n_cat * er.atomic_weight + n_o * aw_o
            oxide_mass[name] = oxide_mass.get(name, 0.0) + w * ox_mw / (n_cat * er.atomic_weight)
        else:
            oxide_mass[sym] = oxide_mass.get(sym, 0.0) + w  # halogen/element carried as element

    ox_tot = sum(oxide_mass.values())
    wt_oxide = {n: (100.0 * m / ox_tot if ox_tot > 0 else 0.0) for n, m in oxide_mass.items()}

    prov_k = kfactors.provenance
    provenance = AnalysisProvenance(
        tool="quant", backend="cliff_lorimer",
        params={
            "reference": reference,
            "excitation_kev": prov_k.params.get("excitation_kev") if prov_k else None,
            "kfactor_method": prov_k.params.get("method") if prov_k else None,
        },
    )
    return QuantResult(
        net_intensities=net, wt_percent_element=wt_element, wt_percent_oxide=wt_oxide,
        reference_element=reference, provenance=provenance, diagnostics=diagnostics,
    )


def quantify_cluster_means(peak_sets, kfactors, elements) -> tuple[QuantResult, ...]:
    """Quantify each per-cluster peak set, preserving order (cluster_ids)."""
    return tuple(quantify(ps, kfactors, elements) for ps in peak_sets)


__all__ = ["quantify", "quantify_cluster_means"]
