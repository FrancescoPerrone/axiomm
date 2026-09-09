"""S4e — the reports hub: a general, self-contained index across many runs."""

from __future__ import annotations

import pytest

from axiomm.analysis.errors import OutputExistsError
from axiomm.analysis.reporting import HubEntry, build_hub
from axiomm.analysis.reporting.models import Report, Svg


def _entries():
    thumb = Svg('<svg viewBox="0 0 10 10"><rect width="10" height="10" fill="var(--accent)"/></svg>')
    return [
        HubEntry(title="Sample A21-054", href="a21_054.html",
                 summary="Two phases resolved.",
                 metadata={"sample": "A21-054", "date": "2026-09-01", "groups": 2},
                 thumbnail=thumb),
        HubEntry(title="Sample B12-009", href="b12_009.html",
                 metadata={"sample": "B12-009", "instrument": "XRM", "groups": 5}),
        HubEntry(title="Unlinked run"),  # no href, no metadata
    ]


def test_hub_is_self_contained_html_listing_all_runs():
    r = build_hub(_entries(), title="My Reports")
    assert isinstance(r, Report) and r.mime == "text/html"
    assert "<!doctype html>" in r.content.lower()
    assert "My Reports" in r.content
    for t in ("Sample A21-054", "Sample B12-009", "Unlinked run"):
        assert t in r.content
    assert 'href="a21_054.html"' in r.content        # linked run
    assert "http://" not in r.content and "https://" not in r.content
    assert "cdn" not in r.content.lower()


def test_hub_renders_arbitrary_metadata_generically():
    r = build_hub(_entries())
    # keys are not hard-coded to any domain — whatever the user passes shows up
    for token in ("sample", "instrument", "groups", "A21-054", "XRM"):
        assert token in r.content


def test_hub_embeds_thumbnail_not_linked():
    r = build_hub(_entries())
    assert "<svg" in r.content  # thumbnail inlined


def test_empty_hub_is_valid():
    r = build_hub([], title="Nothing yet")
    assert "Nothing yet" in r.content
    assert "no runs" in r.content.lower() or "no reports" in r.content.lower()


def test_hub_write_guards_overwrite(tmp_path):
    r = build_hub(_entries())
    out = tmp_path / "index.html"
    r.write(out)
    assert out.exists()
    with pytest.raises(OutputExistsError):
        r.write(out)


def test_hub_escapes_untrusted_text():
    r = build_hub([HubEntry(title="<script>bad</script>", summary="a & b")])
    assert "<script>bad" not in r.content
    assert "&lt;script&gt;bad" in r.content
