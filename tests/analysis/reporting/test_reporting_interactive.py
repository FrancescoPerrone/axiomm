"""S4-interactive — the html backend's drag/edit layer (structural checks).

The behaviour is client-side JS, verified on-device; here we assert the backend
emits the hooks (draggable modules, editable text, the persistence script) when
interactive, omits them when not, and stays self-contained (no external assets).
"""

from __future__ import annotations

from axiomm.analysis.reporting import ReportConfig, ReportSection, Table, render_report, sections


class _Result:
    pass


def _register(sid, title, blocks):
    class _S:
        id = sid

        def applies(self, result):
            return True

        def render(self, result, config):
            return ReportSection(sid, title, blocks)

    sections.register(sid, lambda: _S())


def _render(**cfg):
    _register("alpha", "Alpha", ["intro text", Table(["a"], [[1]], "t")])
    _register("beta", "Beta", ["more text"])
    try:
        return render_report(_Result(), config=ReportConfig(
            sections=("alpha", "beta"), title="My Report", **cfg)).content
    finally:
        sections.unregister("alpha")
        sections.unregister("beta")


def test_interactive_emits_modules_editables_and_script():
    html = _render(subtitle="a lede", eyebrow="AXIOMM")
    assert 'class="report-grid"' in html and 'id="report-grid"' in html
    # sections are canvas items, and the masthead is a canvas item too
    assert html.count('class="module canvas-item"') == 2
    assert 'data-module="alpha"' in html and 'data-module="beta"' in html
    assert 'class="masthead canvas-item" data-module="__masthead__"' in html
    assert 'class="module-handle"' in html
    # editable page + section + paragraph hooks
    for eid in ('page-title', 'page-lede', 'page-eyebrow', 'alpha-title', 'alpha-p1', 'beta-p1'):
        assert f'data-editable="{eid}"' in html, eid
    assert "<script>" in html and "pointerdown" in html
    # full-viewport free-canvas model + per-card hide (close) affordance
    assert "module-resize" in html and "module-hide" in html
    assert "canvas-mode" in html and "applyCanvas" in html
    assert "m.hidden = true" in html   # click-to-hide for the session


def test_interactive_emits_panel_inspect_and_export_affordances():
    """Per-panel features added on top of the canvas: content zooms on resize,
    figures open in a lightbox with a PNG download, and tables export (copy/CSV)."""
    html = _render(subtitle="s")
    # content wrapper + resize zooms it (figures AND text grow with the panel)
    assert "module-body" in html and "style.zoom" in html
    # figure lightbox with a PNG download
    assert "axm-lightbox" in html and "axm-lb-dl" in html and ".png" in html
    # table export: copy as TSV + download CSV
    assert "axm-tbl-tools" in html and "text/csv" in html
    assert "clipboard" in html and "\\t" in html   # TSV for paste into Sheets/Word/PPT


def test_panel_affordances_absent_in_static_mode():
    html = _render(interactive=False)
    assert "axm-lightbox" not in html and "axm-tbl-tools" not in html


def test_static_mode_has_no_interactivity():
    html = _render(interactive=False)
    assert "data-editable" not in html
    assert "module-handle" not in html
    assert "<script>" not in html
    assert 'data-module="alpha"' in html   # modules still identifiable, just not draggable


def test_interactive_report_is_self_contained():
    html = _render(subtitle="s")
    assert "http://" not in html and "https://" not in html
    assert "cdn" not in html.lower()


def test_theme_tokens_defined_for_all_three_states():
    html = _render()
    assert ":root {" in html
    assert '@media (prefers-color-scheme:dark)' in html
    assert ':root[data-theme="dark"]' in html
