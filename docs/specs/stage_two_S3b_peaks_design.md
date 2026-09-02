# AXIOMM Stage Two · S3b — Peak identification (`axiomm.analysis.peaks`) design

> **Status:** design approved 2026-08-31. Second of four
> S3 sub-chunks (S3a reference · **S3b peaks** · S3c Cliff-Lorimer
> quantification · S3d matching + labels). Builds on S0 (`axiomm.analysis`)
> and reuses the converter's `AxisSpec`.

## 1. Goal

A **general spectroscopy primitive**: given one spectrum, a validated
energy axis, and a set of target line energies, produce a
**background-corrected net intensity per line**. Standalone and composed
by S3c (Cliff-Lorimer quantification). Built pluggable so alternative
methods (smoothing, Beer-Lambert, interactive) drop in behind one
protocol; peak *detection* of unknown lines is a deferred extension.

## 2. Guiding principles

- **Pluggable from day one.** A `PeakMeasurer` protocol + registry
  (name→class), with the flanking-window net-intensity method as the
  first backend and explicit room for `smoothing` / `beer_lambert` /
  interactive backends behind the same `measure(...)` contract.
- **Headless core, UX on top.** Interactivity is a UX adapter over the
  headless core, never inside it.
- **General, not mineralogy-specific.** `line_energies` is a generic
  `label→keV` mapping; the tool never imports mineralogy. Callers pass
  `MineralogyReference` element line energies or explicit ones.
- **Measurement facts only.** Peaks report net/gross/background;
  reliability *judgments* (detection floor, validity) belong to S3c.
- **Parameter autonomy.** Background-window sizes are exposed config; the
  `cliff_lorimer.py` values ship as documented example defaults, never
  baked.
- Named exceptions, no import side effects, never silently overwrite.

## 3. Components

### 3.1 Energy-axis resolution (shared) — `peaks/energy.py`

```python
def resolve_energy_axis(axis_spec: AxisSpec, n_channels: int) -> np.ndarray: ...
```

Validates and builds the per-channel energy array in **keV**:
- `axis_spec.size == n_channels` else `PayloadValidationError`;
- `axis_spec.scale` present (not `None`) else `PayloadValidationError`;
- units recognised — `"keV"` used directly, `"eV"` converted
  (`scale/1000`, `offset/1000`); any other/`None` →
  `PayloadValidationError` (no silent `0.01`);
- returns `offset_kev + scale_kev * arange(n_channels)`.

S3c reuses this for the identical channel→keV guarantee.

### 3.2 `PeakMeasurer` protocol — `peaks/base.py`

```python
@runtime_checkable
class PeakMeasurer(Protocol):
    name: str
    def measure(
        self,
        spectrum,
        energy_axis: AxisSpec,
        line_energies: Mapping[str, float],
    ) -> PeakMeasurementSet: ...
```

Backend parameters live on the instance (construction), keeping the
protocol backend-agnostic — smoothing/Beer-Lambert backends bring their
own config.

### 3.3 Result payloads — `peaks/models.py`

```python
@dataclass(frozen=True)
class PeakMeasurement:
    label: str
    center_kev: float
    net: float
    gross: float
    background: float      # per-channel background under the peak
    n_channels: int        # channels in the peak window
    in_range: bool         # was the line inside the axis span

@dataclass
class PeakMeasurementSet:
    measurements: tuple[PeakMeasurement, ...]   # order = line_energies order
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def net_by_label(self) -> dict[str, float]: ...   # convenience for S3c
```

Composition (explicit `provenance`/`diagnostics`), consistent with
S2/S3a.

### 3.4 `NetIntensityMeasurer` — `peaks/net_intensity.py`

- `name = "net_intensity"`.
- `PeakWindowConfig(half_width_kev=0.06, bg_gap_kev=0.04, bg_width_kev=0.10)`
  — the `cliff_lorimer.py` values as **documented example defaults**.
- For each `(label, center_kev)`: if the centre is outside the axis span
  → `in_range=False`, all quantities 0. Otherwise flanking-window linear
  background (median of the left/right flank windows, averaged over
  available sides), `gross = Σ spectrum[peak_mask]`,
  `net = max(gross − bg_per_ch · n_peak_channels, 0)`.
- Provenance records `tool="peaks"`, `backend="net_intensity"`, and the
  window config.

### 3.5 Registry — `peaks/__init__.py`

`peak_measurers` registry (name→**class**, like clusterers, since
backends are configured); `"net_intensity"` registered;
`get_peak_measurer(name)` returns the class for typed construction.
Entry-point discovery deferred with the clusterer follow-up.

### 3.6 Batch helper — `peaks/__init__.py`

```python
def measure_cluster_means(
    means: ClusterMeanSpectra,
    energy_axis: AxisSpec,
    line_energies: Mapping[str, float],
    *,
    measurer: PeakMeasurer,
) -> tuple[PeakMeasurementSet, ...]: ...
```

Maps the single-spectrum primitive over each row of `means.means`,
aligned to `means.cluster_ids`. Keeps the core a single-spectrum
primitive while feeding S3c per cluster.

### 3.7 File adapters — `peaks/io.py`

`write_peaks` / `read_peaks` for a `PeakMeasurementSet` — a **versioned
JSON** sidecar (`schema_version`, the per-line measurements, provenance,
diagnostics; scalars only, so no `.npz`). `OutputExistsError`-guarded.

## 4. Data flow

spectrum + `AxisSpec` + `line_energies` →
`NetIntensityMeasurer(config).measure(...)` → `PeakMeasurementSet`
(per-line net/gross/background). Batched over `ClusterMeanSpectra` for
S3c, which applies k-factors + the reliability gate.

## 5. Error handling

- Energy-axis validation failures → `PayloadValidationError`.
- Non-finite spectrum values → `PayloadValidationError`.
- A line outside the axis span is **not** an error — `in_range=False`
  with a `line_out_of_range` diagnostic.
- `OutputExistsError` on non-overwrite writes.

## 6. Testing

- Net intensity on a synthetic Gaussian-on-flat-background at a known
  centre recovers ≈ the injected area; a flat continuum is subtracted to
  ≈ 0 net.
- A line outside the axis span → `in_range=False`, `net==0`, and a
  `line_out_of_range` diagnostic.
- Energy-axis validation: size mismatch, missing scale, `eV` conversion
  (10 eV/ch → 0.01 keV/ch), unknown/`None` units → `PayloadValidationError`.
- Non-finite spectrum → `PayloadValidationError`.
- Registry resolves `"net_intensity"` to the class; unknown →
  `BackendNotFoundError`.
- `measure_cluster_means` returns one `PeakMeasurementSet` per cluster,
  aligned to `cluster_ids`.
- io round-trips a `PeakMeasurementSet` with `schema_version`.

## 7. Dependencies

numpy only (core). No xraylib/sklearn/h5py at this layer.

## 8. Deferred / follow-ups

- **Alternative backends** (Francesco's sketches): smoothing-based,
  Beer-Lambert absorption, interactive — each a new `PeakMeasurer`.
- **Peak detection** of unknown lines (a second protocol).
- Escape/pile-up/line-overlap deconvolution.

## 9. Constraints reaffirmed

PolyForm licence; headless core; named
exceptions; small committable chunks; STATE.md + wiki roadmap kept in
lockstep and pushed per chunk.
