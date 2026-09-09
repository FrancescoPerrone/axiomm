"""Ergonomic API chunk 2 — reference helpers + reference-aware measure_peaks.

These remove the hand-wiring pain: deriving in-range cations, line-energy maps and
ElementRef lists (and remembering the structural O) straight from the reference.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.clustering.models import ClusterMeanSpectra
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.peaks import measure_peaks
from axiomm.io.converters.models import AxisSpec


def _reference():
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
        "Fe": ElementRef("Fe", 6.400, 55.845, 26, ("FeO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "i", basis="atom_counts"),
    )
    return MineralogyReference(
        name="wire_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}), family_display={"olivine": "Ol"})


def _means_and_axis(ne=300):   # energy span 0-5.98 keV: Fe (6.4 keV) is out of range
    e = np.arange(ne) * 0.02
    def peak(c, a):
        return a * np.exp(-((e - c) ** 2) / (2 * 0.05**2))
    m0 = 5 + peak(1.254, 300) + peak(1.740, 150)         # Mg + Si
    m1 = 5 + peak(3.690, 250) + peak(1.740, 300)         # Ca + Si
    means = ClusterMeanSpectra(
        means=np.vstack([m0, m1]), pixel_counts=np.array([100, 80]),
        cluster_ids=np.array([0, 1]), n_clusters=2)
    axis = AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2)
    return means, axis


# --- reference helpers --------------------------------------------------------

def test_cations_in_range_excludes_structural_and_out_of_range():
    ref = _reference()
    cations = ref.cations_in_range(0.1, 5.0)
    assert cations == ("Mg", "Si", "Ca")     # O structural; Fe (6.4 keV) out of range
    assert "O" not in cations


def test_line_energies_and_element_refs():
    ref = _reference()
    assert ref.line_energies(("Mg", "Si")) == {"Mg": 1.254, "Si": 1.740}
    refs = ref.element_refs(("Mg", "Si"))
    assert [r.symbol for r in refs] == ["Mg", "Si"]


# --- reference-aware measure_peaks -------------------------------------------

def test_measure_peaks_derives_lines_from_reference():
    ref = _reference()
    means, axis = _means_and_axis()
    peaks = measure_peaks(means, axis, ref)          # no hand-built line map
    assert len(peaks) == 2
    labels = {m.label for m in peaks[0].measurements}
    assert labels == {"Mg", "Si", "Ca"}             # O excluded, Fe out of range
    # the Mg+Si cluster has positive net for Mg and Si
    net = peaks[0].net_by_label()
    assert net["Mg"] > 0 and net["Si"] > 0


def test_measure_peaks_without_reference_or_lines_raises():
    from axiomm.analysis.errors import PayloadValidationError
    means, axis = _means_and_axis()
    with pytest.raises(PayloadValidationError, match="reference"):
        measure_peaks(means, axis)


def test_top_level_measure_peaks_is_reference_aware():
    import axiomm
    assert axiomm.measure_peaks is measure_peaks


# --- compose without hand-building ElementRef lists ---------------------------

def test_pipeline_honours_structural_exclude_for_cations():
    """The DRY-adopt makes the pipeline use structural_exclude (not a hardcoded
    != 'O'), so an in-range structural element is not treated as a measured cation."""
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    from axiomm.io.converters.models import AxiommSignalPayload
    from axiomm.pipeline import Pipeline

    # Ca is marked structural here, even though its line (3.69 keV) is in range.
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "i", basis="atom_counts"),
    )
    ref = MineralogyReference(
        name="struct_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O", "Ca"}), family_display={"olivine": "Ol"})

    rng = np.random.default_rng(0)
    ne, ny, nx = 300, 10, 12
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)
    cube[: ny // 2] += 400 * np.exp(-((e - 1.254) ** 2) / (2 * 0.05**2))
    cube[ny // 2:] += 400 * np.exp(-((e - 3.690) ** 2) / (2 * 0.05**2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    payload = AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")

    r = Pipeline(groups=2, components=4, reference=ref,
                 beam_energy_kev=15.0, reference_element="Si").run(payload)
    assert r.quantification is not None
    for q in r.quantification:
        assert "Ca" not in q.net_intensities   # structural -> not a measured cation


def test_quantify_wiring_from_reference_no_manual_elementrefs():
    pytest.importorskip("xraylib")
    from axiomm.analysis.quant import compute_k_factors, quantify_cluster_means
    ref = _reference()
    means, axis = _means_and_axis()
    peaks = measure_peaks(means, axis, ref)
    cations = ref.cations_in_range(float(axis.offset),
                                   float(axis.offset) + float(axis.scale) * (int(axis.size) - 1))
    # k-factors + quant element list come straight from the reference
    k = compute_k_factors(ref.element_refs(cations), excitation_kev=15.0, reference="Si")
    quant = quantify_cluster_means(list(peaks), k,
                                   ref.element_refs(cations) + ref.element_refs(("O",)),
                                   reference_name=ref.name)
    assert len(quant) == 2
    assert "Si" in quant[0].wt_percent_element
