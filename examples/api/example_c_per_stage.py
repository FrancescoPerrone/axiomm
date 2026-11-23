"""Example C — the per-stage walkthrough, for a researcher changing one choice.

Shows the connected sequence of **public** stages with named intermediates, and what
each stage carries forward. This is deliberately the current API, so the naming
inconsistencies the ergonomics pass must fix are visible in plain sight:

  * the acquisition energy is ``beam_energy_kev`` on the facade but ``excitation_kev``
    here (``compute_k_factors``) — the same quantity, two words;
  * ``reference="Si"`` in ``compute_k_factors`` is the reference *element*, while
    ``match_minerals(quant, library)`` takes the mineral *library* — ``reference`` means
    two different things;
  * the measurable cations and the oxygen entry must be derived from the library and
    threaded by hand (the facade hides this).

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


def walkthrough(payload, *, n_components=15, n_clusters=7, beam_energy_kev=13.55):
    library = get_reference("minerals_default_v2")          # the mineral library (data)

    # 1-2. reduce the spectra, then group pixels (GMM needs the count)
    reduced = decompose(payload, backend="pca", n_components=n_components)
    clustering = cluster(reduced, backend="gmm", n_clusters=n_clusters)
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
    kfactors = compute_k_factors(cation_refs, excitation_kev=beam_energy_kev, reference="Si")

    # 6. quantify (oxygen added by hand, as the facade does internally)
    quant_elements = cation_refs + ([library.elements["O"]] if "O" in library.elements else [])
    quant = quantify(peaks, kfactors, quant_elements)
    # 7. reliability; 8. mineral match (reference here is the LIBRARY, not an element)
    reliability = assess_reliability(quant, means)
    minerals = match_minerals(quant, library, reliabilities=reliability)
    return minerals


if __name__ == "__main__":
    from examples.api._fixture import synthetic_payload

    minerals = walkthrough(synthetic_payload())
    print(f"{len(minerals)} clusters matched")
    for m in minerals:
        best = m.best()
        print(f"  cluster {m.cluster_id}: "
              + (f"{best.name} ({best.rank_score:.2f})" if best else "no match"))
