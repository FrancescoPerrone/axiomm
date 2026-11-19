"""Raw-data navigator section — applies on a payload, builds a self-contained,
gzip-compressed, lazily-decompressed modal fragment."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from axiomm.analysis.reporting.models import Html, ReportConfig
from axiomm.analysis.reporting.navigator import navigator_markup
from axiomm.analysis.reporting.section_renderers.navigator import NavigatorSection
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec


def _payload(ny=20, nx=24, ne=256, seed=0):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 1.0)
    cube[:, : nx // 2] += 200 * np.exp(-((e - 1.74) ** 2) / (2 * 0.05 ** 2))
    cube[:, nx // 2:] += 200 * np.exp(-((e - 3.69) ** 2) / (2 * 0.05 ** 2))
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float)
    axes = (
        AxisSpec("y", "navigation", ny, index_in_array=0),
        AxisSpec("x", "navigation", nx, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


def test_navigator_applies_only_with_a_3d_payload():
    sec = NavigatorSection()
    assert sec.applies(SimpleNamespace(payload=_payload())) is True
    assert sec.applies(SimpleNamespace(payload=None)) is False
    assert sec.applies(SimpleNamespace()) is False


def test_navigator_section_builds_a_self_contained_modal():
    sec = NavigatorSection()
    section = sec.render(SimpleNamespace(payload=_payload()), ReportConfig())
    assert section.id == "navigator"
    html_blocks = [b for b in section.blocks if isinstance(b, Html)]
    assert len(html_blocks) == 1
    m = html_blocks[0].markup
    # modal + preview + lazy native decompression, no external assets
    assert "axm-nav-modal" in m and "axm-nav-thumb" in m
    assert "DecompressionStream" in m
    assert "backdrop-filter" in m          # blurs the report behind it
    assert "http://" not in m and "https://" not in m   # self-contained


def test_navigator_binning_shrinks_the_embedded_cube():
    # coarser binning -> smaller fragment (fewer embedded voxels)
    p = _payload(ny=40, nx=40, ne=512)
    fine = navigator_markup(p, spatial_bin=1, energy_bin=2)
    coarse = navigator_markup(p, spatial_bin=4, energy_bin=16)
    assert len(coarse) < len(fine)
