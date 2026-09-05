"""Offline tests for the NIST PGM downloader/cache logic (network-independent).

These verify the integrity/caching contract without any network: hashing,
cache reuse, refusal to reuse or silently replace a mismatched archive, and
checksum-file parsing. The actual NIST download is a separate, opt-in
``@pytest.mark.realdata`` test.
"""

from __future__ import annotations

import hashlib

import pytest

from axiomm.io.datasets import nist_pgm


def _write(path, data: bytes):
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_sha256_of_matches_hashlib(tmp_path):
    p = tmp_path / "blob"
    digest = _write(p, b"platinum group minerals" * 100)
    assert nist_pgm.sha256_of(p) == digest


def test_cached_archive_reused_when_digest_matches(tmp_path):
    dest = tmp_path / nist_pgm.ARCHIVE_NAME
    digest = _write(dest, b"fake archive bytes")
    # matching expected digest -> returned without any network access
    out = nist_pgm.download_and_verify(tmp_path, expected_sha256=digest)
    assert out == dest


def test_cached_archive_is_verified_against_official_checksum_when_not_supplied(
        tmp_path, monkeypatch):
    """A pre-existing archive must not bypass the integrity check."""
    dest = tmp_path / nist_pgm.ARCHIVE_NAME
    _write(dest, b"fake archive bytes")
    monkeypatch.setattr(nist_pgm, "fetch_official_sha256", lambda *a, **k: "0" * 64)

    with pytest.raises(nist_pgm.DatasetIntegrityError, match="mismatch"):
        nist_pgm.download_and_verify(tmp_path)


def test_cached_archive_mismatch_is_never_silently_replaced(tmp_path):
    dest = tmp_path / nist_pgm.ARCHIVE_NAME
    _write(dest, b"fake archive bytes")
    with pytest.raises(nist_pgm.DatasetIntegrityError, match="mismatch"):
        nist_pgm.download_and_verify(tmp_path, expected_sha256="0" * 64)


def test_fetch_official_sha256_parses_sidecar(monkeypatch):
    good = "a" * 64
    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return f"{good}  PGM.tar.gz\n".encode()
    monkeypatch.setattr(nist_pgm.urllib.request, "urlopen", lambda *a, **k: _Resp())
    assert nist_pgm.fetch_official_sha256("https://example/x.sha256") == good


def test_fetch_official_sha256_rejects_garbage(monkeypatch):
    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"not-a-checksum"
    monkeypatch.setattr(nist_pgm.urllib.request, "urlopen", lambda *a, **k: _Resp())
    with pytest.raises(nist_pgm.DatasetIntegrityError):
        nist_pgm.fetch_official_sha256("https://example/x.sha256")


def test_dataset_metadata_is_recorded():
    assert nist_pgm.DATASET["doi"].endswith("mds2-2471")
    assert nist_pgm.DATASET["archive_url"].endswith("PGM.tar.gz")
    assert "nist.gov/open/license" in nist_pgm.DATASET["licence"]


@pytest.mark.realdata
def test_download_real_nist_archive(tmp_path):
    """Opt-in: actually fetch + verify the NIST archive (needs network)."""
    import urllib.error
    try:
        path = nist_pgm.download_and_verify(tmp_path, timeout=120)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        pytest.skip(f"NIST archive not reachable: {exc}")
    assert path.exists()
    assert (tmp_path / f"{nist_pgm.ARCHIVE_NAME}.manifest.json").exists()
