# AXIOMM analysis tools — usage

The `axiomm.analysis` package is a suite of small, independent tools for
turning a converted spectrum-image signal into decomposition, clustering,
per-line intensities, and quantitative composition. Each tool is
**usable on its own** and the tools **compose by hand** (a full pipeline
object and command-line interface are not built yet).

This page shows, for every tool available today, the exact import, a
minimal runnable example, and its real output. Every snippet below was run
as shown.

## Install

```bash
python -m pip install -e ".[analysis,quant]"
```

| Extra | Adds | Needed by |
|-------|------|-----------|
| `analysis` | `scikit-learn` | decomposition (PCA), clustering (GMM) |
| `quant` | `xraylib` | k-factors (theoretical Cliff-Lorimer) |

`numpy` is a core dependency. Optional libraries are imported lazily, so
importing a package never pulls in a library you are not using.

All result objects carry two common fields: `provenance` (an
`AnalysisProvenance` recording the tool, backend, and parameters) and
`diagnostics` (a list of `Diagnostic(severity, code, message)`).

---

## 1. Decomposition — `axiomm.analysis.decomposition`

Reduce a spectrum-image to a few components (PCA). Input is the converter's
neutral `AxiommSignalPayload`; the number of components is yours to choose
(`n_components=None` keeps all).

```python
import numpy as np
from axiomm.io.converters.models import AxisSpec, AxiommSignalPayload
from axiomm.analysis.decomposition import decompose

rng = np.random.default_rng(0)
base = rng.random((2, 8))                # two latent component spectra
coeffs = rng.random((12, 2))             # per-pixel mixing
data = (coeffs @ base).reshape(4, 3, 8)  # (x, y, energy)
axes = (
    AxisSpec("x", "navigation", 4, index_in_array=0),
    AxisSpec("y", "navigation", 3, index_in_array=1),
    AxisSpec("Energy", "signal", 8, units="keV", scale=0.01, offset=0.0, index_in_array=2),
)
payload = AxiommSignalPayload(data=data, axes=axes, signal_kind="signal1d")

result = decompose(payload, backend="pca", n_components=2)
print("factors.shape  =", result.factors.shape)
print("loadings.shape =", result.loadings.shape)
print("explained_variance_ratio =", np.round(result.explained_variance_ratio, 4))
print("nav_shape =", result.nav_shape, " n_components =", result.n_components)
print("provenance =", result.provenance)
```

```text
factors.shape  = (8, 2)
loadings.shape = (12, 2)
explained_variance_ratio = [0.9044 0.0956]
nav_shape = (4, 3)  n_components = 2
provenance = AnalysisProvenance(tool='decomposition', backend='pca', tool_version=None, params={'n_components': 2})
```

**`DecompositionResult`**: `factors` `(n_channels, n_components)` (component
spectra), `loadings` `(n_pixels, n_components)` (per-pixel scores),
`explained_variance_ratio` `(n_components,)`, `nav_shape`, `n_components`.
`loadings` is what clustering consumes next. Persist with
`write_decomposition` / `read_decomposition`.

---

## 2. Clustering — `axiomm.analysis.clustering`

Cluster the decomposition loadings (Gaussian mixture). The clusterer is
pure (features in, labels out); per-cluster **mean spectra** are a separate
step over the source signal. The number of clusters is required.

```python
from axiomm.analysis.clustering import GMMClusterer, GMMConfig, compute_cluster_means

clustering = GMMClusterer(n_clusters=2, config=GMMConfig(random_state=0)).cluster(result)
print("labels    =", clustering.labels)
print("label_map =\n", clustering.label_map)
print("cluster_ids =", clustering.cluster_ids, " masks.shape =", clustering.masks.shape)

means = compute_cluster_means(clustering, payload)
print("means.shape =", means.means.shape, " pixel_counts =", means.pixel_counts)
```

```text
labels    = [0 1 1 0 0 0 0 0 1 0 1 0]
label_map =
 [[0 1 1]
 [0 0 0]
 [0 0 1]
 [0 1 0]]
cluster_ids = [0 1]  masks.shape = (2, 4, 3)
means.shape = (2, 8)  pixel_counts = [8 4]
```

**`ClusteringResult`**: `labels` `(n_pixels,)`, `label_map` (nav-shaped),
`cluster_ids`, `n_clusters`, and a computed `masks` property
`(n_clusters, *nav_shape)`. **`ClusterMeanSpectra`**: `means`
`(n_clusters, n_channels)`, `pixel_counts`, `cluster_ids` — aligned
row-for-row to `cluster_ids`. `GMMClusterer` also accepts
`GMMConfig(covariance_type, random_state, n_init, max_iter, tol,
reg_covar)`.

---

## 3. Peak identification — `axiomm.analysis.peaks`

Measure the **background-subtracted net intensity** of element lines in one
spectrum, given a validated energy axis. Pluggable backends; the default is
flanking-window background subtraction. Reports measurement facts only.

```python
import numpy as np
from axiomm.io.converters.models import AxisSpec
from axiomm.analysis.peaks import NetIntensityMeasurer

spectrum = np.full(1000, 10.0)   # flat background = 10 counts/channel
spectrum[638:643] += 20.0        # a peak of 100 net counts near 6.40 keV
energy_axis = AxisSpec("Energy", "signal", 1000, units="keV", scale=0.01, offset=0.0)

pset = NetIntensityMeasurer().measure(spectrum, energy_axis, {"Fe": 6.40, "Si": 1.74})
print("net_by_label =", pset.net_by_label())
for m in pset.measurements:
    print("  ", m)
```

```text
net_by_label = {'Fe': 100.0, 'Si': 0.0}
   PeakMeasurement(label='Fe', center_kev=6.4, net=100.0, gross=220.0, background=10.0, n_channels=12, in_range=True)
   PeakMeasurement(label='Si', center_kev=1.74, net=0.0, gross=130.0, background=10.0, n_channels=13, in_range=True)
```

**`PeakMeasurementSet`**: `measurements` (a tuple of `PeakMeasurement`:
`label`, `center_kev`, `net`, `gross`, `background`, `n_channels`,
`in_range`) plus `net_by_label()`. Window widths are configurable via
`NetIntensityMeasurer(PeakWindowConfig(half_width_kev, bg_gap_kev,
bg_width_kev))`. A line outside the axis span is flagged `in_range=False`,
not an error. `resolve_energy_axis(axis_spec, n_channels)` validates the
axis (keV/eV only — no silent calibration) and is reused by quantification.

---

## 4. Mineralogy reference — `axiomm.analysis.mineralogy`

The named, versioned science bundle: per-element X-ray/chemical data and a
provenance-tagged mineral endmember library. Oxygen and the halogens Br/I
are excluded from structural cation vectors.

```python
import numpy as np
from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF

print("name =", REF.name, " version =", REF.version, " endmembers =", len(REF.minerals))
print("Fe element =", REF.elements["Fe"])
vecs = dict(REF.mineral_vectors())
order = REF.element_order()
print("Quartz cation vector (nonzero) =",
      {order[i]: round(float(v), 3) for i, v in enumerate(vecs["Quartz"]) if v})

# the preset is also registered in the shared reference registry:
from axiomm.analysis.reference import get_reference
print("via registry:", get_reference("minerals_default_v1").name)
```

```text
name = minerals_default_v1  version = 1  endmembers = 44
Fe element = ElementRef(symbol='Fe', line_energy_kev=6.404, atomic_weight=55.845, atomic_number=26, oxide_form=('FeO', 1, 1), emission_line='Ka')
Quartz cation vector (nonzero) = {'Si': 1.0}
via registry: minerals_default_v1
```

**`MineralogyReference`**: `elements` (`symbol → ElementRef`), `minerals`
(a tuple of `MineralEndmember`), `structural_exclude` (`{"O","Br","I"}`),
`family_display`, plus `element_order()` and `mineral_vectors()`
(normalized, O/Br/I-excluded cation vectors). You can build and register
your own `MineralogyReference`.

---

## 5. k-factors — `axiomm.analysis.quant`

Theoretical Cliff-Lorimer k-factors from xraylib fundamental parameters.
The excitation energy is required (no baked value); the reference element
is configurable (default `Si`).

```python
from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V1 as REF
from axiomm.analysis.quant import compute_k_factors

cations = [REF.elements[s] for s in ["Si", "Fe", "Al", "Ca"]]
kf = compute_k_factors(cations, excitation_kev=18.0, reference="Si")
print("k_factors =", {k: round(v, 3) for k, v in kf.k_factors.items()})
print("provenance.params =", kf.provenance.params)
```

```text
k_factors = {'Si': 1.0, 'Fe': 0.027, 'Al': 1.68, 'Ca': 0.11}
provenance.params = {'method': 'theoretical (xraylib FP, Kissel cross-sections)', 'xraylib_version': '4.3.0', 'excitation_kev': 18.0, 'reference': 'Si'}
```

**`KFactorSet`**: `k_factors` (`symbol → k_{i,ref}`), `sensitivities`,
`reference_element`, `excitation_kev`. If xraylib is not installed,
`compute_k_factors` raises `AnalysisDependencyError`. Persist with
`write_kfactors` / `read_kfactors`.

---

## 6. Cliff-Lorimer quantification — `axiomm.analysis.quant`

Turn net intensities into element and oxide weight percents, using the
k-factors. This composes tools 3–5. Iron is reported as FeO (EDS cannot
resolve its oxidation state); halogens are carried as elements. Oxygen must
be present in `elements` (for the oxide-mass conversion) but is not itself
quantified — the quantified set is exactly the k-factor elements.

```python
import numpy as np
from axiomm.io.converters.models import AxisSpec
from axiomm.analysis.peaks import NetIntensityMeasurer
from axiomm.analysis.quant import quantify

energy_axis = AxisSpec("Energy", "signal", 1000, units="keV", scale=0.01, offset=0.0)
spec = np.full(1000, 5.0)
for center, area in [(1.740, 300.0), (1.486, 200.0), (6.404, 100.0)]:  # Si, Al, Fe
    i = int(round(center / 0.01)); spec[i-2:i+3] += area / 5.0

lines = {s: REF.elements[s].line_energy_kev for s in ["Si", "Al", "Fe", "Ca"]}
peaks_q = NetIntensityMeasurer().measure(spec, energy_axis, lines)
elements_with_O = [REF.elements[s] for s in ["O", "Si", "Fe", "Al", "Ca"]]

qr = quantify(peaks_q, kf, elements_with_O)
print("net_intensities    =", {k: round(v, 1) for k, v in qr.net_intensities.items()})
print("wt_percent_element =", {k: round(v, 1) for k, v in qr.wt_percent_element.items()})
print("wt_percent_oxide   =", {k: round(v, 1) for k, v in qr.wt_percent_oxide.items()})
print("diagnostics        =", [d.code for d in qr.diagnostics])
```

```text
net_intensities    = {'Si': 300.0, 'Fe': 100.0, 'Al': 200.0, 'Ca': 0.0}
wt_percent_element = {'Si': 47.0, 'Fe': 0.4, 'Al': 52.6, 'Ca': 0.0}
wt_percent_oxide   = {'SiO2': 50.1, 'FeO': 0.3, 'Al2O3': 49.6}
diagnostics        = []
```

**`QuantResult`**: `net_intensities`, `wt_percent_element` (metals/cation
basis), `wt_percent_oxide`, `reference_element`. `quantify_cluster_means`
runs `quantify` over a sequence of per-cluster `PeakMeasurementSet`s
(from `peaks.measure_cluster_means`), preserving `cluster_ids` order.
Persist with `write_quant` / `read_quant`.

> These numbers are the raw Cliff-Lorimer result. Deciding which cluster
> means are clean enough to report as quantitative — and flagging elements
> below a reliable count as *below the quantification limit* — is a
> separate reliability step (still in development); a raw cluster mean is
> not automatically a validated phase composition.

---

## Composing the tools

The examples above already chain: a payload flows through
`decompose` → `cluster` → `compute_cluster_means`, and a spectrum flows
through `measure` → `quantify` with `compute_k_factors`. Because every tool
reads and writes plain typed objects (and offers file adapters), you wire
them together in whatever order your analysis needs — each one remains
runnable and testable on its own.
