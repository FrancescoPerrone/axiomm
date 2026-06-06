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
print(signal)                                 # <Signal1D, …>
print(signal.metadata.AXIOMM.reader)          # 'xrmmap_h5'
print(signal.metadata.General.title)          # 'A21_054_map'
print(signal.axes_manager)                    # x, y in µm; Energy in keV
```

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

If the configured `counts_path` is missing from the file, the reader
raises `DatasetNotFoundError` with a message that names both the path
it looked at *and* the config field to override — so you don't have to
read the source to know what to change.

Missing **optional** metadata (the environ table, the ROI table, the
beam-size key) is non-fatal: the reader attaches a structured
`Diagnostic` to the payload and continues. This is by design (spec
§7.8): scientific-data safety, but graceful degradation.

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
| `manifest_not_yet_implemented`    | info     | You passed `manifest=True` (the default); the sidecar isn't written yet (Chunk 7 deliverable). |
| `output_skipped_existing`         | info     | `skip_existing=True` matched; no read/build/write was performed.                                |
| `environ_missing`                 | warning  | The XRM environ config table wasn't found; fell back to `fallback_field_width_um`.             |
| `beam_size_missing`               | warning  | The configured beam-size key wasn't in the environ table; fell back.                           |
| `beam_size_unparseable`           | warning  | The beam-size string couldn't be parsed; fell back.                                            |
| `roi_missing`                     | warning  | ROI metadata datasets weren't present; ROIs not extracted.                                     |
| `roi_limits_unexpected_shape`     | warning  | ROI limits had an unexpected shape (e.g. `(n, k, 2)` on real files); ROIs not extracted.       |
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
