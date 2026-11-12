"""Quant report section — the oxide column must show real oxide wt%.

Regression: ``wt_percent_oxide`` is keyed by oxide formula ("SiO2") for
oxide-forming cations, by element symbol for halogens. The renderer previously
looked it up by element symbol for everything, so every oxide-forming cation
rendered 0.00. The element→formula map lives in provenance ``oxide_forms``.
"""

from __future__ import annotations

from types import SimpleNamespace

from axiomm.analysis.models import AnalysisProvenance
from axiomm.analysis.quant.models import QuantResult
from axiomm.analysis.reporting.section_renderers.quant import QuantSection


def _render(q):
    sec = QuantSection().render(SimpleNamespace(quantification=[q]), config=None)
    table = sec.blocks[1]  # [note, table]
    return {r[1]: r for r in table.rows}  # by element symbol


def test_oxide_column_uses_formula_key_not_element_symbol():
    prov = AnalysisProvenance(
        tool="quant", backend="xraylib",
        params={"oxide_forms": {"Si": ["SiO2", 1, 2], "Fe": ["FeO", 1, 1]}},
    )
    q = QuantResult(
        net_intensities={"Si": 100.0, "Fe": 50.0},
        wt_percent_element={"Si": 50.0, "Fe": 50.0},
        wt_percent_oxide={"SiO2": 62.45, "FeO": 37.55},
        reference_element="Si",
        observation_status={"Si": "measured_positive", "Fe": "measured_positive"},
        cluster_id=0,
        provenance=prov,
    )
    by_el = _render(q)
    assert by_el["Si"][3] == 62.45   # wt% oxide column — not 0.0
    assert by_el["Fe"][3] == 37.55
    assert by_el["Si"][2] == 50.0    # wt% element column unchanged


def test_halogen_carried_as_element_still_reads_by_symbol():
    # Cl has no oxide form: wt_percent_oxide is keyed by the element symbol,
    # and provenance omits it from oxide_forms. The symbol fallback must work.
    prov = AnalysisProvenance(
        tool="quant", backend="xraylib",
        params={"oxide_forms": {"Si": ["SiO2", 1, 2]}},
    )
    q = QuantResult(
        net_intensities={"Si": 80.0, "Cl": 20.0},
        wt_percent_element={"Si": 80.0, "Cl": 20.0},
        wt_percent_oxide={"SiO2": 85.0, "Cl": 15.0},
        reference_element="Si",
        cluster_id=1,
        provenance=prov,
    )
    by_el = _render(q)
    assert by_el["Si"][3] == 85.0
    assert by_el["Cl"][3] == 15.0
