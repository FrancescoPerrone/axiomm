# Known issues and common pitfalls

This page collects the user-facing traps across AXIOMM. Some are bugs
in *external* artefacts (the legacy prototype's outputs); some are
deliberate forward-compatibility no-ops in the current MVP; some are
domain footguns AXIOMM guards against on your behalf but wants you to
understand. Read this before you waste an hour debugging a
correctly-behaving function.

```{contents}
:local:
:depth: 2
```

## Legacy prototype: silently swapped x and y axis labels

**Scope.** Any `.hspy` file produced by
`docs/specs/_legacy/converter_prototype.py` (or any other code using
the same `axes_manager.navigation_axes[0].name = 'x'` pattern).

**Symptom.** The data values are correct, but the axis with
`index_in_array == 0` is *named* `'y'` and the axis with
`index_in_array == 1` is named `'x'`. Spatial maps appear transposed
relative to the physical sample. When `xdim ≠ ydim`, the axis *scales*
are also wrong, not just the labels.

**Cause.** HyperSpy orders `axes_manager.navigation_axes` and
`axes_manager.signal_axes` in *reverse* numpy order within each role
group. For a numpy array of shape `(d0, d1, d2)` constructed as
`hs.signals.Signal1D(data)`:

| HyperSpy axis              | numpy axis | numpy size |
|----------------------------|------------|------------|
| `navigation_axes[0]`       | 1          | `d1`       |
| `navigation_axes[1]`       | 0          | `d0`       |
| `signal_axes[0]`           | 2          | `d2`       |

The legacy prototype assumed `navigation_axes[0]` was numpy axis 0
(`xdim` in our convention), which is wrong — it's numpy axis 1
(`ydim`).

**Fix path.** Re-run the new converter on the original `.h5` files:

```python
from axiomm.io.converters import convert_file

convert_file(
    input_path="A21_054_map.h5",      # original instrument file
    output_path="A21_054_map.hspy",   # overwrite the legacy output
    reader="xrmmap_h5",
    overwrite=True,                   # explicitly authorise replacement
)
```

The new builder matches `AxisSpec.index_in_array` to HyperSpy's
per-axis `index_in_array`, so the convention reversal is handled
correctly. Verify with:

```python
import hyperspy.api as hs
signal = hs.load("A21_054_map.hspy")
by_index = {
    a.index_in_array: a
    for a in list(signal.axes_manager.navigation_axes)
       + list(signal.axes_manager.signal_axes)
}
assert by_index[0].name == "x"
assert by_index[1].name == "y"
```

**Rule for AXIOMM contributors.** Any code that does
`signal.axes_manager.navigation_axes[i].name = ...` (or `.scale = ...`,
`.units = ...`) by tuple position is a likely re-occurrence of this
bug. Map by `index_in_array` instead. The neutral `AxiommSignalPayload`
carries `AxisSpec.index_in_array` precisely for this purpose; see
`axiomm.io.converters.signals.hyperspy_builder` for the reference
implementation.

## Choosing the right ROI variant on real XRM files

**Scope.** Real instrument XRM files where ROI limits have shape
`(n_rois, n_variants, 2)` (multiple ROI variants per element — likely
per-detector or per-fit-pass), not the `(n_rois, 2)` the prototype
expected.

**Default behaviour as of Chunk 9.** The reader detects the 3-D shape
and extracts `limits[:, XRMMapH5Config.roi_variant_index, :]`. The
default `roi_variant_index = 0` works for the typical "first variant
is the canonical one" convention. ROIs are extracted normally with
no warning. Verified end-to-end on the real
`IE_30s_map__Sep16_15_20_39_A22-043_1_001.h5` file: 35 ROIs
extracted, e.g. `Si Ka` at 1.64–1.84 keV (Si Kα ≈ 1.74 keV).

**When you need a different variant.**

```python
from axiomm.io.converters import XRMMapH5Config, XRMMapH5Reader, convert_file

reader = XRMMapH5Reader(config=XRMMapH5Config(roi_variant_index=3))
convert_file("input.h5", output_path="out.hspy", reader=reader)
```

**Out-of-bounds index.** If you set `roi_variant_index` beyond the
file's variant axis length, the reader emits a
`roi_variant_out_of_bounds` diagnostic naming the available range and
skips ROI extraction — same fail-soft policy as for missing metadata.

**Files with the original 2-D `(n_rois, 2)` shape** (e.g. the
synthetic test fixture, or older files) continue to work without any
config tweak.

## Truly unexpected ROI limits shapes

If a file's ROI limits dataset is neither 2-D nor 3-D-with-last-dim-2
(e.g. a 4-D layout or a last dimension that isn't 2), the reader
emits the `roi_limits_unexpected_shape` diagnostic and skips ROI
extraction. The message names the actual shape. Recovery requires
either post-processing the file yourself or filing an issue with the
shape so we can extend the reader.

## `lazy=True` currently downgrades to eager

**Scope.** Any call to `convert_file(..., lazy=True)` or
`Reader.read(..., lazy=True)`. `lazy=True` is the documented default.

**Symptom.** Memory usage is proportional to the dataset size, not
proportional to your access pattern. A `lazy_downgraded_to_eager`
diagnostic appears in the result.

**Cause.** The MVP reader materialises the counts dataset into a NumPy
array regardless of the `lazy` flag. The flag is accepted for forward
compatibility (so callers don't have to change when true lazy support
lands).

**Fix path.** True lazy execution (likely via `dask`-backed
`HyperSpy.LazySignal`) is on the longer roadmap. For now, if you don't
want the diagnostic noise:

```python
convert_file(..., lazy=False)
```

## `convert_file` refuses to overwrite by default

**Scope.** Any call to `convert_file` whose output path already exists,
called without `overwrite=True` or `skip_existing=True`.

**Symptom.** `OutputExistsError` is raised with a message naming the
path and the flags that would unblock the call.

**Cause.** AXIOMM's spec §9.7 explicitly forbids silently replacing
scientific output. The strict default protects you from clobbering a
day's analysis with an unintended re-run.

**Fix path.** Pick one:

- `overwrite=True` — replace the existing file.
- `skip_existing=True` — leave the existing file alone and short-circuit
  before reading; useful for resuming a batch.
- Different `output_path` — write somewhere else.

## See also

- {doc}`Converter user guide <converter>` — the canonical reference for
  `convert_file`.
- [Architecture: HyperSpy axis-reversal](https://github.com/FrancescoPerrone/axiomm/wiki/Converter-Architecture#known-gotcha--hyperspy-axis-reversal-vs-numpy)
  — wiki section with the full convention table.
- [Specification §18](https://github.com/FrancescoPerrone/axiomm/blob/main/docs/specs/converter_tool_spec.md#18-licence-and-header-issue)
  — the licence-header release blocker, separate from the bugs on this
  page but worth knowing about for publication.
