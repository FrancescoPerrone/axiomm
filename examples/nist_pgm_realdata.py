"""Real-data exploratory demonstration — NIST PGM SEM/EDS hyperspectral set.

OPT-IN and network-dependent. This script:

  1. downloads the NIST archive into a local cache and VERIFIES it against the
     official SHA-256 (refusing corrupted/mismatched data), then
  2. INSPECTS the verified archive and reports its actual structure.

It deliberately stops there. AXIOMM does not guess file format, array ordering,
detector organisation, or energy-axis calibration: the reader and the pipeline
run are implemented only AFTER inspection has established those facts against
the real files (see examples/REALDATA.md). This is real-data *pipeline testing*
scaffolding, NOT standards-based quantitative validation.

Usage:
    python examples/nist_pgm_realdata.py [CACHE_DIR]

If there is no network route to data.nist.gov the script prints a clear message
and exits non-zero without inventing any data.
"""

from __future__ import annotations

import sys
import tarfile
import urllib.error
from pathlib import Path

from axiomm.io.datasets import nist_pgm


def inspect_archive(path: Path, *, max_members: int = 40) -> None:
    """Report the archive's real contents (facts only — no interpretation)."""
    print(f"\nInspecting {path.name} ({path.stat().st_size / 1e6:.1f} MB)")
    with tarfile.open(path, "r:gz") as tar:
        members = tar.getmembers()
    print(f"  {len(members)} member(s):")
    for m in members[:max_members]:
        kind = "d" if m.isdir() else "f"
        print(f"    [{kind}] {m.name}  ({m.size} bytes)")
    if len(members) > max_members:
        print(f"    ... and {len(members) - max_members} more")
    print("\nInspection complete. Reader + pipeline are pending format "
          "confirmation from these contents — see examples/REALDATA.md.")


def main(argv: list[str]) -> int:
    cache = Path(argv[1]) if len(argv) > 1 else Path.home() / ".cache" / "axiomm" / "nist_pgm"
    print(f"NIST PGM dataset — DOI {nist_pgm.DATASET['doi']}")
    print(f"Cache dir: {cache}")
    try:
        path = nist_pgm.download_and_verify(cache)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"\nERROR: could not retrieve the NIST archive: {exc}\n"
              "This demonstration requires a network route to data.nist.gov.",
              file=sys.stderr)
        return 2
    except nist_pgm.DatasetIntegrityError as exc:
        print(f"\nERROR: checksum verification failed: {exc}", file=sys.stderr)
        return 3
    print("Archive verified against the official SHA-256.")
    inspect_archive(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
