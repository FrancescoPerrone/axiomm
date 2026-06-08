# Converter user guide

The **converter** is AXIOMM's tool for turning instrument-specific data
files into analysis-ready signal objects. It lives at
`axiomm.io.converters` and is the first tool delivered as part of
AXIOMM.

This page is a task-oriented user guide. For the architectural
breakdown, see the **Architecture** section of the
[wiki](https://github.com/FrancescoPerrone/axiomm/wiki/Converter-Architecture).
For the authoritative specification, see
[`docs/specs/converter_tool_spec.md`](https://github.com/FrancescoPerrone/axiomm/blob/main/docs/specs/converter_tool_spec.md)
in the repository.

```{contents}
:local:
:depth: 2
```

## Quick start — one-call conversion

The shortest path from an XRM-style HDF5 file to a HyperSpy `.hspy`:

```python
from axiomm.io.converters import convert_file

result = convert_file(
    input_path="A21_054_map.h5",
    output_path="A21_054_map.hspy",
    reader="xrmmap_h5",
)

print(result.output_path)      # PosixPath('A21_054_map.hspy')
print(result.reader_name)      # 'xrmmap_h5'
print(result.writer_name)      # 'hspy'
for d in result.diagnostics:
    print(f"[{d.severity}] {d.code}: {d.message}")
```

The output file is a standard HyperSpy `.hspy`:

```python
import hyperspy.api as hs

signal = hs.load("A21_054_map.hspy")
print(signal)                                          # <Signal1D, …>
print(signal.metadata.AXIOMM.converter.reader)         # 'xrmmap_h5'
print(signal.metadata.AXIOMM.source.path)              # original .h5 path
print(signal.metadata.General.title)                   # 'A21_054_map'
print(signal.axes_manager)                             # x, y in µm; Energy in keV
```

The `AXIOMM` namespace is nested per spec §15 — see the
[AXIOMM metadata layout](#axiomm-metadata-layout) section below for
the full structure.

## How AXIOMM decides what to read and where to write

### Reader resolution

The `reader` argument controls which `Reader` handles the input. The
options, in order of explicitness:

| Value                          | Behaviour                                                                 |
|--------------------------------|---------------------------------------------------------------------------|
| `Reader` instance              | Used as-is (advanced; lets you configure the reader before passing it in). |
| Registered name, e.g. `"xrmmap_h5"` | Looked up in a small built-in mapping; instantiated with defaults.    |
| `"auto"` *(default)*           | Iterates registered readers; picks the one whose `can_read(path)` is `True`. Raises `ReaderDetectionError` if none or more than one accept. |

Today only `XRMMapH5Reader` is registered, so `"auto"` resolves to it
for XRM files. As more readers are added, `"auto"` will dispatch
between them; if it can't decide, it fails *explicitly* — never silently
guesses.

### Output-path resolution

The output destination follows this precedence (spec §11.2):

1. Explicit `output_path=...` wins.
2. Otherwise `output_dir / (input_path.stem + writer_extension)`.
3. Otherwise `input_path.with_suffix(".hspy")` — alongside the input.

```python
convert_file("a.h5", output_path="out/here.hspy")  # → out/here.hspy
convert_file("a.h5", output_dir="out/")            # → out/a.hspy
convert_file("a.h5")                                # → ./a.hspy
```

### Overwrite vs skip-existing

AXIOMM never silently replaces existing outputs (spec §9.7). When the
target file already exists:

| Flags                                | Behaviour                                                                |
|--------------------------------------|--------------------------------------------------------------------------|
| *(neither)*                          | Raises `OutputExistsError`. The message names the path and how to override. |
| `overwrite=True`                     | Replaces the existing file.                                              |
| `skip_existing=True`                 | Short-circuits **before** reading; returns a result pointing at the existing file with an `output_skipped_existing` diagnostic. Useful for resuming batch runs. |

If both are set, `skip_existing` wins (no work is done).

## Handling XRM files with non-default HDF5 paths

XRM-style files produced by different acquisition-software versions
sometimes store the same information at different HDF5 paths. Rather
than subclass the reader, pass a configured `XRMMapH5Reader`:

```python
from axiomm.io.converters import XRMMapH5Config, XRMMapH5Reader, convert_file

reader = XRMMapH5Reader(config=XRMMapH5Config(
    counts_path="/some/other/path/counts",
    environ_name_path="/some/other/config/name",
    # ...override only the fields you need; defaults cover the rest.
))

convert_file(
    input_path="alternative.h5",
    output_path="alternative.hspy",
    reader=reader,
)
```

### Picking a ROI variant on real files

Real instrument files store ROI limits as `(n_rois, n_variants, 2)`,
not `(n_rois, 2)`. The reader handles both shapes; on the 3-D shape
it extracts `limits[:, roi_variant_index, :]`. The default
`roi_variant_index = 0` works for the "first variant is canonical"
convention; set it to a different value if your acquisition stores
the trusted variant elsewhere:

```python
reader = XRMMapH5Reader(config=XRMMapH5Config(roi_variant_index=3))
```

An out-of-bounds index emits the `roi_variant_out_of_bounds`
diagnostic with a message naming the available range.

If the configured `counts_path` is missing from the file, the reader
raises `DatasetNotFoundError` with a message that names both the path
it looked at *and* the config field to override — so you don't have to
read the source to know what to change.

Missing **optional** metadata (the environ table, the ROI table, the
beam-size key) is non-fatal: the reader attaches a structured
`Diagnostic` to the payload and continues. This is by design (spec
§7.8): scientific-data safety, but graceful degradation.

## Scientific assumptions still requiring owner confirmation

Three of `XRMMapH5Config`'s defaults are **assumed scientific
constants**, not values derived from the input file. They reproduce
the AXIOMM prototype's behaviour and are exposed as configuration —
but they have not been independently validated against the package
owner's instrument data. Per spec §17 they remain an open question
that must be resolved before public release.

```{list-table}
:header-rows: 1
:widths: 32 18 50

* - Constant
  - Default
  - What needs confirming
* - `energy_scale` (keV per MCA channel)
  - `40.96 / 4096`
  - The detector / MCA gain. Confirm against your instrument's
    energy calibration, or — better — extract it from the source
    file's metadata when available.
* - `roi_limit_scale`
  - `0.01`
  - The scaling applied to the integer ROI limits in
    `/xrmmap/config/rois/limits`. Default assumes centi-keV
    (divide by 100 for keV). Confirm this matches the units your
    XRM software writes.
* - `fallback_field_width_um` (µm)
  - `500.0`
  - The assumed map width when no beam size is available. Used as
    `fallback_field_width_um / xdim` for the navigation scale.
    This is a pure fallback; if your instrument writes a beam size
    into the environ table you should rely on that (the converter
    already does) and this fallback never applies.
```

Each of these is a field on `XRMMapH5Config`, so a user with the
correct value can pass a configured reader without subclassing:

```python
from axiomm.io.converters import XRMMapH5Config, XRMMapH5Reader, convert_file

reader = XRMMapH5Reader(config=XRMMapH5Config(
    energy_scale=...,     # your confirmed gain
    roi_limit_scale=...,
    fallback_field_width_um=...,
))
convert_file("input.h5", output_path="out.hspy", reader=reader)
```

The manifest sidecar records the `config_used`, so any conversion
done with non-default values is auditable after the fact.

## AXIOMM metadata layout

Both `signal.metadata.AXIOMM` (in-memory after build) and the
``axiomm_metadata`` subkey of the manifest sidecar share the same
nested structure, defined by spec §15:

```text
AXIOMM
├── converter
│   ├── reader            "xrmmap_h5"
│   ├── reader_version    "0.1.0.dev0"
│   └── config            { full XRMMapH5Config dataclass dump }
├── axes
│   └── [ {name, role, size, units, scale, offset, index_in_array}, ... ]
├── source
│   ├── path              "/path/to/input.h5"
│   ├── reader            "xrmmap_h5"
│   ├── reader_version    "0.1.0.dev0"
│   └── input_hash        null
├── provenance_classification
│   ├── observed          [ ... ]
│   ├── inferred          [ ... ]
│   └── assumed           [ ... ]
└── diagnostics
    └── [ {severity, code, message, context}, ... ]
```

Every section is built by a composable transformer in
`axiomm.io.converters.metadata`; the same transformers are used by
the HyperSpy builder and the manifest writer so the two cannot drift.

## Reproducibility: the manifest sidecar

Every successful `convert_file` call writes a JSON manifest at
`<output>.axiomm.json` next to the `.hspy` file. The manifest captures
everything needed to reproduce or audit the conversion.

### Schema (v2)

```{list-table}
:header-rows: 1
:widths: 28 72

* - Field
  - Description
* - `manifest_schema_version`
  - Schema version string. Currently `"2"`. Future non-additive
    changes bump this so consumers can gate on the version they see.
* - `axiomm_version`
  - The AXIOMM package version that produced the conversion.
* - `created_at`
  - ISO 8601 timestamp in UTC, timezone-aware.
* - `input_path`, `output_path`
  - The resolved source and target paths.
* - `reader_name`, `writer_name`
  - Identifiers of the components actually used (e.g. `"xrmmap_h5"`,
    `"hspy"`).
* - `source_shape`
  - The input dataset's shape as a list of ints, or `null` if the
    reader's data exposes no `.shape`.
* - `axiomm_metadata`
  - Nested AXIOMM namespace with `converter`, `axes`, `source`,
    `provenance_classification`, `diagnostics` subkeys — mirrors
    ``signal.metadata.AXIOMM`` exactly. See
    [AXIOMM metadata layout](#axiomm-metadata-layout) above for the
    full structure.
```

```{note}
Schema v2 (Chunk 10) groups the AXIOMM-specific fields under
``axiomm_metadata`` so they mirror ``signal.metadata.AXIOMM``. In v1
they sat flat at the manifest root (``axes_summary``,
``config_used``, ``diagnostics``, ``provenance_classification``).
v2 manifests are not backwards-compatible with v1 consumers; check
``manifest_schema_version`` if your code reads both.
```

### Provenance classification (spec §15)

The classification distinguishes:

- **observed** — metadata read directly from the source file (counts
  dataset, environ keys, ROI entries when present, navigation scale
  when computed from a beam-size value found in the environ table).
- **inferred** — values derived from observed values (e.g. axis sizes
  from `data.shape`).
- **assumed** — fallback or config-default values with *no source* in
  the input file (the Energy axis scale `40.96 / 4096`, the navigation
  axis units, the navigation scale when it falls back to
  `fallback_field_width_um / xdim`, the ROI limit rescaling).

This separation is what makes an AXIOMM conversion auditable: a
downstream consumer can tell what came from the instrument vs. what
came from the converter's defaults.

### Reading a manifest

```python
import json
from axiomm.io.converters import convert_file

result = convert_file("A21_054_map.h5", output_path="A21_054_map.hspy")

with result.manifest_path.open() as f:
    manifest = json.load(f)

print(manifest["axiomm_version"])
print(manifest["reader_name"], "→", manifest["writer_name"])

# AXIOMM-specific content lives under "axiomm_metadata" in v2.
classification = manifest["axiomm_metadata"]["provenance_classification"]
for bucket, entries in classification.items():
    print(f"[{bucket}] ({len(entries)})")
    for e in entries:
        print(f"  - {e}")
```

### Opting out

Pass `manifest=False` to `convert_file` if you don't want a sidecar.
`ConversionResult.manifest_path` will be `None` and no JSON file is
written. The sidecar is also skipped when `skip_existing=True`
short-circuits — skip means no work, no manifest update.

## Lower-level: reader + builder without the writer

If you want the HyperSpy signal in memory without writing to disk:

```python
from axiomm.io.converters import XRMMapH5Reader, build_hyperspy_signal

payload = XRMMapH5Reader().read("example.h5")
signal = build_hyperspy_signal(payload)
# ... downstream analysis ...
```

The intermediate `AxiommSignalPayload` is a neutral in-memory
representation of the signal — data array, axis specs, metadata,
provenance, diagnostics. It is deliberately backend-agnostic so future
non-HyperSpy builders (xarray, RosettaSciIO dicts, plain NumPy) can be
added without churning the readers.

## Diagnostics — read your `ConversionResult`

Every conversion returns a `ConversionResult` whose `diagnostics` field
is a tuple of structured `Diagnostic` records. They surface decisions
the converter made on your behalf:

| Code                              | Severity | What it means                                                                                  |
|-----------------------------------|----------|------------------------------------------------------------------------------------------------|
| `lazy_downgraded_to_eager`        | info     | You passed `lazy=True` (the default); the MVP reader materialised the dataset eagerly.         |
| `output_skipped_existing`         | info     | `skip_existing=True` matched; no read/build/write was performed.                                |
| `environ_missing`                 | warning  | The XRM environ config table wasn't found; fell back to `fallback_field_width_um`.             |
| `beam_size_missing`               | warning  | The configured beam-size key wasn't in the environ table; fell back.                           |
| `beam_size_unparseable`           | warning  | The beam-size string couldn't be parsed; fell back.                                            |
| `roi_missing`                     | warning  | ROI metadata datasets weren't present; ROIs not extracted.                                     |
| `roi_limits_unexpected_shape`     | warning  | ROI limits had a shape we don't know how to slice (not `(n, 2)` and not `(n, k, 2)`); ROIs not extracted. |
| `roi_variant_out_of_bounds`       | warning  | The file has `(n_rois, n_variants, 2)` ROI limits but the configured `roi_variant_index` is out of range. |
| `roi_unreadable`                  | warning  | ROI metadata datasets couldn't be decoded; ROIs not extracted.                                 |
| `environ_unreadable`              | warning  | Environ datasets couldn't be decoded.                                                          |
| `environ_length_mismatch`         | warning  | The environ `name` and `value` arrays had different lengths; truncated to the shorter.         |
| `navigation_scale_unknown`        | warning  | No beam size *and* no fallback configured; navigation scale defaulted to 1.0.                  |

Pattern-match `d.code` rather than `d.message` if you build automation
on top — codes are stable, messages may be reworded.

## See also

- {doc}`Known issues <known_issues>` — the user-facing traps AXIOMM
  either guards against or wants you to be aware of (including the
  prototype's silent x/y swap on `.hspy` outputs).
- [Specification](https://github.com/FrancescoPerrone/axiomm/blob/main/docs/specs/converter_tool_spec.md)
  — the authoritative design document for the converter.
- [Wiki](https://github.com/FrancescoPerrone/axiomm/wiki/Converter) — the
  high-level landing page for the converter inside the broader AXIOMM
  docs.
- [Python API reference](../api/index) — auto-generated from the package
  source.
