"""Example C — the per-stage walkthrough, for a researcher changing one choice.

Shows the connected sequence of **public** stages with named intermediates, and what
each stage carries forward, in the plain-English vocabulary:

  * ``method=`` chooses the algorithm at each stage (``decompose``/``cluster``);
  * ``beam_energy="13.55 keV"`` is the one energy word (``compute_k_factors`` accepts it
    alongside the legacy ``excitation_kev``);
  * ``reference_element="Si"`` is the normalising element and ``library=`` the mineral
    set — no more one word meaning two things.

(The measurable cations and the oxygen entry are still derived from the library by hand;
the facade hides that, and unifying it further is future work.) Every name here also has
a canonical alias that still works.

Run on the synthetic fixture:

    python examples/api/example_c_per_stage.py
"""
from __future__ import annotations

from axiomm import (
    assess_reliability,
    cluster,
    compute_cluster_means,
    compute_k_factors,
    decompose,
    get_reference,
    match_minerals,
    measure_peaks,
    quantify,
)


def walkthrough(payload, *, n_components=15, n_clusters=7, beam_energy="13.55 keV"):
    library = get_reference("minerals_default_v2")          # the mineral library (data)

    # 1-2. reduce the spectra, then group pixels (GMM needs the count)
    reduced = decompose(payload, method="pca", n_components=n_components)
    clustering = cluster(reduced, method="gmm", n_clusters=n_clusters)
    # 3. average each cluster's spectrum
    means = compute_cluster_means(clustering, payload)

    # the elements measurable in this energy range, derived from the library by hand
    signal_axis = next(a for a in payload.axes if a.role == "signal")
    emin = signal_axis.offset
    emax = signal_axis.offset + signal_axis.scale * (signal_axis.size - 1)
    cations = list(library.cations_in_range(emin, emax))
    cation_refs = library.element_refs(cations)

    # 4. measure peaks (lines derived from the library); 5. theoretical k-factors
    peaks = measure_peaks(means, signal_axis, library)
    kfactors = compute_k_factors(cation_refs, beam_energy=beam_energy, reference_element="Si")

    # 6. quantify (oxygen added by hand, as the facade does internally)
    quant_elements = cation_refs + ([library.elements["O"]] if "O" in library.elements else [])
    quant = quantify(peaks, kfactors, quant_elements)
    # 7. reliability; 8. mineral match (library = the mineral set)
    reliability = assess_reliability(quant, means)
    minerals = match_minerals(quant, library=library, reliabilities=reliability)
    return minerals


if __name__ == "__main__":
    from examples.api._fixture import synthetic_payload

    minerals = walkthrough(synthetic_payload())
    print(f"{len(minerals)} clusters matched")
    for m in minerals:
        best = m.best()
        print(f"  cluster {m.cluster_id}: "
              + (f"{best.name} ({best.rank_score:.2f})" if best else "no match"))
