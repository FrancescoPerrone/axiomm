# AXIOMM real-data exploratory demonstration (NIST PGM)

> **Status: scaffolding delivered; data-dependent steps are blocked in the
> current build environment (no network route to `data.nist.gov`).** The
> download/verify/cache utility and its offline tests are complete; the reader,
> pipeline run, fixture, and report are pending archive inspection on a
> networked machine (AXIOMM does **not** guess file format or calibration).

## Dataset

- **Title:** SEM/EDS hyperspectral data set from platinum group mineral ore embedded in epoxy
- **DOI:** https://doi.org/10.18434/mds2-2471
- **Archive:** https://data.nist.gov/od/ds/mds2-2471/PGM.tar.gz
- **Checksum:** https://data.nist.gov/od/ds/mds2-2471/PGM.tar.gz.sha256
- **Catalog:** https://catalog.data.gov/dataset/sem-eds-hyperspectral-data-set-from-platinum-group-mineral-ore-embedded-in-epoxy
- **Licence:** https://www.nist.gov/open/license (NIST open data)

## Published metadata — TO BE VERIFIED, not assumed

The NIST catalog describes a 512×512 SEM/EDS acquisition, 10 eV/channel with a
0 eV offset, 20 keV beam energy, 1 nA probe current, ~1.3 h across four
detectors. **These are recorded here only as published claims.** Per the task,
the adapter must verify every value against the downloaded files and archive
contents and must not hard-code unverified assumptions. Nothing in the code
depends on these numbers yet.

## Reproducible workflow

```bash
pip install -e ".[all,quant,viz]"

# 1. download + verify (refuses corrupted/mismatched data; caches; records
#    URL, checksum, UTC date, licence, DOI in a sidecar manifest)
python examples/nist_pgm_realdata.py                 # or: ... <CACHE_DIR>

# opt-in download test (deselected by default; skips cleanly without network):
pytest -m realdata tests/io/datasets
```

The downloader lives in `axiomm.io.datasets.nist_pgm`
(`download_and_verify`, `fetch_official_sha256`, `sha256_of`) and is unit-tested
offline in `tests/io/datasets/test_nist_pgm_downloader.py` (hashing, cache
reuse, refusal to silently replace a mismatched archive, checksum parsing).

## What is delivered vs. blocked

**Delivered now (offline-testable):**
- reproducible, checksum-verifying downloader + cache with retrieval provenance;
- an inspection entry point that lists the *actual* archive contents (facts
  only) once the archive is available;
- offline unit tests of the integrity/cache contract;
- an opt-in `realdata` test that performs the real download when a network route
  exists and skips with a clear message otherwise.

**Blocked in this environment (no route to `data.nist.gov`):**
- archive inspection (format, array ordering, navigation/signal dims, detector
  organisation, energy-axis calibration, live/dead-time semantics);
- the format-specific reader (RosettaSciIO/HyperSpy or a small validated
  adapter) — **not implemented, because implementing it without inspecting the
  real files would be guessing, which is explicitly disallowed**;
- the end-to-end pipeline run, the network-independent fixture derived from a
  real subset, and the real-data report.

## What a completed run will and will NOT establish

- **Will:** that the AXIOMM pipeline ingests and processes a real measured
  SEM/EDS hyperspectral map deterministically; where the observed chemistry
  falls outside the current reference library, that it abstains with an explicit
  diagnostic rather than forcing a mineral identification.
- **Will NOT:** standards-based quantitative accuracy, or validated
  mineral-identification performance. This dataset is **not** assumed to carry
  authoritative pixel-level phase ground truth; absent such ground truth, no
  classification accuracy/precision/recall will be reported, and agreement with
  AXIOMM's own references is **not** independent validation. Results are
  observational and exploratory. Platinum-group phases are largely outside the
  current silicate/oxide reference coverage, so abstention is an expected and
  valid outcome.
