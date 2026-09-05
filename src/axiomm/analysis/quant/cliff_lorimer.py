"""Cliff-Lorimer quantification: net intensities + k-factors -> wt%.

Composes S3b peaks, S3c-1 k-factors, and S3a element data. Reports the
numbers only; reliability judgments belong to S3c-3.

**Scientific caveat.** The weight percents are an *uncorrected theoretical
sensitivity-ratio estimate*: they apply the k-factor ratios (see
:mod:`axiomm.analysis.quant.kfactors`) and Cliff-Lorimer closure, and
nothing else. They are not a validated quantitative composition. See
``docs/user/analysis.md`` (Scientific assumptions & limitations).

Input validation (no silent propagation of bad data):

* k-factors must be finite and strictly positive.
* net intensities must be finite and non-negative.
* every element carried by the k-factors must have a matching ``ElementRef``
  (no element is silently dropped and the remainder renormalised to 100%).
* atomic weights must be finite and positive; oxide stoichiometry must be
  well-formed.
"""

from __future__ import annotations

import math

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.models import QuantResult


def _check_finite(name: str, value: float, *, positive: bool = False,
                  non_negative: bool = False) -> None:
    """Raise :class:`PayloadValidationError` unless ``value`` is admissible."""
    if not math.isfinite(value):
        raise PayloadValidationError(f"{name} must be finite; got {value!r}.")
    if positive and value <= 0:
        raise PayloadValidationError(f"{name} must be > 0; got {value!r}.")
    if non_negative and value < 0:
        raise PayloadValidationError(f"{name} must be >= 0; got {value!r}.")


def quantify(peaks, kfactors, elements, *, reference_name: str | None = None) -> QuantResult:
    """Cliff-Lorimer element + oxide wt% for one spectrum's peaks.

    ``reference_name`` optionally records the reference-library identity in
    provenance (the element list alone does not carry it).
    """
    k = dict(kfactors.k_factors)
    if not k:
        raise PayloadValidationError("k-factor set is empty.")
    reference = kfactors.reference_element
    if reference not in k:
        raise PayloadValidationError(
            f"reference element {reference!r} not in k-factors {sorted(k)}."
        )

    # --- k-factor validity: finite and strictly positive -----------------
    for sym, kv in k.items():
        _check_finite(f"k-factor for {sym!r}", float(kv), positive=True)

    # --- oxygen is derived by stoichiometry, never a k-factor element -----
    # Measuring O as a cation *and* adding it via oxide stoichiometry would
    # double-count oxygen. There is no measured-oxygen mode yet (finding 9).
    if "O" in k:
        raise PayloadValidationError(
            "'O' must not be a k-factor element: oxygen is derived by oxide "
            "stoichiometry, and quantifying it directly would double-count it. "
            "A measured-oxygen mode is not implemented."
        )

    # --- element reference table: no duplicates --------------------------
    el_by_sym: dict[str, object] = {}
    for e in elements:
        if e.symbol in el_by_sym:
            raise PayloadValidationError(f"duplicate ElementRef for symbol {e.symbol!r}.")
        el_by_sym[e.symbol] = e

    # --- complete coverage: every measured element must be described -----
    missing = sorted(sym for sym in k if sym not in el_by_sym)
    if missing:
        raise PayloadValidationError(
            f"no ElementRef for k-factor element(s) {missing}; refusing to "
            "drop them and renormalise the remainder to 100%."
        )
    if "O" not in el_by_sym:
        raise PayloadValidationError(
            "element 'O' must be among elements for oxide conversion."
        )

    # --- net intensities: finite, non-negative; retain raw peak facts ----
    meas_by_label = {m.label: m for m in peaks.measurements}
    diagnostics: list[Diagnostic] = []
    net: dict[str, float] = {}
    gross: dict[str, float] = {}
    background: dict[str, float] = {}
    window: dict[str, int] = {}
    observation_status: dict[str, str] = {}
    for sym in k:
        m = meas_by_label.get(sym)
        if m is None:
            net[sym] = 0.0
            observation_status[sym] = "not_measured"
            diagnostics.append(
                Diagnostic("info", "element_not_measured",
                           f"element {sym!r} has no measured peak; net set to 0.")
            )
            continue
        _check_finite(f"net intensity for {sym!r}", float(m.net), non_negative=True)
        # Retained LOD/LOQ inputs must be coherent, not just present: gross and
        # background are non-negative and net cannot exceed gross (finding 5).
        _check_finite(f"gross for {sym!r}", float(m.gross), non_negative=True)
        _check_finite(f"background for {sym!r}", float(m.background), non_negative=True)
        if not (isinstance(m.n_channels, int) and not isinstance(m.n_channels, bool)
                and m.n_channels >= 0):
            raise PayloadValidationError(
                f"window channels for {sym!r} must be a non-negative integer; got {m.n_channels!r}."
            )
        if float(m.net) > float(m.gross) + 1e-9:
            raise PayloadValidationError(
                f"net ({m.net}) exceeds gross ({m.gross}) for {sym!r}; incoherent peak facts."
            )
        net[sym] = float(m.net)
        gross[sym] = float(m.gross)
        background[sym] = float(m.background)
        window[sym] = int(m.n_channels)
        observation_status[sym] = "measured_positive" if float(m.net) > 0 else "measured_zero"

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

    # --- oxide conversion (validated stoichiometry) ----------------------
    o_ref = el_by_sym["O"]
    _check_finite("atomic weight of 'O'", float(o_ref.atomic_weight), positive=True)
    aw_o = float(o_ref.atomic_weight)
    oxide_mass: dict[str, float] = {}
    for sym, w in wt_element.items():
        if w <= 0:
            continue
        er = el_by_sym[sym]
        _check_finite(f"atomic weight of {sym!r}", float(er.atomic_weight), positive=True)
        if er.oxide_form is not None:
            name, n_cat, n_o = er.oxide_form
            if not name:
                raise PayloadValidationError(f"element {sym!r} has empty oxide name.")
            if n_cat <= 0 or n_o < 0:
                raise PayloadValidationError(
                    f"element {sym!r} has invalid oxide stoichiometry "
                    f"(n_cation={n_cat}, n_oxygen={n_o})."
                )
            ox_mw = n_cat * er.atomic_weight + n_o * aw_o
            oxide_mass[name] = oxide_mass.get(name, 0.0) + w * ox_mw / (n_cat * er.atomic_weight)
        else:
            oxide_mass[sym] = oxide_mass.get(sym, 0.0) + w  # halogen/element carried as element

    ox_tot = sum(oxide_mass.values())
    wt_oxide = {n: (100.0 * m / ox_tot if ox_tot > 0 else 0.0) for n, m in oxide_mass.items()}

    # --- provenance chain (P9) ------------------------------------------
    prov_k = kfactors.provenance
    kp = prov_k.params if prov_k else {}
    provenance = AnalysisProvenance(
        tool="quant", backend="cliff_lorimer",
        params={
            "reference": reference,
            "reference_name": reference_name,
            "kfactor_values": dict(k),
            "kfactor_method": kp.get("method"),
            "kfactor_line_method": kp.get("line_method"),
            "physical_model": kp.get("physical_model"),
            "xraylib_version": kp.get("xraylib_version"),
            "xraylib_backend": kp.get("xraylib_backend"),
            "excitation_kev": kp.get("excitation_kev"),
            "oxide_forms": {
                sym: list(el_by_sym[sym].oxide_form)
                for sym in k if el_by_sym[sym].oxide_form is not None
            },
            "cluster_id": peaks.cluster_id,
        },
    )
    return QuantResult(
        net_intensities=net, wt_percent_element=wt_element, wt_percent_oxide=wt_oxide,
        reference_element=reference,
        gross_intensities=gross, background_per_channel=background, window_channels=window,
        observation_status=observation_status,
        cluster_id=peaks.cluster_id,
        provenance=provenance, diagnostics=diagnostics,
    )


def quantify_cluster_means(peak_sets, kfactors, elements,
                           *, reference_name: str | None = None) -> tuple[QuantResult, ...]:
    """Quantify each per-cluster peak set, carrying each set's cluster id."""
    return tuple(
        quantify(ps, kfactors, elements, reference_name=reference_name)
        for ps in peak_sets
    )


__all__ = ["quantify", "quantify_cluster_means"]
