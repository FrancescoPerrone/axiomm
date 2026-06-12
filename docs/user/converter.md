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
  - The detector / MCA gain. The default encodes the assumption
    that the full MCA range spans $40.96\ \mathrm{keV}$ over
    $4096$ channels, giving a per-channel energy width of
    $E_\text{scale} = \dfrac{40.96\ \mathrm{keV}}{4096\ \mathrm{channels}} \approx 0.01\ \mathrm{keV/channel}$.
    The channel-$i$ energy is then $E_i = E_\text{scale} \cdot i$
    (offset = 0). Confirm against your instrument's energy
    calibration, or — better — extract it from the source file's
    metadata when available.
* - `roi_limit_scale`
  - `0.01`
  - The scaling applied to the integer ROI limits stored at
    `/xrmmap/config/rois/limits`. With the default the conversion
    is $E_\text{ROI} = 0.01 \cdot n_\text{ROI,int}$, i.e. the
    integers are interpreted as centi-keV (so $640 \to 6.40\ \mathrm{keV}$).
    Confirm this matches the units your XRM software writes; in
    particular, this is independent of `energy_scale` only if the
    file does not store ROI limits as MCA channel indices.
* - `fallback_field_width_um` (µm)
  - `500.0`
  - The assumed total map width in µm when no beam size is in the
    environ table. The navigation pixel scale is then
    $s_\text{nav,fallback} = \dfrac{w_\text{fallback}}{x_\text{dim}}$
    where $w_\text{fallback}$ = `fallback_field_width_um` and
    $x_\text{dim}$ is the size of the first navigation axis. This
    is a pure fallback; if your instrument writes a beam size into
    the environ table the converter uses
    $s_\text{nav} = b_\text{nominal}$ instead, where
    $b_\text{nominal}$ is the parsed
    `Experiment.Beam_Size__Nominal` value.
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

## Calibration provenance primitives (Chunk 15)

Phase 4 of the converter introduces **per-value calibration
provenance**. Chunk 15 lays the *types and plumbing* for it; the
ladder behaviour itself lands in Chunk 16 and the user-facing
precedence rewrite in Chunk 19. **No reader behaviour has changed
yet** — the three constants on the previous section are still
applied exactly as they were before.

What's new are three importable types in
`axiomm.io.converters.calibration` (re-exported at the package
top-level):

* `CalibrationSource` — where a single calibration value came from.
  Five members: `source_metadata`, `user_config`, `legacy_preset`,
  `inferred`, `unknown`. Stored as a `str` subclass so the value
  serialises to its bare token in manifest JSON.
* `ConversionMode` — policy switch on the ladder. Four members:
  `legacy` (current default, allows preset fallback), `generic`
  (safe public default, no silent preset fallback), `strict` (no
  inference allowed), `diagnostic` (dry-run report). The `legacy`
  default stays in force through Chunk 17 and flips to `generic`
  in Chunk 18 — that single flip is the only breaking change
  planned for Phase 4.
* `ResolvedValue(value, source, note=None)` — frozen dataclass
  pairing a value with its provenance.

Readers can attach a per-value provenance dict to the neutral
payload:

```python
from axiomm.io.converters import (
    AxiommSignalPayload, AxisSpec,
    CalibrationSource, ResolvedValue,
)

payload = AxiommSignalPayload(
    data=...,
    axes=(AxisSpec("Energy", "signal", 4096, units="keV",
                   scale=0.01, index_in_array=2),),
    signal_kind="signal1d",
    resolved_calibration={
        "energy_scale": ResolvedValue(
            value=0.01,
            source=CalibrationSource.LEGACY_PRESET,
            note="APS 13-ID-E preset v1",
        ),
    },
)
```

When `resolved_calibration` is populated, the AXIOMM metadata
namespace and the manifest sidecar gain a new `calibration`
subkey alongside the existing `converter` / `axes` / `source` /
`provenance_classification` / `diagnostics` sections. The subkey
is **additive**: when `resolved_calibration` is `None` or empty,
the namespace byte-shape is identical to the pre-Chunk-15
layout — existing snapshots and round-trip tests continue to
pass unchanged.

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
├── diagnostics
│   └── [ {severity, code, message, context}, ... ]
└── calibration                                       (optional, Chunk 15+)
    └── { <name>: {value, source, note}, ... }
```

The `calibration` subkey only appears when the reader populated
`payload.resolved_calibration`. Readers that pre-date Chunk 16
leave it absent, so existing snapshots stay byte-identical.

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

## Reading non-XRM HDF5 files via `GenericHDF5MapReader`

If your file has the same *structure* as an XRM-Map file — a 3-D
counts dataset, an optional environ name/value table, an optional
ROI name/limits table — but lives at different HDF5 paths, you do
not need to write a new `Reader` class. Pass an `HDF5MapSchema` to
`GenericHDF5MapReader`:

```python
from axiomm.io.converters import (
    GenericHDF5MapReader, HDF5MapConfig, HDF5MapSchema, convert_file,
)

schema = HDF5MapSchema(
    counts_path="/scan/data/counts",
    environ_name_path="/scan/metadata/names",
    environ_value_path="/scan/metadata/values",
    beam_size_key="Beam_Size_Um",
    # ROIs absent in this hypothetical file → leave roi_*_path = None
)

reader = GenericHDF5MapReader(
    schema=schema,
    config=HDF5MapConfig(
        energy_scale=0.005,                # keV per channel
        roi_limit_scale=1.0,               # if you had ROIs in keV already
        fallback_field_width_um=None,      # no fallback; nav scale must come from environ
    ),
)

convert_file(
    input_path="scan.h5",
    output_path="scan.hspy",
    reader=reader,
)
```

The schema describes **where** things live; the config describes
**what they mean**. The two are deliberately separate so a single
schema can serve multiple instruments / generations whose
calibration constants differ. The built-in
`XRMMAP_H5_SCHEMA` covers the canonical XRM-Map / Larch layout, so
you can use it as a starting point:

```python
from dataclasses import replace
from axiomm.io.converters import XRMMAP_H5_SCHEMA, HDF5MapSchema

# Same layout as XRM but with a renamed root group.
schema = replace(XRMMAP_H5_SCHEMA,
    counts_path="/xrm_v2/counts",
    environ_name_path="/xrm_v2/config/env/name",
    environ_value_path="/xrm_v2/config/env/value",
)
```

`GenericHDF5MapReader` follows the same conventions as
`XRMMapH5Reader`: counts are required, environ / ROI metadata are
optional with structured diagnostics on absence, ROI limits handle
both `(n_rois, 2)` and `(n_rois, n_variants, 2)` shapes (via
`HDF5MapConfig.roi_variant_index`), and the
`signal.metadata.AXIOMM.converter.config` records both the schema
and the config used for the conversion, making manifests fully
reproducible.

For files whose structure diverges from this layout (multiple
counts datasets per file, non-trailing signal axis, no environ
table at all), write a bespoke `Reader` class instead — see the
next section.

## Extending AXIOMM with custom readers and writers

Third-party packages can add their own readers and writers without
modifying AXIOMM — declare them as Python **entry points** in your
package's `pyproject.toml` and AXIOMM discovers them automatically
on import via :func:`axiomm.io.converters.load_plugins`.

### Entry-point groups

| Group              | What it registers |
|--------------------|-------------------|
| `axiomm.readers`   | A `Reader` plugin |
| `axiomm.writers`   | A `Writer` plugin |

### Writing a reader plugin

Implement the `Reader` protocol — a `name` attribute, a
`supported_extensions` tuple, and `can_read(path)` /
`read(path, *, lazy=True)` methods returning an
`AxiommSignalPayload`:

```python
# my_xrf_package/readers/my_format.py
from axiomm.io.converters.models import AxiommSignalPayload

class MyFormatReader:
    name = "my_format"
    supported_extensions = (".myx",)

    def can_read(self, path) -> bool:
        # Cheap probe — extension + signature peek.
        return str(path).endswith(".myx")

    def read(self, path, *, lazy: bool = True) -> AxiommSignalPayload:
        # Open the file, extract the counts dataset and any metadata,
        # return a populated AxiommSignalPayload.
        ...
```

In your package's `pyproject.toml`:

```toml
[project.entry-points."axiomm.readers"]
my_format = "my_xrf_package.readers.my_format:MyFormatReader"
```

After `pip install`-ing your package alongside AXIOMM:

```python
from axiomm.io.converters import iter_readers, convert_file

[r.name for r in iter_readers()]
# -> ['xrmmap_h5', 'my_format']

convert_file("scan.myx", output_path="scan.hspy", reader="my_format")
# or
convert_file("scan.myx", output_path="scan.hspy", reader="auto")
```

`reader="auto"` walks the registry and picks the (single) plugin
whose `can_read(path)` returns `True`, so your plugin participates
in auto-detection alongside the built-in readers.

### Writing a writer plugin

Same pattern using `axiomm.writers`:

```toml
[project.entry-points."axiomm.writers"]
my_out = "my_xrf_package.writers.my_out:MyFormatWriter"
```

```python
# my_xrf_package/writers/my_out.py
from pathlib import Path
from axiomm.io.converters.errors import OutputExistsError

class MyFormatWriter:
    name = "my_out"
    supported_extensions = (".myout",)

    def write(self, signal, output_path, *, overwrite: bool = False) -> Path:
        path = Path(output_path)
        if path.exists() and not overwrite:
            raise OutputExistsError(f"{path} already exists; pass overwrite=True.")
        # ...persist `signal` to disk in your format...
        return path
```

### What happens if a plugin is broken?

AXIOMM aims to be tolerant of third-party breakage without silencing
real bugs:

- **Malformed entry-point value** (e.g. missing `:`) — logged at
  `WARNING` by `load_plugins`; that single plugin is skipped, the
  rest still register.
- **Plugin package uninstalled but entry-point metadata stale** —
  the registration succeeds (it's a lazy string), but
  `iter_readers()` (used by `reader="auto"`) logs a `WARNING` for
  that plugin and continues with the others.
- **Direct `get_reader("name")` of a broken plugin** — the
  underlying `ImportError` / `AttributeError` propagates, so
  explicit calls *do* fail loudly. Auto-detection is the tolerant
  path; named lookup is the strict path.

### Forcing a re-discovery

If you install a plugin into the running Python session (e.g. via
`pip install` from a notebook), call:

```python
from axiomm.io.converters import load_plugins
load_plugins()
```

to pick up the new entry points without restarting the process.
`load_plugins()` is idempotent — calling it repeatedly is safe.

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
