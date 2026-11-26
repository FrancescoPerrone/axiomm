"""Quantification section — per-cluster element / oxide wt% (stage two, S4d).

The wt% are an *uncorrected* theoretical sensitivity-ratio estimate (no matrix
correction), never a validated composition — the reliability section qualifies
them. ``observation_status`` records how each element was observed.
"""

from __future__ import annotations

from axiomm.analysis.reporting.models import ReportSection, Table


def _oxide_key_map(q) -> dict[str, str]:
    """Map each element symbol to the key under which its oxide wt% is stored.

    ``wt_percent_oxide`` is mixed-keyed: oxide-forming cations live under the
    oxide *formula* (``"SiO2"``) while halogens / elements carried as-is live
    under the element *symbol*. The element→formula mapping is recorded in the
    quantifier's provenance (``params["oxide_forms"]``); without it, the symbol
    is the only available key (correct for halogens, degraded for oxides).
    """
    prov = getattr(q, "provenance", None)
    params = getattr(prov, "params", None) or {}
    forms = params.get("oxide_forms", {}) or {}
    out: dict[str, str] = {}
    for sym, form in forms.items():
        if isinstance(form, (list, tuple)) and form:
            out[sym] = form[0]
    return out


class QuantSection:
    id = "quant"

    def applies(self, result) -> bool:
        return bool(getattr(result, "quantification", None))

    def render(self, result, config) -> ReportSection:
        rows = []
        for q in result.quantification:
            cid = q.cluster_id
            status = dict(getattr(q, "observation_status", {}) or {})
            oxide_key = _oxide_key_map(q)
            # Iterate the full observation record, not just measured wt%, so a no-measurement
            # state is visible rather than hidden: a measured value (incl. measured_zero) shows
            # its number, while not_excited / out_of_coverage show "NA" — never a fabricated 0 wt%.
            for el in sorted(set(q.wt_percent_element) | set(status)):
                if el in q.wt_percent_element:
                    # wt_percent_oxide is keyed by oxide formula for oxide-formers, by element
                    # symbol for halogens — resolve the right key per element.
                    name = oxide_key.get(el, el)
                    wt_el = round(float(q.wt_percent_element.get(el, 0.0)), 2)
                    wt_ox = round(float(q.wt_percent_oxide.get(name, 0.0)), 2)
                else:
                    wt_el = wt_ox = "NA"      # no measurement: never a fabricated 0 wt%
                rows.append([cid, el, wt_el, wt_ox, status.get(el, "")])
        table = Table(["cluster", "element", "wt% element", "wt% oxide", "observed as"],
                      rows, "uncorrected wt% estimate")
        note = ("Uncorrected sensitivity-ratio estimate (no matrix correction) — an "
                "exploratory read-out, not a standards-validated composition. "
                "'NA' marks an element with no measurement (not excited, or its line outside "
                "the spectral window); 'measured_zero' is a genuine zero.")
        return ReportSection("quant", "Quantification", [note, table])


__all__ = ["QuantSection"]
