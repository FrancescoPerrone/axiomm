"""S4d — spectra + peak-ID, and the quant / reliability / minerals sections."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.reporting.svg import spectrum_svg
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def _payload(seed=0, counts=400.0, ny=16, nx=20, ne=400):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 2.0)

    def add(sl, lines):
        for cen, amp in lines:
            cube[sl] += amp * counts * np.exp(-((e - cen) ** 2) / (2 * 0.05**2))

    add((slice(None, ny // 2),), [(1.254, 300), (1.740, 150)])
    add((slice(ny // 2, None),), [(3.690, 250), (1.740, 300)])
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


def _reference():
    els = {
        "O": ElementRef("O", 0.525, 15.999, 8, None, "Ka"),
        "Mg": ElementRef("Mg", 1.254, 24.305, 12, ("MgO", 1, 1), "Ka"),
        "Si": ElementRef("Si", 1.740, 28.085, 14, ("SiO2", 1, 2), "Ka"),
        "Ca": ElementRef("Ca", 3.690, 40.078, 20, ("CaO", 1, 1), "Ka"),
    }
    minerals = (
        MineralEndmember("Forsterite", "olivine", {"Mg": 2, "Si": 1, "O": 4}, None, "i", basis="atom_counts"),
        MineralEndmember("Wollastonite", "pyroxenoid", {"Ca": 1, "Si": 1, "O": 3}, None, "i", basis="atom_counts"),
    )
    return MineralogyReference(
        name="rep_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}), family_display={"olivine": "Ol", "pyroxenoid": "Ca-sil"})


def _full():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    return Pipeline(groups=2, components=6, reference=_reference(),
                    beam_energy_kev=15.0, seed=0).run(_payload())


# --- the spectrum SVG renderer (no matplotlib needed) -------------------------

def test_spectrum_svg_is_self_contained_and_theme_aware():
    e = np.linspace(0, 8, 400)
    y = 50 + 500 * np.exp(-((e - 1.74) ** 2) / (2 * 0.03**2))
    svg = spectrum_svg(e, y, peaks=[{"label": "Si Ka", "center_kev": 1.74,
                                     "window_kev": 0.2, "background": 50.0}])
    assert svg.strip().startswith("<svg") and svg.strip().endswith("</svg>")
    assert "currentColor" in svg          # axes/text adapt to the page ink
    assert "var(--accent" in svg          # data line uses the theme accent (with fallback)
    assert "Si Ka" in svg
    assert "http" not in svg


def test_spectrum_svg_handles_adjacent_peak_labels():
    # two lines close in energy must not spin the label de-collision loop
    e = np.linspace(0, 8, 400)
    y = np.ones_like(e)
    peaks = [{"label": "Mg Ka", "center_kev": 1.25, "window_kev": 0.15, "background": 1.0},
             {"label": "Si Ka", "center_kev": 1.74, "window_kev": 0.15, "background": 1.0}]
    svg = spectrum_svg(e, y, peaks)
    assert "Mg Ka" in svg and "Si Ka" in svg


def test_spectrum_svg_scales():
    e = np.linspace(0, 8, 200)
    y = np.abs(np.sin(e)) * 100 + 1
    for scale in ("linear", "sqrt", "log"):
        assert spectrum_svg(e, y, y_scale=scale).startswith("<svg")


# --- sections in a full run ---------------------------------------------------

def test_report_has_spectra_peaks_quant_reliability_minerals():
    html = _full().report_html().content
    for heading in ("Spectra", "Peaks", "Quantification", "Reliability", "Minerals"):
        assert heading in html, heading
    assert "<svg" in html                      # embedded inline spectra
    assert "wt%" in html                        # quant table
    assert "reportable_estimate" in html or "exploratory_only" in html  # reliability chips


def test_spectra_render_without_matplotlib(monkeypatch):
    # the priority plot must not depend on the viz extra
    import axiomm.analysis.reporting.figures as figures

    def _boom():
        from axiomm.analysis.errors import AnalysisDependencyError
        raise AnalysisDependencyError("no matplotlib")

    monkeypatch.setattr(figures, "import_matplotlib", _boom)
    html = _full().report_html(config=None).content
    assert "Spectra" in html and "<svg" in html   # spectra still there (SVG, not mpl)


def test_clusters_only_still_shows_spectra_without_peaks():
    pytest.importorskip("sklearn")
    r = Pipeline(groups=2, components=6).run(_payload())
    html = r.report_html().content
    assert "Spectra" in html and "<svg" in html
    assert "Quantification" not in html   # no minerals -> quant section absent
