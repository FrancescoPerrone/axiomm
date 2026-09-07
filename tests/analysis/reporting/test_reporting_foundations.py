"""S4a — reporting foundations: format-agnostic sections + pluggable backends.

No stage science yet: this proves the assembler, the section/backend registries,
the self-contained HTML skeleton, safe writing, and that importing the subsystem
never pulls in matplotlib.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from axiomm.analysis.errors import BackendNotFoundError, OutputExistsError
from axiomm.analysis.reporting import (
    Figure,
    Report,
    ReportConfig,
    ReportSection,
    Table,
    render_report,
    reporters,
    sections,
)


class _DummyResult:
    """Stand-in for a PipelineResult / stage payload."""


def _register_section(sid, *, applies=True, blocks=None):
    class _S:
        id = sid

        def applies(self, result):
            return applies

        def render(self, result, config):
            return ReportSection(id=sid, title=sid.title(), blocks=blocks or [f"body of {sid}"])

    sections.register(sid, lambda: _S())


# --- import stays matplotlib-free ---------------------------------------------

def test_import_does_not_pull_matplotlib():
    code = ("import axiomm.analysis.reporting, sys; "
            "print('matplotlib' not in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.strip() == "True", out.stdout + out.stderr


# --- the HTML skeleton --------------------------------------------------------

def test_empty_report_is_valid_self_contained_html():
    r = render_report(_DummyResult(), backend="html", config=ReportConfig(title="My Run"))
    assert isinstance(r, Report)
    assert r.mime == "text/html"
    assert "<!doctype html>" in r.content.lower()
    assert "My Run" in r.content
    assert "http://" not in r.content and "https://" not in r.content  # no external assets
    assert "<style" in r.content  # inline CSS


def test_sections_render_in_order_and_applies_filters():
    for sid in ("alpha", "beta", "gamma"):
        _register_section(sid, applies=(sid != "beta"))
    try:
        r = render_report(_DummyResult(), backend="html",
                          config=ReportConfig(sections=("gamma", "alpha", "beta")))
        body = r.content
        assert "Gamma" in body and "Alpha" in body
        assert "Beta" not in body  # applies() == False -> omitted
        assert body.index("Gamma") < body.index("Alpha")  # explicit order honored
        assert [s.id for s in r.sections] == ["gamma", "alpha"]
    finally:
        for sid in ("alpha", "beta", "gamma"):
            sections.unregister(sid)


def test_include_and_exclude():
    for sid in ("one", "two"):
        _register_section(sid)
    try:
        inc = render_report(_DummyResult(), config=ReportConfig(include=("one",)))
        assert [s.id for s in inc.sections] == ["one"]
        exc = render_report(_DummyResult(), config=ReportConfig(exclude=("one",)))
        assert "two" in [s.id for s in exc.sections] and "one" not in [s.id for s in exc.sections]
    finally:
        for sid in ("one", "two"):
            sections.unregister(sid)


# --- blocks render to HTML ----------------------------------------------------

def test_table_and_figure_blocks_render():
    _register_section("mix", blocks=[
        "a paragraph with <unsafe> chars",
        Table(headers=["el", "wt%"], rows=[["Si", 21.3], ["Mg", 12.0]], caption="composition"),
        Figure(data=b"\x89PNG\r\n\x1a\n fake", alt="a plot", caption="fig 1"),
    ])
    try:
        body = render_report(_DummyResult()).content
        assert "&lt;unsafe&gt;" in body            # text is escaped
        assert "<table" in body and "wt%" in body and "composition" in body
        assert "data:image/png;base64," in body     # figure embedded, not linked
        assert 'alt="a plot"' in body
    finally:
        sections.unregister("mix")


# --- backend is pluggable -----------------------------------------------------

def test_reporter_backend_is_pluggable():
    class _MdReporter:
        name = "md"

        def assemble(self, rendered, config):
            lines = [f"# {config.title}"] + [f"## {s.title}" for s in rendered]
            return Report(backend="md", content="\n".join(lines), mime="text/markdown",
                          sections=list(rendered))

    reporters.register("md", lambda: _MdReporter())
    _register_section("s1")
    try:
        r = render_report(_DummyResult(), backend="md", config=ReportConfig(title="T"))
        assert r.mime == "text/markdown"
        assert r.content.startswith("# T")
        assert "## S1" in r.content
    finally:
        reporters.unregister("md")
        sections.unregister("s1")


def test_unknown_backend_raises():
    with pytest.raises(BackendNotFoundError):
        render_report(_DummyResult(), backend="nope")


# --- safe writing -------------------------------------------------------------

def test_write_refuses_silent_overwrite(tmp_path):
    r = render_report(_DummyResult(), config=ReportConfig(title="X"))
    path = tmp_path / "report.html"
    written = r.write(path)
    assert written == path and path.read_text().find("X") >= 0
    with pytest.raises(OutputExistsError):
        r.write(path)
    r.write(path, overwrite=True)  # explicit opt-in works


def test_report_carries_provenance():
    r = render_report(_DummyResult(), backend="html")
    assert r.provenance is not None
    assert r.provenance.tool == "axiomm.analysis.reporting"
    assert r.provenance.backend == "html"
