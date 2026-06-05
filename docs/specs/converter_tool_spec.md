# AXIOMM Converter Tool: Refactoring and Implementation Specification

## 0. Purpose of this specification

This document specifies how to refactor the current AXIOMM prototype converter into a reusable, testable, package-ready conversion tool.

The current converter is a working prototype for a specific XRM-map-style HDF5 input. The refactor must preserve that functionality while turning the converter into an extensible AXIOMM component that can later support multiple input formats, multiple output formats, command-line use, notebook use, and optional GUI-assisted workflows.

This specification is intended to be passed directly to a local coding agent such as Codex or Claude Code.

---

## 1. High-level judgement

The proposed strategy is good, provided the implementation follows one correction:

> The converter should be a headless importable library first. UX interfaces should be adapters around the library, not dependencies of the core conversion logic.

The final design should therefore have:

1. Four core callable modules/components.
2. A thin UX layer that calls those components.
3. No import-time prompts, GUI calls, or file dialogs.
4. A stable public Python API usable from both scripts and Jupyter notebooks.
5. A CLI entry point for reproducible batch conversion.

The current prototype should become the first concrete reader/writer workflow inside AXIOMM, not the whole architecture.

---

## 2. AXIOMM context

AXIOMM is expected to be a larger scientific data-analysis package, not only a file converter. The converter described here should live as one tool inside the AXIOMM pipeline.

Recommended package namespace:

```text
axiomm/
  io/
    converters/
      ...
```

Recommended CLI command:

```bash
axiomm-convert
```

The converter should eventually support high-dimensional spectroscopy and microscopy datasets, especially workflows that need reliable conversion into HyperSpy-compatible signal objects.

---

## 3. Current prototype responsibilities

The current single-file prototype performs all of the following in one script:

1. Prompts for a sample identifier.
2. Opens a Tkinter directory-selection dialog.
3. Finds `.h5` files containing the sample identifier.
4. Lets the user process one file or all matching files.
5. Opens each HDF5 file.
6. Extracts configuration metadata from XRM-specific HDF5 paths.
7. Extracts ROI/energy-region metadata.
8. Reads `/xrmmap/mcasum/counts`.
9. Builds a `hyperspy.signals.Signal1D`.
10. Assigns navigation and signal-axis metadata.
11. Saves the result as `.hspy`.

The refactor must split these responsibilities into isolated components.

---

## 4. Architecture overview

### 4.1 Four core components

The converter should be decomposed into four core components:

```text
Component 1: Input discovery and selection
Component 2: Format-specific reader and metadata extractor
Component 3: AXIOMM signal model and HyperSpy builder
Component 4: Output writer and conversion reporting
```

These four components must be callable independently.

### 4.2 UX layer

The UX layer must not be counted as a core component. It should wrap the four components and expose them through:

```text
1. Public Python API
2. CLI
3. Notebook helpers
4. Optional Tkinter GUI helpers
```

UX code may prompt the user. Core code must not.

---

## 5. Proposed package layout

Implement the converter under a `src/` layout:

```text
src/
  axiomm/
    __init__.py
    io/
      __init__.py
      converters/
        __init__.py
        models.py
        errors.py
        registry.py
        discovery.py
        workflows.py
        readers/
          __init__.py
          base.py
          xrmmap_h5.py
        signals/
          __init__.py
          hyperspy_builder.py
          validation.py
        writers/
          __init__.py
          base.py
          hspy.py
          manifest.py
        ux/
          __init__.py
          cli.py
          notebook.py
          tk_dialogs.py

tests/
  io/
    converters/
      test_discovery.py
      test_xrmmap_h5_reader.py
      test_hyperspy_builder.py
      test_hspy_writer.py
      test_workflows.py
      fixtures.py

pyproject.toml
README.md
LICENSE
CITATION.cff
```

The `src/axiomm/io/converters` package should be importable without importing Tkinter and without creating GUI windows.

---

## 6. Component 1: input discovery and selection

### 6.1 Module

```text
axiomm.io.converters.discovery
```

### 6.2 Responsibility

This component resolves user-supplied files or directories into a list of concrete input files to be converted.

It should handle:

- single-file input;
- directory input;
- recursive or non-recursive search;
- extension filtering;
- sample identifier filtering;
- deterministic ordering;
- basic validation of file existence and readability.

It must not:

- open HDF5 datasets;
- build HyperSpy signals;
- save output files;
- prompt the user;
- open GUI windows.

### 6.3 Public functions

```python
from pathlib import Path

from axiomm.io.converters.discovery import discover_inputs

files = discover_inputs(
    input_path=Path("/path/to/maps"),
    extensions=(".h5", ".hdf5"),
    sample="A21_054",
    recursive=False,
)
```

Recommended function signature:

```python
def discover_inputs(
    input_path: str | Path,
    *,
    extensions: tuple[str, ...] | None = None,
    sample: str | None = None,
    recursive: bool = False,
    require_non_empty: bool = True,
) -> list[Path]:
    ...
```

### 6.4 Behavioural requirements

- If `input_path` is a file, return `[input_path]` after validation.
- If `input_path` is a directory, search for matching files.
- Matching must be case-insensitive for extensions.
- Sample filtering should be substring-based for MVP, but the implementation should allow future regex matching.
- Returned paths must be sorted deterministically.
- Raise `InputDiscoveryError` if no files are found and `require_non_empty=True`.

---

## 7. Component 2: format-specific reader and metadata extractor

### 7.1 Module

```text
axiomm.io.converters.readers
```

The first concrete reader should be:

```text
axiomm.io.converters.readers.xrmmap_h5.XRMMapH5Reader
```

### 7.2 Responsibility

A reader converts a source file into an AXIOMM intermediate signal payload. The reader should know file-format details, but it must not know UX, CLI, Tkinter, or output-directory policy.

### 7.3 Reader protocol

Define a reader protocol or abstract base class:

```python
from pathlib import Path
from typing import Protocol

from axiomm.io.converters.models import AxiommSignalPayload

class Reader(Protocol):
    name: str
    supported_extensions: tuple[str, ...]

    def can_read(self, path: str | Path) -> bool:
        ...

    def read(self, path: str | Path, *, lazy: bool = True) -> AxiommSignalPayload:
        ...
```

### 7.4 XRMMapH5Reader requirements

The first reader must preserve the current prototype behaviour for XRM map files.

Default paths:

```text
counts dataset:          /xrmmap/mcasum/counts
config names:            /xrmmap/config/environ/name
config values:           /xrmmap/config/environ/value
ROI names:               /xrmmap/config/rois/name
ROI limits:              /xrmmap/config/rois/limits
beam size metadata key:  Experiment.Beam_Size__Nominal
```

The reader should extract:

- counts dataset;
- data shape;
- configuration metadata as a dictionary;
- ROI names and limits;
- beam size, if available;
- inferred navigation-axis scale;
- suggested signal type, initially `Signal1D`;
- original source metadata;
- reader diagnostics and warnings.

### 7.5 Configurability

The reader must not hard-code all scientific assumptions irreversibly. Use defaults, but allow override through a config object:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class XRMMapH5Config:
    counts_path: str = "/xrmmap/mcasum/counts"
    environ_name_path: str = "/xrmmap/config/environ/name"
    environ_value_path: str = "/xrmmap/config/environ/value"
    roi_name_path: str = "/xrmmap/config/rois/name"
    roi_limits_path: str = "/xrmmap/config/rois/limits"
    beam_size_key: str = "Experiment.Beam_Size__Nominal"
    fallback_field_width_um: float | None = 500.0
    energy_axis_name: str = "Energy"
    energy_axis_units: str = "keV"
    energy_scale: float = 40.96 / 4096
    roi_limit_scale: float = 0.01
```

Then:

```python
reader = XRMMapH5Reader(config=XRMMapH5Config(energy_scale=0.01))
payload = reader.read("A21_054_map.h5")
```

### 7.6 String decoding

The reader must robustly decode byte strings from HDF5 datasets.

Support at least:

- `bytes`;
- fixed-width byte strings;
- null-padded byte strings;
- NumPy bytes arrays;
- already-decoded strings.

Implement helper functions:

```python
def decode_hdf5_string(value: object) -> str:
    ...


def decode_hdf5_string_array(values: object) -> list[str]:
    ...
```

### 7.7 Beam-size parsing

The current prototype only handles values like `"1 um"` after lowercasing and stripping `"um"`. The refactor should accept:

```text
1um
1 um
1 µm
1 μm
1.0um
1.0 micrometer
1.0 micrometre
```

Implement:

```python
def parse_micrometre_value(value: str) -> float:
    ...
```

Raise a specific `MetadataParseError` if parsing fails.

### 7.8 Missing metadata policy

Missing optional metadata must not crash conversion by default.

Examples:

- missing beam size: use fallback scale if configured;
- missing ROI metadata: emit warning but still convert counts;
- missing configuration table: emit warning and continue if counts exist;
- missing counts dataset: fail with `DatasetNotFoundError`.

All warnings should be attached to the returned payload as structured diagnostics, not only printed.

---

## 8. Component 3: AXIOMM signal model and HyperSpy builder

### 8.1 Modules

```text
axiomm.io.converters.models
axiomm.io.converters.signals.hyperspy_builder
axiomm.io.converters.signals.validation
```

### 8.2 Responsibility

This component defines the neutral internal representation and converts that representation into a HyperSpy signal.

The internal model must be independent of HyperSpy where possible. HyperSpy-specific code belongs in the builder.

### 8.3 Data model

Implement these dataclasses in `models.py`.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

import numpy as np

AxisRole = Literal["navigation", "signal"]
SignalKind = Literal["auto", "signal1d", "signal2d", "base"]
Severity = Literal["info", "warning", "error"]

@dataclass(frozen=True)
class AxisSpec:
    name: str
    role: AxisRole
    size: int
    units: str | None = None
    scale: float | None = None
    offset: float = 0.0
    index_in_array: int | None = None

@dataclass(frozen=True)
class Diagnostic:
    severity: Severity
    code: str
    message: str
    context: Mapping[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class SourceProvenance:
    path: Path
    reader: str
    reader_version: str | None = None
    input_hash: str | None = None

@dataclass
class AxiommSignalPayload:
    data: Any
    axes: tuple[AxisSpec, ...]
    signal_kind: SignalKind
    metadata: dict[str, Any] = field(default_factory=dict)
    original_metadata: dict[str, Any] = field(default_factory=dict)
    provenance: SourceProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    title: str | None = None
```

Notes:

- `data` is intentionally typed as `Any` rather than strictly `np.ndarray` because large HDF5-backed or lazy data should not necessarily be materialised immediately.
- Axis order must be explicit through `index_in_array`.
- `signal_kind="auto"` should be allowed but should resolve deterministically in the builder.

### 8.4 HyperSpy builder

Implement:

```python
from axiomm.io.converters.models import AxiommSignalPayload

class HyperSpyBuilder:
    def build(self, payload: AxiommSignalPayload):
        ...
```

Convenience function:

```python
def build_hyperspy_signal(payload: AxiommSignalPayload):
    return HyperSpyBuilder().build(payload)
```

### 8.5 Signal-kind resolution

Rules:

- `signal_kind="signal1d"` -> create `hs.signals.Signal1D(data)`.
- `signal_kind="signal2d"` -> create `hs.signals.Signal2D(data)`.
- `signal_kind="base"` -> create a generic HyperSpy base signal if appropriate.
- `signal_kind="auto"` -> infer from the number of axes with `role="signal"`.

MVP inference:

```text
1 signal axis  -> Signal1D
2 signal axes  -> Signal2D
otherwise      -> BaseSignal or explicit error, depending on HyperSpy compatibility
```

### 8.6 Axis validation

Before building a HyperSpy signal, validate:

- number of `AxisSpec` entries equals `data.ndim`, when `data.ndim` is available;
- each axis size matches the corresponding data dimension, when shape is available;
- exactly one signal axis exists for `signal1d`;
- exactly two signal axes exist for `signal2d`;
- navigation axes and signal axes are explicit;
- unit strings are normalised where possible.

### 8.7 Axis assignment

The builder must assign:

- axis name;
- units;
- scale;
- offset.

It must avoid assuming that HyperSpy's internal axis order matches the input order without validation. Tests must assert that the resulting HyperSpy `axes_manager` has the expected navigation and signal axes.

### 8.8 Metadata assignment

The builder should copy:

```text
payload.metadata           -> signal.metadata
payload.original_metadata  -> signal.original_metadata
payload.title              -> signal.metadata.General.title, when available
payload.provenance         -> metadata under an AXIOMM-specific namespace
payload.diagnostics        -> metadata under an AXIOMM-specific namespace
```

Recommended namespace:

```text
signal.metadata.AXIOMM
```

---

## 9. Component 4: output writer and conversion reporting

### 9.1 Modules

```text
axiomm.io.converters.writers
axiomm.io.converters.workflows
```

### 9.2 Responsibility

This component saves converted outputs and returns structured reports.

It must not:

- discover input files;
- parse HDF5 internals;
- open GUI prompts.

### 9.3 Writer protocol

```python
from pathlib import Path
from typing import Protocol

class Writer(Protocol):
    name: str
    supported_extensions: tuple[str, ...]

    def write(
        self,
        signal: object,
        output_path: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        ...
```

### 9.4 MVP writer

Implement:

```text
HSpyWriter
```

Default output extension:

```text
.hspy
```

### 9.5 Manifest writer

Each conversion should optionally create a sidecar manifest:

```text
<output>.axiomm.json
```

The manifest should include:

- input path;
- output path;
- reader name;
- writer name;
- AXIOMM version;
- conversion timestamp in ISO 8601;
- source data shape;
- axes summary;
- warnings and diagnostics;
- relevant configuration values;
- optional input hash, if requested.

### 9.6 Conversion result model

Add to `models.py`:

```python
@dataclass(frozen=True)
class ConversionResult:
    input_path: Path
    output_path: Path
    manifest_path: Path | None
    reader_name: str
    writer_name: str
    diagnostics: tuple[Diagnostic, ...] = ()
```

### 9.7 Overwrite policy

Default must be safe:

```text
overwrite=False
```

If the output exists and `overwrite=False`, raise `OutputExistsError`.

Allow CLI flags:

```bash
--overwrite
--skip-existing
```

Do not silently overwrite scientific data.

---

## 10. UX layer

### 10.1 Modules

```text
axiomm.io.converters.ux.cli
axiomm.io.converters.ux.notebook
axiomm.io.converters.ux.tk_dialogs
```

### 10.2 Rule

The UX layer may call the four core components. The four core components must not import the UX layer.

This avoids circular dependencies and keeps the converter usable in scripts, notebooks, CI, servers, and headless environments.

### 10.3 Public Python API

Expose these from `axiomm.io.converters.__init__`:

```python
from axiomm.io.converters.discovery import discover_inputs
from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Reader
from axiomm.io.converters.signals.hyperspy_builder import build_hyperspy_signal
from axiomm.io.converters.workflows import convert_file, convert_many
```

Recommended usage in a Python script:

```python
from pathlib import Path

from axiomm.io.converters import convert_file

result = convert_file(
    input_path=Path("A21_054_map.h5"),
    output_path=Path("A21_054_map.hspy"),
    reader="xrmmap_h5",
    writer="hspy",
    overwrite=False,
)

print(result.output_path)
```

Recommended usage in a notebook:

```python
from axiomm.io.converters import XRMMapH5Reader, build_hyperspy_signal

reader = XRMMapH5Reader()
payload = reader.read("A21_054_map.h5")
signal = build_hyperspy_signal(payload)
signal.plot()
```

### 10.4 CLI

Add a console script entry point:

```text
axiomm-convert = "axiomm.io.converters.ux.cli:main"
```

MVP CLI examples:

```bash
axiomm-convert A21_054_map.h5 --reader xrmmap_h5 --output A21_054_map.hspy
```

```bash
axiomm-convert /path/to/maps --sample A21_054 --reader xrmmap_h5 --output-dir /path/to/out --all
```

```bash
axiomm-convert /path/to/maps --sample A21_054 --reader xrmmap_h5 --output-dir /path/to/out --recursive --skip-existing
```

Required CLI options:

```text
input_path positional argument
--reader
--output or --output-dir
--sample
--all
--recursive
--overwrite
--skip-existing
--manifest / --no-manifest
--lazy / --no-lazy
--verbose
--quiet
```

The CLI must be non-interactive by default. Prompting is allowed only with an explicit flag:

```bash
--interactive
```

### 10.5 Tkinter GUI helper

Tkinter must be optional and isolated.

```python
from axiomm.io.converters.ux.tk_dialogs import choose_directory

path = choose_directory(title="Select maps directory")
```

Implementation requirement:

```python
root = tk.Tk()
root.withdraw()
root.update()
root.attributes("-topmost", True)
path = filedialog.askdirectory(parent=root, title=title)
root.attributes("-topmost", False)
root.destroy()
```

Do not call this from core conversion code.

### 10.6 Notebook helper

Notebook helpers should return objects, not only print strings.

Suggested functions:

```python
def notebook_select_directory() -> Path | None:
    ...


def notebook_preview_payload(payload: AxiommSignalPayload):
    ...


def notebook_convert_interactive(...):
    ...
```

Notebook helpers are convenience adapters. They must not be required for normal package operation.

---

## 11. Workflow orchestration

### 11.1 Module

```text
axiomm.io.converters.workflows
```

### 11.2 `convert_file`

```python
def convert_file(
    input_path: str | Path,
    *,
    output_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    reader: str | Reader = "auto",
    writer: str | Writer = "hspy",
    overwrite: bool = False,
    skip_existing: bool = False,
    manifest: bool = True,
    lazy: bool = True,
) -> ConversionResult:
    ...
```

Responsibilities:

1. Resolve reader.
2. Read payload.
3. Build HyperSpy signal.
4. Resolve output path.
5. Write signal.
6. Write manifest if requested.
7. Return `ConversionResult`.

### 11.3 `convert_many`

```python
def convert_many(
    input_paths: list[str | Path],
    *,
    output_dir: str | Path,
    reader: str | Reader = "auto",
    writer: str | Writer = "hspy",
    overwrite: bool = False,
    skip_existing: bool = False,
    manifest: bool = True,
    lazy: bool = True,
    continue_on_error: bool = True,
) -> list[ConversionResult]:
    ...
```

Responsibilities:

- Convert files one by one.
- Return successful results and structured diagnostics.
- If `continue_on_error=False`, fail on the first error.
- If `continue_on_error=True`, keep going and return error diagnostics.

---

## 12. Reader and writer registry

### 12.1 Module

```text
axiomm.io.converters.registry
```

### 12.2 Requirement

Implement a lightweight registry for readers and writers.

```python
register_reader(XRMMapH5Reader())
reader = get_reader("xrmmap_h5")
```

MVP registry can be internal and static.

Future version may support plugin discovery through Python entry points.

### 12.3 Reader auto-detection

`reader="auto"` should attempt:

1. extension match;
2. `reader.can_read(path)`;
3. fail with `ReaderDetectionError` if ambiguous or unsupported.

Ambiguous auto-detection must fail explicitly rather than guessing.

---

## 13. Error classes

Create `errors.py`:

```python
class AxiommConverterError(Exception):
    """Base exception for AXIOMM converter errors."""

class InputDiscoveryError(AxiommConverterError):
    ...

class ReaderDetectionError(AxiommConverterError):
    ...

class UnsupportedFormatError(AxiommConverterError):
    ...

class DatasetNotFoundError(AxiommConverterError):
    ...

class MetadataParseError(AxiommConverterError):
    ...

class SignalValidationError(AxiommConverterError):
    ...

class OutputExistsError(AxiommConverterError):
    ...

class ConversionWorkflowError(AxiommConverterError):
    ...
```

Avoid bare `except Exception` except at workflow boundaries where errors are converted into structured diagnostics.

---

## 14. Logging and diagnostics

Replace `print(...)` calls with logging and structured diagnostics.

Use:

```python
import logging

logger = logging.getLogger(__name__)
```

Core components should log useful details at `debug` or `info` level but must not be verbose by default.

CLI should configure logging from:

```text
--verbose
--quiet
```

Warnings about missing optional metadata must be added to `payload.diagnostics` and, where appropriate, to the manifest.

---

## 15. Scientific metadata policy

The converter must distinguish:

```text
observed metadata     metadata present in the source file
inferred metadata     metadata derived from shape or config
assumed metadata      fallback or user-configured defaults
```

Example:

- `beam_size_um` from `Experiment.Beam_Size__Nominal` is observed/inferred from source metadata.
- `fallback_field_width_um=500.0` is an assumption and must be recorded as such.
- `energy_scale=40.96/4096` is an assumption unless explicitly present in the source file.

Manifest and HyperSpy metadata should expose this distinction.

Recommended metadata structure:

```python
payload.metadata["AXIOMM"] = {
    "converter": {
        "reader": "xrmmap_h5",
        "assumptions": [...],
        "diagnostics": [...],
    },
    "axes": {...},
    "source": {...},
}
```

---

## 16. Memory and large-data policy

AXIOMM may handle very large spectroscopy/microscopy data. Therefore:

- Do not eagerly convert large HDF5 datasets to NumPy arrays unless necessary.
- Prefer preserving lazy or file-backed data where HyperSpy supports it.
- Provide `lazy=True` as the default reader/workflow option.
- Allow `lazy=False` for small files and tests.
- Tests may use small synthetic arrays.

If true lazy support cannot be completed in the first implementation, expose the `lazy` argument but document that MVP behaviour is eager for the first reader. Do not pretend lazy conversion works unless tested.

---

## 17. Current XRM-map conversion defaults

The migrated XRM map reader should reproduce these current behaviours unless overridden:

```text
Input format:              .h5 / .hdf5
Primary dataset:           /xrmmap/mcasum/counts
Default signal kind:       signal1d
Navigation axes:           x, y
Navigation units:          µm
Signal axis:               Energy
Signal units:              keV
Energy scale:              40.96 / 4096
Beam-size metadata key:    Experiment.Beam_Size__Nominal
Fallback nav scale:        500 / xdim
Output format:             .hspy
```

Open question to resolve scientifically:

> The values `40.96 / 4096`, `500 / xdim`, and ROI-limit division by `100` must be justified, parameterised, or extracted from metadata before public release. They should not remain hidden constants.

---

## 18. Licence and header issue

The current prototype header says `MIT License` but also includes an additional special acknowledgement/usage clause for a collaborator.

This must be resolved before public packaging.

Acceptable options:

1. Use a clean standard licence, such as MIT, BSD-3-Clause, Apache-2.0, GPL-3.0, etc., and move collaborator acknowledgement to `ACKNOWLEDGEMENTS.md`, `README.md`, and `CITATION.cff`.
2. Keep a custom licence, but do not call it MIT and do not present the package as standard open-source MIT-licensed software.
3. Consult institutional/legal guidance before public distribution.

Implementation agent must not silently preserve the current header as standard MIT.

Add a packaging blocker:

```text
BLOCKER: Resolve licence/header inconsistency before PyPI/public GitHub release.
```

---

## 19. Packaging requirements

Use `pyproject.toml`.

Suggested package metadata:

```toml
[project]
name = "axiomm"
version = "0.1.0"
description = "AXIOMM: tools for microscopy and spectroscopy data conversion and analysis"
requires-python = ">=3.10"
dependencies = [
    "numpy",
    "pandas",
    "h5py",
    "hyperspy",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-cov", "ruff", "mypy"]
notebook = ["ipywidgets", "jupyter"]

[project.scripts]
axiomm-convert = "axiomm.io.converters.ux.cli:main"
```

Do not add Tkinter to pip dependencies; it is normally provided by the Python distribution or OS packages. GUI code should fail gracefully with a clear message if Tkinter is unavailable.

---

## 20. Testing requirements

### 20.1 Synthetic HDF5 fixture

Create a fixture that generates a minimal valid XRM-map-like HDF5 file:

```text
/xrmmap/mcasum/counts
/xrmmap/config/environ/name
/xrmmap/config/environ/value
/xrmmap/config/rois/name
/xrmmap/config/rois/limits
```

Use a small shape, for example:

```text
(4, 3, 16)
```

### 20.2 Unit tests

Required tests:

```text
test_discover_single_file
test_discover_directory_sample_filter
test_xrmmap_can_read_valid_file
test_xrmmap_read_counts_shape
test_xrmmap_extracts_config_metadata
test_xrmmap_extracts_roi_metadata
test_parse_micrometre_value_variants
test_missing_counts_dataset_raises
test_missing_roi_metadata_warns_but_converts
test_hyperspy_builder_signal1d_axes
test_hspy_writer_refuses_overwrite_by_default
test_convert_file_end_to_end
test_import_has_no_side_effects
```

### 20.3 No-GUI import test

Add a test that imports the package and verifies no Tkinter window or prompt is triggered.

Example:

```python
def test_import_has_no_side_effects():
    import axiomm.io.converters
```

This test must not require a display server.

### 20.4 CLI tests

Use subprocess or Click/Typer test tools if a CLI framework is introduced.

Required CLI behaviours:

```text
axiomm-convert --help exits 0
missing input exits non-zero
valid synthetic file converts successfully
existing output without --overwrite exits non-zero
```

---

## 21. Documentation requirements

Add documentation pages or README sections for:

1. What the converter does.
2. Supported formats.
3. Supported outputs.
4. Python API usage.
5. Notebook usage.
6. CLI usage.
7. GUI helper usage.
8. Scientific assumptions and metadata policy.
9. Adding a new reader.
10. Adding a new writer.
11. Licence and citation.

Add a short example:

```python
from axiomm.io.converters import convert_file

result = convert_file(
    "A21_054_map.h5",
    output_path="A21_054_map.hspy",
    reader="xrmmap_h5",
)

print(result)
```

Add a lower-level example:

```python
from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Reader
from axiomm.io.converters.signals.hyperspy_builder import build_hyperspy_signal

payload = XRMMapH5Reader().read("A21_054_map.h5")
signal = build_hyperspy_signal(payload)
signal.plot()
```

---

## 22. Compatibility with the HyperSpy/RosettaSciIO ecosystem

Do not try to replace all general scientific file I/O.

AXIOMM should focus on:

- project-specific or instrument-specific readers;
- metadata correction and preservation;
- robust conversion into analysis-ready HyperSpy signals;
- reproducible conversion manifests;
- integration into the AXIOMM analysis pipeline.

Future extension:

```python
payload.to_rsciio_dict()
```

or an adapter that makes AXIOMM payloads structurally close to RosettaSciIO-style dictionaries.

This should be considered later, not required for MVP.

---

## 23. Implementation phases

### Phase 0: safe extraction

Goal: move existing behaviour into package form without changing scientific output.

Tasks:

1. Create package skeleton.
2. Implement models and errors.
3. Implement `XRMMapH5Reader` using the current HDF5 paths.
4. Implement `HyperSpyBuilder`.
5. Implement `HSpyWriter`.
6. Implement `convert_file`.
7. Add synthetic HDF5 tests.
8. Ensure no GUI or input prompt occurs on import.

### Phase 1: CLI and notebook usability

Tasks:

1. Implement `axiomm-convert` CLI.
2. Add notebook examples.
3. Add optional Tkinter helper.
4. Replace print statements with logging.
5. Add manifest writing.

### Phase 2: configurability and validation

Tasks:

1. Add `XRMMapH5Config`.
2. Parameterise energy scale, ROI scale, fallback field width.
3. Add metadata provenance classification.
4. Add stricter axis validation.
5. Add end-to-end tests against one known real file, if one can be safely included or mocked.

### Phase 3: extensibility

Tasks:

1. Add reader registry.
2. Add writer registry.
3. Add generic HDF5 schema-driven reader prototype.
4. Add plugin discovery only if needed.
5. Add additional output formats only when scientifically justified.

---

## 24. Acceptance criteria

The implementation is acceptable when all of the following are true:

1. `import axiomm.io.converters` opens no GUI and asks no questions.
2. `XRMMapH5Reader().read(path)` works independently.
3. `build_hyperspy_signal(payload)` works independently.
4. `HSpyWriter().write(signal, path)` works independently.
5. `convert_file(...)` performs full conversion.
6. `discover_inputs(...)` works independently.
7. `axiomm-convert --help` works.
8. A synthetic XRM-map HDF5 fixture converts successfully in tests.
9. Missing optional metadata produces diagnostics, not silent failure.
10. Missing required counts data fails clearly.
11. Existing output is not overwritten unless explicitly requested.
12. The current licence/header inconsistency is documented as a release blocker.
13. The scientific constants from the prototype are exposed as configuration, not hidden magic numbers.

---

## 25. Specific instructions for the coding agent

Implement this refactor incrementally.

Do not rewrite unrelated parts of AXIOMM.

Do not add GUI logic to package import paths.

Do not introduce global code that prompts with `input()` outside CLI or explicit interactive helpers.

Prefer `pathlib.Path` over raw string path manipulation.

Prefer dataclasses for simple immutable configuration and result objects.

Prefer explicit exceptions over returning `None` on failure.

Preserve the current XRM-map conversion defaults, but parameterise them.

Add tests before broadening format support.

Do not claim support for a format, output, or lazy execution mode unless covered by tests.

Keep the current prototype available as a reference during migration, but do not leave it as the public implementation.

---

## 26. Minimal first implementation target

A minimal but good first implementation should allow this:

```python
from axiomm.io.converters import convert_file

result = convert_file(
    input_path="example_xrmmap.h5",
    output_path="example_xrmmap.hspy",
    reader="xrmmap_h5",
    overwrite=False,
)
```

And this:

```python
from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Reader
from axiomm.io.converters.signals.hyperspy_builder import build_hyperspy_signal

payload = XRMMapH5Reader().read("example_xrmmap.h5")
signal = build_hyperspy_signal(payload)
```

And this:

```bash
axiomm-convert example_xrmmap.h5 --reader xrmmap_h5 --output example_xrmmap.hspy
```

All three routes must use the same core conversion logic.

