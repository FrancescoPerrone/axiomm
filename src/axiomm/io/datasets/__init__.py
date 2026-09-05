"""Reproducible open-dataset downloaders/caches for real-data demonstrations.

Datasets are fetched into a local cache and verified by checksum; they are
never committed to git. See :mod:`axiomm.io.datasets.nist_pgm`.
"""

from __future__ import annotations

from axiomm.io.datasets.nist_pgm import (
    DATASET as NIST_PGM,
)
from axiomm.io.datasets.nist_pgm import (
    DatasetIntegrityError,
    download_and_verify,
    fetch_official_sha256,
    sha256_of,
)

__all__ = [
    "NIST_PGM",
    "DatasetIntegrityError",
    "download_and_verify",
    "fetch_official_sha256",
    "sha256_of",
]
