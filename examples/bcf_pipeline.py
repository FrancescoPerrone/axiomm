"""AXIOMM real-data pipeline run on a STEM-EDS Bruker .bcf spectrum image.

OPT-IN, local-file. Runs the genuine AXIOMM analysis sequence on real measured
data via the pluggable ``BrukerBCFReader``:

    read (.bcf) -> AxiommSignalPayload
      -> decompose (PCA)
      -> cluster (GMM)
      -> cluster mean spectra
      -> peak net intensities

This is the very sequence the forthcoming ``axiomm.pipeline`` facade will
orchestrate as one object, and that a UX layer will eventually drive — the core
stays headless. Identifiers, configuration, and provenance are preserved across
every transition.

**Quantification and mineral matching are deliberately NOT run.** This is a
STEM materials-science specimen (a REBCO-type thin film) whose chemistry lies
outside AXIOMM's silicate/oxide mineral reference and outside its SEM/bulk
Cliff-Lorimer regime, so the honest outcome is abstention at the reference-scope
level — recorded as an explicit diagnostic, not a forced identification.

Scope: real STEM-EDS interoperability + pipeline-execution evidence. NOT SEM,
NOT mineral ground truth, NOT standards-based quantification, NOT accuracy.

Licence: source is GPL-3.0. The binary and all outputs stay OUTSIDE git.

Usage:
    AXIOMM_REALDATA_BCF=/abs/path/EDS_dataset.bcf python examples/bcf_pipeline.py
    python examples/bcf_pipeline.py /abs/path/EDS_dataset.bcf [OUT_DIR]
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

import numpy as np

from axiomm import __version__ as _AXIOMM_VERSION
from axiomm.analysis.clustering import GMMClusterer, GMMConfig
from axiomm.analysis.clustering.means import compute_cluster_means
from axiomm.analysis.decomposition import decompose
from axiomm.analysis.peaks import NetIntensityMeasurer, measure_cluster_means
from axiomm.io.converters.readers.bruker_bcf import BrukerBCFReader

# common EDS lines (keV) for peak measurement — facts, not identifications
_EDS_LINES = {
    "O_Ka": 0.525, "F_Ka": 0.677, "Cu_La": 0.930, "Y_La": 1.922, "Sr_La": 1.806,
    "Ba_La": 4.466, "Ti_Ka": 4.508, "Fe_Ka": 6.404, "Cu_Ka": 8.048,
}


def run_pipeline(bcf_path, *, n_components: int = 8, n_clusters: int = 6,
                 seed: int = 0, plot: bool = True, out_dir=None) -> dict:
    """Read a .bcf and run decompose → cluster → cluster spectra → peaks."""
    bcf_path = Path(bcf_path)
    payload = BrukerBCFReader().read(bcf_path, lazy=False)
    sig_ax = next(a for a in payload.axes if a.role == "signal")
    lines = {k: v for k, v in _EDS_LINES.items()
             if sig_ax.offset <= v <= sig_ax.offset + sig_ax.scale * sig_ax.size}

    decomp = decompose(payload, backend="pca", n_components=n_components)
    clustering = GMMClusterer(n_clusters=n_clusters,
                              config=GMMConfig(random_state=seed)).cluster(decomp)
    means = compute_cluster_means(clustering, payload)
    peaks = measure_cluster_means(means, sig_ax, lines, measurer=NetIntensityMeasurer())

    report = {
        "dataset": {"local_file": str(bcf_path),
                    "sha256": payload.metadata["AXIOMM"]["source_sha256"]},
        "reader": payload.metadata["AXIOMM"]["reader"],
        "tools": {"axiomm": _AXIOMM_VERSION, "numpy": np.__version__},
        "utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "config": {"decompose": "pca", "n_components": n_components,
                   "n_clusters": n_clusters, "seed": seed, "eds_lines_keV": lines},
        "shape": list(np.asarray(payload.data).shape),
        "explained_variance_ratio": [float(x) for x in decomp.explained_variance_ratio[:n_components]],
        "clusters": [
            {"cluster_id": int(c), "pixels": int(np.sum(np.asarray(clustering.labels) == c)),
             "peak_nets": {m.label: float(m.net) for m in ps.measurements}}
            for c, ps in zip(clustering.cluster_ids, peaks, strict=True)
        ],
        "quantification_and_matching": (
            "NOT RUN — out of reference scope: STEM materials-science chemistry "
            "outside AXIOMM's silicate/oxide reference and SEM/bulk Cliff-Lorimer "
            "regime. Honest outcome is abstention at the reference-scope level."),
        "scope": ("real STEM-EDS pipeline-execution evidence; NOT SEM, NOT mineral "
                  "ground truth, NOT standards-based quantification, NOT accuracy."),
    }

    out_dir = Path(out_dir) if out_dir else bcf_path.parent
    (out_dir / f"{bcf_path.stem}.pipeline.json").write_text(json.dumps(report, indent=2))
    if plot:
        _plot(payload, clustering, means, peaks, lines, bcf_path, out_dir)
    return {"payload": payload, "clustering": clustering, "means": means,
            "peaks": peaks, "report": report}


def _plot(payload, clustering, means, peaks, lines, bcf_path, out_dir) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    label_map = np.asarray(clustering.label_map)
    ncl = len(clustering.cluster_ids)
    sig_ax = next(a for a in payload.axes if a.role == "signal")
    energy = sig_ax.offset + sig_ax.scale * np.arange(sig_ax.size)

    fig, ax = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("AXIOMM real-data pipeline — STEM-EDS spectrum image\n"
                 "(read → PCA → GMM → cluster spectra → peaks; quant/matching "
                 "abstained: chemistry out of reference scope)", fontsize=11)
    im = ax[0].imshow(label_map, cmap="tab10")
    ax[0].set_title(f"GMM cluster map (k={ncl})")
    ax[0].set_xticks([])
    ax[0].set_yticks([])
    fig.colorbar(im, ax=ax[0], fraction=0.046, ticks=range(ncl))
    m = np.asarray(means.means)
    for i, cid in enumerate(means.cluster_ids):
        ax[1].plot(energy, m[i], lw=0.7, label=f"cluster {int(cid)}")
    for e in lines.values():
        ax[1].axvline(e, color="#ccc", lw=0.5, ls="--")
    ax[1].set_xlim(0, min(12, energy[-1]))
    ax[1].set_xlabel("Energy (keV)")
    ax[1].set_ylabel("mean counts")
    ax[1].set_title("Cluster mean spectra")
    ax[1].legend(fontsize=7, ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    dest = out_dir / f"{bcf_path.stem}.pipeline.png"
    fig.savefig(dest, dpi=120)
    plt.close(fig)
    print(f"  figure -> {dest}")


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else os.environ.get("AXIOMM_REALDATA_BCF")
    if not path or not Path(path).is_file():
        print("Provide a .bcf path (arg) or set AXIOMM_REALDATA_BCF.", file=sys.stderr)
        return 2
    out_dir = Path(argv[2]) if len(argv) > 2 else Path(path).parent
    try:
        result = run_pipeline(path, out_dir=out_dir)
    except ImportError as exc:
        print(f"Reader/backends unavailable (install [all,quant]): {exc}", file=sys.stderr)
        return 3
    rep = result["report"]
    print(f"Ran AXIOMM pipeline on {Path(path).name}: shape {rep['shape']}, "
          f"{len(rep['clusters'])} clusters")
    print(f"  {rep['quantification_and_matching']}")
    print(f"  report -> {out_dir / (Path(path).stem + '.pipeline.json')}  (outside git)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
