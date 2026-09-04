"""AXIOMM end-to-end proof of concept: spectra -> phase map.

Runs the whole stage-two analysis pipeline on a small synthetic X-ray map and
renders the target output — a **mineral phase map** — beside the intermediate
steps, so the visual result AXIOMM is built for is on show.

**About the data.** Real hyperspectral geology maps are large and not
pip-installable, so this demo *synthesises* a map from **open reference
mineral chemistry**: four ground-truth domains whose spectra are generated
from the basis-audited ``MINERALOGY_DEFAULT_V2`` endmembers (idealised
formulae + GeoReM/EPMA-derived compositions). The spatial arrangement is
synthetic; the chemistry is real and open. Peak areas are placed as
``sensitivity_i * mass_fraction_i`` so the *actual* Cliff-Lorimer quantifier
recovers the input chemistry — i.e. the full real pipeline runs, it is only
the input image that is simulated. This is a proof of concept, not measured
data; **standards validation remains mandatory** before any
quantitative-accuracy or validated mineral-identification claim.

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

# --- experiment set-up -----------------------------------------------------
# Four distinctive, multi-element ground-truth phases (all in V2's open chemistry).
GROUND_TRUTH = ["Forsterite", "Diopside", "Orthoclase", "Apatite"]
# A curated subset of the open V2 endmembers for an unambiguous demo; the full
# MINERALOGY_DEFAULT_V2 (44 endmembers, incl. broad glasses) is the real default.
CURATED = ["Quartz", "Forsterite", "Fayalite", "Diopside", "Hedenbergite",
           "Orthoclase", "Albite", "Anorthite", "Apatite", "Ilmenite", "Magnetite"]
MEASURED = ["F", "Na", "Mg", "Al", "Si", "P", "K", "Ca", "Ti", "Fe"]
REFERENCE_EL = "Si"
EXCITATION_KEV = 15.0
SCALE_KEV = 0.01
N_CHANNELS = 800                                        # 0 .. 8 keV
COUNTS = 6.0e4                                          # per-pixel intensity scale
NAV = (70, 90)                                          # y, x pixels
SEED = 7


def _elemental_mass_fractions(mineral, elements):
    """Cation elemental mass fractions of an endmember over the measured set."""
    moles = {e: float(mineral.composition.get(e, 0.0)) for e in MEASURED}
    mass = {e: moles[e] * elements[e].atomic_weight for e in MEASURED}
    total = sum(mass.values())
    return {e: (mass[e] / total if total > 0 else 0.0) for e in MEASURED}


def _domain_map(nav):
    """Four rectangular domains (0..3), a diagonal split for visual interest."""
    ny, nx = nav
    dom = np.zeros(nav, dtype=int)
    dom[: ny // 2, : nx // 2] = 0          # top-left
    dom[: ny // 2, nx // 2:] = 1           # top-right
    dom[ny // 2:, : nx // 2] = 2           # bottom-left
    dom[ny // 2:, nx // 2:] = 3            # bottom-right
    # a rounded inclusion of domain 3 inside domain 0 (a phase blob)
    yy, xx = np.ogrid[:ny, :nx]
    blob = (yy - ny // 4) ** 2 + (xx - nx // 4) ** 2 < (min(ny, nx) // 8) ** 2
    dom[blob] = 3
    return dom


def _synthesize(dom, energy, sensitivities, elements, rng):
    """Build an (y, x, E) count cube from per-domain mineral chemistry."""
    ny, nx = dom.shape
    cube = np.full((ny, nx, energy.size), 3.0, dtype=float)   # small flat background
    sig = 0.05                                                 # peak width (keV)
    # per-domain template spectrum
    templates = []
    for name in GROUND_TRUTH:
        mineral = next(m for m in REF.minerals if m.name == name)
        m_frac = _elemental_mass_fractions(mineral, elements)
        spec = np.zeros(energy.size)
        for el in MEASURED:
            area = sensitivities[el] * m_frac[el]
            if area <= 0:
                continue
            centre = elements[el].line_energy_kev
            spec += area * np.exp(-((energy - centre) ** 2) / (2 * sig ** 2))
        s = spec.sum()
        templates.append(spec / s * COUNTS if s > 0 else spec)
    for d in range(len(GROUND_TRUTH)):
        mask = dom == d
        base = templates[d]
        n = int(np.count_nonzero(mask))
        # Poisson-like shot noise per pixel
        noisy = rng.poisson(np.clip(np.broadcast_to(base, (n, energy.size)), 0, None))
        cube[mask] = noisy + 3.0
    return cube


def _element_map(cube, energy, element_ref):
    """Quick per-pixel integrated intensity in a window around a line."""
    idx = int((element_ref.line_energy_kev - float(energy[0])) / SCALE_KEV + 0.5)
    lo, hi = max(0, idx - 4), min(energy.size, idx + 5)
    return cube[..., lo:hi].sum(axis=2)


def run():
    rng = np.random.default_rng(SEED)
    energy = np.arange(N_CHANNELS) * SCALE_KEV
    elements = REF.elements
    k = compute_k_factors([elements[e] for e in MEASURED],
                          excitation_kev=EXCITATION_KEV, reference=REFERENCE_EL)
    sensitivities = k.sensitivities

    dom = _domain_map(NAV)
    cube = _synthesize(dom, energy, sensitivities, elements, rng)

    # --- the real AXIOMM pipeline -----------------------------------------
    axes = (
        AxisSpec("y", "navigation", NAV[0], index_in_array=0),
        AxisSpec("x", "navigation", NAV[1], index_in_array=1),
        AxisSpec("Energy", "signal", N_CHANNELS, units="keV",
                 scale=SCALE_KEV, offset=0.0, index_in_array=2),
    )
    payload = AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")

    decomp = decompose(payload, backend="pca", n_components=6)
    clustering = GMMClusterer(n_clusters=4, config=GMMConfig(random_state=SEED)).cluster(decomp)
    means = compute_cluster_means(clustering, payload)

    energy_axis = axes[2]
    lines = {e: elements[e].line_energy_kev for e in MEASURED}
    peak_sets = measure_cluster_means(means, energy_axis, lines, measurer=NetIntensityMeasurer())
    # oxide conversion needs O in the element list (O is not a k-factor element)
    quant_elements = [elements[e] for e in MEASURED] + [elements["O"]]
    quant = quantify_cluster_means(peak_sets, k, quant_elements, reference_name=REF.name)
    reports = assess_cluster_reliability(list(quant), means)
    demo_ref = MineralogyReference(
        name="demo_curated_v1", version="1",
        description="Curated open-chemistry subset of MINERALOGY_DEFAULT_V2 for the demo.",
        elements=REF.elements,
        minerals=tuple(m for m in REF.minerals if m.name in CURATED),
        structural_exclude=REF.structural_exclude, family_display=REF.family_display)
    demo_ref.validate(strict=True)
    matches = match_clusters(list(quant), demo_ref, reliabilities=list(reports),
                             config=MatchConfig(top_k=3))

    best_by_cid = {mres.cluster_id: (mres.best().name if mres.best() else "unresolved")
                   for mres in matches}
    print("Cluster -> best-match mineral (score):")
    for mres in matches:
        top = mres.best()
        label = f"{top.name} ({top.score:.3f})" if top else "unresolved"
        print(f"  cluster {mres.cluster_id}: {label}  [{mres.input_reliability}]")

    _plot(dom, cube, energy, clustering, means, peak_sets, best_by_cid, elements)
    return best_by_cid


def _plot(dom, cube, energy, clustering, means, peak_sets, best_by_cid, elements):
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch

    label_map = np.asarray(clustering.label_map)
    # a stable colour per mineral name that appears
    phase_names = sorted({best_by_cid.get(int(c), "unresolved") for c in clustering.cluster_ids}
                         | {GROUND_TRUTH[d] for d in range(len(GROUND_TRUTH))})
    palette = plt.get_cmap("tab10")
    colour = {name: palette(i % 10) for i, name in enumerate(phase_names)}
    colour["unresolved"] = (0.6, 0.6, 0.6, 1.0)

    def phase_rgb(name_grid):
        rgb = np.zeros((*name_grid.shape, 4))
        for name in np.unique(name_grid):
            rgb[name_grid == name] = colour[name]
        return rgb

    gt_names = np.array(GROUND_TRUTH, dtype=object)[dom]
    pred_names = np.vectorize(lambda c: best_by_cid.get(int(c), "unresolved"))(label_map)

    fig, ax = plt.subplots(2, 3, figsize=(15, 9))
    fig.suptitle("AXIOMM — synthetic proof of concept: spectra → mineral phase map\n"
                 "(chemistry from open MINERALOGY_DEFAULT_V2; spatial map simulated)",
                 fontsize=13)

    ax[0, 0].imshow(phase_rgb(gt_names))
    ax[0, 0].set_title("Ground-truth phases (input)")
    ax[0, 1].imshow(_element_map(cube, energy, elements["Si"]), cmap="viridis")
    ax[0, 1].set_title("Si Ka intensity map")
    ax[0, 2].imshow(_element_map(cube, energy, elements["Ca"]), cmap="magma")
    ax[0, 2].set_title("Ca Ka intensity map")

    ncl = len(clustering.cluster_ids)
    ax[1, 0].imshow(label_map, cmap=ListedColormap(palette(np.arange(ncl) % 10)))
    ax[1, 0].set_title(f"GMM cluster map (k={ncl})")

    ax[1, 1].imshow(phase_rgb(pred_names))
    ax[1, 1].set_title("AXIOMM phase map (matched)")
    ax[1, 1].legend(handles=[Patch(facecolor=colour[n], label=n)
                             for n in phase_names if (pred_names == n).any()],
                    loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=2, fontsize=8)

    # a representative cluster-mean spectrum with labelled peaks
    ci = 0
    spec = np.asarray(means.means)[ci]
    ax[1, 2].plot(energy, spec, lw=0.8, color="#222")
    ax[1, 2].set_title(f"Cluster {int(means.cluster_ids[ci])} mean spectrum "
                       f"→ {best_by_cid.get(int(means.cluster_ids[ci]), '?')}")
    ax[1, 2].set_xlabel("Energy (keV)")
    ax[1, 2].set_ylabel("counts")
    for m in peak_sets[ci].measurements:
        if m.net > 0 and m.in_range:
            ax[1, 2].annotate(m.label, (m.center_kev, spec.max() * 0.9),
                              fontsize=8, ha="center", color="#b00")

    for a in (ax[0, 0], ax[0, 1], ax[0, 2], ax[1, 0], ax[1, 1]):
        a.set_xticks([])
        a.set_yticks([])

    out = Path(__file__).parent / "output"
    out.mkdir(exist_ok=True)
    dest = out / "axiomm_phase_map_demo.png"
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(dest, dpi=130)
    print(f"\nSaved figure -> {dest}")


if __name__ == "__main__":
    run()
