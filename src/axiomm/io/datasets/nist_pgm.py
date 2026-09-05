"""Reproducible downloader + cache for the NIST PGM SEM/EDS hyperspectral set.

Dataset: *SEM/EDS hyperspectral data set from platinum group mineral ore
embedded in epoxy* (NIST Public Data Repository).

- DOI:        https://doi.org/10.18434/mds2-2471
- Archive:    https://data.nist.gov/od/ds/mds2-2471/PGM.tar.gz
- Checksum:   https://data.nist.gov/od/ds/mds2-2471/PGM.tar.gz.sha256
- Catalog:    https://catalog.data.gov/dataset/sem-eds-hyperspectral-data-set-from-platinum-group-mineral-ore-embedded-in-epoxy
- Licence:    https://www.nist.gov/open/license (NIST open data)

The archive is large and must **not** be committed to git. This module fetches
it once into a local cache, verifies it against the official SHA-256 *before*
use, refuses corrupted or mismatched data, reuses an already-verified cache,
never silently replaces an existing file with a different digest, and records
retrieval provenance (URL, checksum, UTC date, licence, DOI) in a sidecar.

Network is only touched inside :func:`download_and_verify` /
:func:`fetch_official_sha256`; the hashing, verification and cache-reuse logic
is import-time-clean and unit-testable offline.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import urllib.request
from pathlib import Path

DATASET = {
    "title": "SEM/EDS hyperspectral data set from platinum group mineral ore embedded in epoxy",
    "doi": "https://doi.org/10.18434/mds2-2471",
    "archive_url": "https://data.nist.gov/od/ds/mds2-2471/PGM.tar.gz",
    "sha256_url": "https://data.nist.gov/od/ds/mds2-2471/PGM.tar.gz.sha256",
    "catalog": "https://catalog.data.gov/dataset/"
               "sem-eds-hyperspectral-data-set-from-platinum-group-mineral-ore-embedded-in-epoxy",
    "licence": "https://www.nist.gov/open/license",
}
ARCHIVE_NAME = "PGM.tar.gz"


class DatasetIntegrityError(RuntimeError):
    """Raised when a downloaded/cached archive fails SHA-256 verification."""


def sha256_of(path: str | Path, *, chunk: int = 1 << 20) -> str:
    """Streaming SHA-256 of a file (no full read into memory)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _verify(path: Path, expected: str) -> None:
    actual = sha256_of(path)
    if actual.lower() != expected.lower():
        raise DatasetIntegrityError(
            f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}."
        )


def fetch_official_sha256(url: str = DATASET["sha256_url"], *, timeout: float = 60) -> str:
    """Fetch and parse the official ``*.sha256`` sidecar (``<hash>  <name>``)."""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", "replace").strip()
    token = text.split()[0] if text else ""
    if len(token) != 64:
        raise DatasetIntegrityError(f"unexpected checksum file contents from {url!r}: {text[:80]!r}")
    return token.lower()


def download_and_verify(cache_dir: str | Path, *, url: str = DATASET["archive_url"],
                        expected_sha256: str | None = None,
                        sha256_url: str = DATASET["sha256_url"],
                        force: bool = False, timeout: float = 600) -> Path:
    """Return a verified local copy of the archive, downloading only if needed.

    * A cached archive whose digest matches ``expected_sha256`` is reused
      without any network access.
    * A cached archive whose digest DISAGREES with ``expected_sha256`` is never
      silently replaced: it raises unless ``force=True``.
    * On download, the archive is verified against ``expected_sha256`` (or the
      official ``sha256_url``) before being kept; a mismatch deletes the partial
      file and raises.
    * Retrieval provenance is written to ``<archive>.manifest.json``.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / ARCHIVE_NAME
    expected = expected_sha256 or fetch_official_sha256(sha256_url, timeout=timeout)

    if dest.exists() and not force:
        _verify(dest, expected)
        return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    try:
        _verify(tmp, expected)
    except DatasetIntegrityError:
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(dest)
    (cache_dir / f"{ARCHIVE_NAME}.manifest.json").write_text(json.dumps({
        "title": DATASET["title"], "doi": DATASET["doi"], "url": url,
        "sha256": expected, "retrieved_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "licence": DATASET["licence"], "catalog": DATASET["catalog"],
    }, indent=2))
    return dest


__all__ = ["ARCHIVE_NAME", "DATASET", "DatasetIntegrityError",
           "download_and_verify", "fetch_official_sha256", "sha256_of"]
