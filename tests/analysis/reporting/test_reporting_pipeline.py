"""S4b — overview + phase_map sections rendered from a real PipelineResult.

Exercises both entry points (`result.report_html(...)` shortcut and
`result.report(backend=...).write(...)`), the applies()-gating for a
clusters-only run, and the embedded (never linked) phase-map figure.
"""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.reporting.models import Report
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def _payload(seed=0, counts=400.0, ny=12, nx=16, ne=400):
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
        name="rep_test_ref", version="1", elements=els, minerals=minerals,
        structural_exclude=frozenset({"O"}),
        family_display={"olivine": "Ol", "pyroxenoid": "Ca-sil"})


def _full_result():
    pytest.importorskip("sklearn")
    pytest.importorskip("xraylib")
    return Pipeline(groups=2, components=4, reference=_reference(),
                    beam_energy_kev=15.0, seed=0).run(_payload())


# --- both entry points --------------------------------------------------------

def test_report_html_shortcut_returns_report():
    r = _full_result()
    rep = r.report_html()
    assert isinstance(rep, Report) and rep.mime == "text/html"
    assert "Overview" in rep.content and "Phase map" in rep.content


def test_report_backend_write_path(tmp_path):
    r = _full_result()
    out = tmp_path / "run.html"
    r.report(backend="html").write(out)
    assert out.exists() and "<!doctype html>" in out.read_text().lower()


def test_report_html_writes_and_guards_overwrite(tmp_path):
    r = _full_result()
    out = tmp_path / "run.html"
    r.report_html(out)
    assert out.exists()
    with pytest.raises(OutputExistsError):
        r.report_html(out)
    r.report_html(out, overwrite=True)


# --- content ------------------------------------------------------------------

def test_overview_lists_clusters_and_phase_map_has_table():
    r = _full_result()
    html = r.report_html().content
    # cluster rows + phase modal table
    assert "best match" in html and "area %" in html
    names = set(np.unique(r.phase_map))
    assert any(n in html for n in names)


def test_phase_map_figure_is_embedded_not_linked():
    pytest.importorskip("matplotlib")
    r = _full_result()
    html = r.report_html().content
    assert "data:image/png;base64," in html
    assert "http://" not in html and "https://" not in html


# --- applies()-gating for a clusters-only run ---------------------------------

def test_clusters_only_omits_phase_map_keeps_overview():
    pytest.importorskip("sklearn")
    r = Pipeline(groups=2, components=4).run(_payload())  # no beam energy -> no minerals
    assert r.phase_map is None
    html = r.report_html().content
    assert "Overview" in html
    assert "Phase map" not in html
