"""AXIOMM synthetic self-consistency integration demo: spectra -> phase map.

Runs the whole stage-two analysis pipeline on a **synthetic** X-ray map with a
geologically shaped texture and renders a mineral phase map beside the
intermediate steps. Its role is a **deterministic round-trip integration
demo** — it exercises ingestion → decomposition → clustering → cluster spectra
→ peaks → quantification → reliability → matching end to end and checks the
pieces fit together. It is **not** empirical validation and says nothing about
quantitative accuracy.

**Self-consistency caveat.** The observations here are *generated* from the
same reference compositions and fluorescence sensitivities that the quantifier
and matcher later use, so recovering the input phases demonstrates internal
consistency, not measurement accuracy. The reference *compositions* are
scientifically grounded (idealised formulae + GeoReM/EPMA-derived standards in
``MINERALOGY_DEFAULT_V2`), but the *spectra generated from them are synthetic
observations*, not real chemistry. Per-pixel peak areas are placed as
``sensitivity_i * mass_fraction_i``, which is exactly why the quantifier
recovers the inputs. For real measured data see the separate NIST real-data
demonstration (``examples/nist_pgm_realdata.py``). **Standards validation
remains mandatory** before any quantitative-accuracy or validated
mineral-identification claim; the demo makes no such claim.

**The scene** is a petrographic texture, not a test pattern: interlocking
mineral grains (a Voronoi mosaic at a realistic modal abundance), a
cross-cutting apatite vein, and a compositionally zoned olivine phenocryst
(forsterite core grading to a fayalitic rim).

Run:  python examples/phase_map_demo.py   (needs the [all] / [viz] + [quant] extras)
Output: examples/output/axiomm_phase_map_demo.png
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from axiomm.analysis.clustering import GMMClusterer, GMMConfig
from axiomm.analysis.clustering.means import compute_cluster_means
from axiomm.analysis.decomposition import decompose
from axiomm.analysis.mineralogy import MINERALOGY_DEFAULT_V2 as REF
from axiomm.analysis.mineralogy.match import MatchConfig, match_clusters
from axiomm.analysis.mineralogy.reference import MineralogyReference
from axiomm.analysis.peaks import NetIntensityMeasurer, measure_cluster_means
from axiomm.analysis.quant import (
    assess_cluster_reliability,
    compute_k_factors,
    quantify_cluster_means,
)
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec

# --- scene set-up ----------------------------------------------------------
# Grain phases + their modal abundance (a plausible alkaline mafic rock). All
# are multi-element: single-cation phases (quartz, magnetite) can't be pinned by
# cation ratios on one line and would flag as low-evidence by design.
MODAL = {
    "Albite": 0.28, "Orthoclase": 0.18, "Diopside": 0.18, "Forsterite": 0.14,
    "Ilmenite": 0.12, "Apatite": 0.10,
}
# Curated open-chemistry reference for the demo (superset of the scene phases,
# incl. Fayalite so the zoned rim matches a distinct olivine composition).
CURATED = [*MODAL, "Fayalite", "Hedenbergite", "Anorthite"]
MEASURED = ["F", "Na", "Mg", "Al", "Si", "P", "K", "Ca", "Ti", "Fe"]
REFERENCE_EL = "Si"
EXCITATION_KEV = 15.0
SCALE_KEV = 0.01
N_CHANNELS = 800                         # 0 .. 8 keV
COUNTS = 6.0e4                           # per-pixel intensity scale
NAV = (120, 150)                         # y, x pixels
N_GRAINS = 55
N_CLUSTERS = 8
SEED = 11


def _mass_fractions(mineral, elements):
    moles = {e: float(mineral.composition.get(e, 0.0)) for e in MEASURED}
    mass = {e: moles[e] * elements[e].atomic_weight for e in MEASURED}
    total = sum(mass.values())
    return {e: (mass[e] / total if total > 0 else 0.0) for e in MEASURED}


def _template(mass_frac, energy, sensitivities, elements):
    """A normalised template spectrum for a set of elemental mass fractions."""
    sig = 0.05
    spec = np.zeros(energy.size)
    for el in MEASURED:
        area = sensitivities[el] * mass_frac[el]
        if area <= 0:
            continue
        spec += area * np.exp(-((energy - elements[el].line_energy_kev) ** 2)
                              / (2 * sig ** 2))
    s = spec.sum()
    return spec / s * COUNTS if s > 0 else spec


def _voronoi_grains(nav, n_grains, rng):
    """Assign each pixel to the nearest of n random seeds (interlocking grains)."""
    ny, nx = nav
    sy = rng.integers(0, ny, size=n_grains)
    sx = rng.integers(0, nx, size=n_grains)
    yy, xx = np.mgrid[:ny, :nx]
    d = (yy[..., None] - sy) ** 2 + (xx[..., None] - sx) ** 2
    return np.argmin(d, axis=2)          # grain id per pixel


def build_scene(energy, sensitivities, elements, rng):
    """Return (spectral cube, ground-truth phase-name grid)."""
    ny, nx = NAV
    grain = _voronoi_grains(NAV, N_GRAINS, rng)

    # assign a mineral to each grain by modal abundance
    names, probs = zip(*MODAL.items(), strict=True)
    grain_mineral = rng.choice(names, size=N_GRAINS, p=np.array(probs) / sum(probs))
    phase = np.empty(NAV, dtype=object)
    for g in range(N_GRAINS):
        phase[grain == g] = grain_mineral[g]

    templates = {name: _template(_mass_fractions(next(m for m in REF.minerals
                 if m.name == name), elements), energy, sensitivities, elements)
                 for name in set(CURATED)}

    cube = np.zeros((ny, nx, energy.size), dtype=float)
    for name in np.unique(phase):
        cube[phase == name] = templates[name]

    # --- a cross-cutting apatite vein (sinuous band) ----------------------
    xs = np.arange(nx)
    vein_y = (ny * 0.5 + 0.16 * ny * np.sin(xs / nx * 3 * np.pi)
              + 0.10 * ny * np.sin(xs / nx * 7 * np.pi)).astype(int)
    for x in xs:
        y0, y1 = max(0, vein_y[x] - 2), min(ny, vein_y[x] + 2)
        cube[y0:y1, x] = templates["Apatite"]
        phase[y0:y1, x] = "Apatite"

    # --- a zoned olivine phenocryst: forsterite core, fayalitic rim -------
    cy, cx, R = int(ny * 0.70), int(nx * 0.28), int(min(ny, nx) * 0.26)
    yy, xx = np.mgrid[:ny, :nx]
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    core = r < 0.58 * R
    rim = (r >= 0.58 * R) & (r < R)
    cube[core] = templates["Forsterite"]
    phase[core] = "Forsterite"
    cube[rim] = templates["Fayalite"]
    phase[rim] = "Fayalite"

    # Poisson shot noise + small background
    cube = rng.poisson(np.clip(cube, 0, None)).astype(float) + 3.0
    return cube, phase


def run(*, save: bool = True, verbose: bool = True):
    """Run the synthetic self-consistency pipeline; optionally render the figure.

    Returns a dict with ``best`` (cluster_id -> matched mineral or 'unresolved'),
    ``matches`` and ``means`` so it can be driven as a deterministic integration
    test (``save=False`` skips plotting and needs no matplotlib).
    """
    rng = np.random.default_rng(SEED)
    energy = np.arange(N_CHANNELS) * SCALE_KEV
    elements = REF.elements
    k = compute_k_factors([elements[e] for e in MEASURED],
                          excitation_kev=EXCITATION_KEV, reference=REFERENCE_EL)

    cube, gt_phase = build_scene(energy, k.sensitivities, elements, rng)

    # --- the AXIOMM analysis pipeline (on synthetic observations) ---------
    axes = (
        AxisSpec("y", "navigation", NAV[0], index_in_array=0),
        AxisSpec("x", "navigation", NAV[1], index_in_array=1),
        AxisSpec("Energy", "signal", N_CHANNELS, units="keV",
                 scale=SCALE_KEV, offset=0.0, index_in_array=2),
    )
    payload = AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")

    decomp = decompose(payload, backend="pca", n_components=8)
    clustering = GMMClusterer(n_clusters=N_CLUSTERS,
                              config=GMMConfig(random_state=SEED)).cluster(decomp)
    means = compute_cluster_means(clustering, payload)

    lines = {e: elements[e].line_energy_kev for e in MEASURED}
    peak_sets = measure_cluster_means(means, axes[2], lines, measurer=NetIntensityMeasurer())
    quant_elements = [elements[e] for e in MEASURED] + [elements["O"]]
    quant = quantify_cluster_means(peak_sets, k, quant_elements, reference_name=REF.name)
    reports = assess_cluster_reliability(list(quant), means)

    demo_ref = MineralogyReference(
        name="demo_curated_v1", version="1",
        description="Curated open-chemistry subset of MINERALOGY_DEFAULT_V2.",
        elements=REF.elements,
        minerals=tuple(m for m in REF.minerals if m.name in CURATED),
        structural_exclude=REF.structural_exclude, family_display=REF.family_display)
    demo_ref.validate(strict=True)
    matches = match_clusters(list(quant), demo_ref, reliabilities=list(reports),
                             config=MatchConfig(top_k=3))

    best = {mres.cluster_id: (mres.best().name if mres.best() else "unresolved")
            for mres in matches}
    if verbose:
        print("Cluster -> best-match mineral (score):")
        for mres in matches:
            top = mres.best()
            print(f"  cluster {mres.cluster_id}: "
                  f"{top.name+f' ({top.score:.3f})' if top else 'unresolved'}")

    if save:
        _plot(cube, energy, gt_phase, clustering, means, best, elements)
    return {"best": best, "matches": matches, "means": means}


def _plot(cube, energy, gt_phase, clustering, means, best, elements):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    label_map = np.asarray(clustering.label_map)
    pred = np.vectorize(lambda c: best.get(int(c), "unresolved"))(label_map)
    names = sorted(set(np.unique(gt_phase)) | set(np.unique(pred)))
    pal = plt.get_cmap("tab20")
    colour = {n: pal(i % 20) for i, n in enumerate(names)}
    colour["unresolved"] = (0.75, 0.75, 0.75, 1.0)

    def rgb(grid):
        out = np.zeros((*grid.shape, 4))
        for n in np.unique(grid):
            out[grid == n] = colour[n]
        return out

    def emap(el):
        i = int((elements[el].line_energy_kev - energy[0]) / SCALE_KEV + 0.5)
        m = cube[..., max(0, i - 4):i + 5].sum(2)
        return m / m.max() if m.max() else m

    fig, ax = plt.subplots(2, 3, figsize=(16, 9.5))
    fig.suptitle("AXIOMM — synthetic self-consistency integration demo: spectra → phase map\n"
                 "(petrographic texture; chemistry from open MINERALOGY_DEFAULT_V2, "
                 "spatial map simulated)", fontsize=13)

    comp = np.dstack([emap("Fe"), emap("Ca"), emap("Si")])
    ax[0, 0].imshow(comp)
    ax[0, 0].set_title("Element composite  (R=Fe  G=Ca  B=Si)")
    ax[0, 1].imshow(rgb(gt_phase))
    ax[0, 1].set_title("Ground-truth phases (input)")
    ax[0, 2].imshow(label_map, cmap="tab20")
    ax[0, 2].set_title(f"GMM cluster map (k={len(clustering.cluster_ids)})")

    ax[1, 0].imshow(rgb(pred))
    ax[1, 0].set_title("AXIOMM phase map (matched)")
    present = [n for n in names if (pred == n).any()]
    ax[1, 0].legend(handles=[Patch(facecolor=colour[n], label=n) for n in present],
                    loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=3, fontsize=8)

    # matched modal mineralogy (area fraction) — a self-consistency summary,
    # NOT a standards-validated quantitative measurement
    frac = {n: float((pred == n).mean()) for n in present}
    order = sorted(frac, key=frac.get, reverse=True)
    ax[1, 1].barh(range(len(order)), [frac[n] * 100 for n in order],
                  color=[colour[n] for n in order])
    ax[1, 1].set_yticks(range(len(order)))
    ax[1, 1].set_yticklabels(order, fontsize=8)
    ax[1, 1].invert_yaxis()
    ax[1, 1].set_xlabel("area %")
    ax[1, 1].set_title("Modal area fraction (self-consistency, not validated)")

    # overlay two cluster-mean spectra that matched different olivines (zoning)
    ax[1, 2].set_title("Cluster mean spectra (olivine zoning)")
    picks = [(cid, best[cid]) for cid in best if best[cid] in ("Forsterite", "Fayalite")][:2]
    if len(picks) < 2:
        picks = [(int(c), best[int(c)]) for c in list(clustering.cluster_ids)[:2]]
    cid_to_row = {int(c): i for i, c in enumerate(means.cluster_ids)}
    for cid, name in picks:
        spec = np.asarray(means.means)[cid_to_row[int(cid)]]
        ax[1, 2].plot(energy, spec, lw=0.9, label=f"cluster {cid} → {name}")
    for el in ("Mg", "Si", "Fe"):
        ax[1, 2].axvline(elements[el].line_energy_kev, color="#bbb", lw=0.6, ls="--")
        ax[1, 2].text(elements[el].line_energy_kev, 0, el, fontsize=7, color="#666")
    ax[1, 2].set_xlim(0, 8)
    ax[1, 2].set_xlabel("Energy (keV)")
    ax[1, 2].set_ylabel("counts")
    ax[1, 2].legend(fontsize=8)

    for a in (ax[0, 0], ax[0, 1], ax[0, 2], ax[1, 0]):
        a.set_xticks([])
        a.set_yticks([])

    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)
    dest = out / "axiomm_phase_map_demo.png"
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(dest, dpi=130)
    print(f"\nSaved figure -> {dest}")


if __name__ == "__main__":
    run()
