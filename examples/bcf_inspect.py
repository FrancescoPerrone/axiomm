"""AXIOMM real-data inspection: a STEM-EDS Bruker ``.bcf`` spectrum image.

OPT-IN, local-file, inspect-only. This is the *evidence-gathering* step for
AXIOMM's real-data work: it loads a real STEM-EDS spectrum image at the edge
(RosettaSciIO/HyperSpy — never a core AXIOMM dependency), records the facts and
provenance verbatim, and renders an AXIOMM-relevant quick-look (the summed EDS
spectrum and the total-counts navigation map) so a real measured spectrum image
is visibly on show. It does **not** implement a reader, build AXIOMM's payload,
run the pipeline, or make any quantitative/mineralogical claim.

Scientific scope: a **real STEM-EDS spectrum image** (thin TEM specimen, 200 keV
— low bremsstrahlung), materials science (a REBCO-type thin film), NOT SEM, NOT
mineral ground truth, NOT standards-based quantification. AXIOMM's silicate/oxide
mineral reference does not cover this chemistry, so downstream matching would be
expected to abstain (insufficient reference scope).

Licence: the source (github.com/lukmuk/eds-processing-notebooks) is GPL-3.0. The
binary, any derivative/subset, and this script's output are kept OUTSIDE the git
repository and out of the PolyForm-licensed package.

Usage:
    AXIOMM_REALDATA_BCF=/abs/path/EDS_dataset.bcf python examples/bcf_inspect.py
    python examples/bcf_inspect.py /abs/path/EDS_dataset.bcf [OUT_DIR]

Output (written beside the data by default, NOT into git):
    <name>.inspection.json  + (if matplotlib present) <name>.quicklook.png
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

# The dataset's public provenance (from the local handoff); the SHA-256 and size
# are recomputed from the actual file at inspection time.
SOURCE = {
    "description": "STEM-EDS spectrum image of a REBa2Cu3O7-delta thin film on "
                   "SrTiO3, FEI Tecnai Osiris at 200 keV",
    "source_repo": "https://github.com/lukmuk/eds-processing-notebooks",
    "source_commit": "0554bf432762bf42b751203b7982d3d74d2b67ba",
    "licence": "GPL-3.0 (treat data conservatively as GPL-covered)",
}

# curated, AXIOMM-relevant metadata keys (dotted paths into signal.metadata)
_CURATED = {
    "beam_energy": "Acquisition_instrument.TEM.beam_energy",
    "live_time_s": "Acquisition_instrument.TEM.Detector.EDS.live_time",
    "real_time_s": "Acquisition_instrument.TEM.Detector.EDS.real_time",
    "detector_type": "Acquisition_instrument.TEM.Detector.EDS.detector_type",
    "detector_azimuth_deg": "Acquisition_instrument.TEM.Detector.EDS.azimuth_angle",
    "detector_elevation_deg": "Acquisition_instrument.TEM.Detector.EDS.elevation_angle",
    "elements_in_file": "Sample.elements",
    "acquisition_date": "General.date",
    "signal_type": "Signal.signal_type",
    "quantity": "Signal.quantity",
}


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _get(md, dotted: str):
    return (True, md.get_item(dotted)) if md.has_item(dotted) else (False, None)


def _tool_versions() -> dict:
    import hyperspy
    import rsciio

    import axiomm
    return {"hyperspy": hyperspy.__version__, "rosettasciio": rsciio.__version__,
            "numpy": np.__version__, "axiomm": axiomm.__version__}


def inspect_bcf(path: str | Path, *, plot: bool = True) -> dict:
    """Load, enumerate and quick-look a ``.bcf`` spectrum image; return the report."""
    import hyperspy.api as hs

    path = Path(path)
    signals = hs.load(str(path), select_type="spectrum_image", convert_units=True)
    signals = signals if isinstance(signals, list) else [signals]

    report: dict = {
        "dataset": {**SOURCE, "local_file": str(path),
                    "sha256": _sha256(path), "size_bytes": path.stat().st_size},
        "tools": _tool_versions(),
        "inspection_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "scientific_scope": (
            "real STEM-EDS spectrum image; NOT SEM; NOT mineral ground truth; NOT "
            "standards-based quantitative validation. Mineral matching is expected "
            "to abstain — this chemistry is outside AXIOMM's silicate/oxide reference."),
        "signals": [],
    }

    for i, s in enumerate(signals):
        axes = [{"index_in_array": ax.index_in_array, "name": ax.name, "size": int(ax.size),
                 "scale": float(ax.scale), "offset": float(ax.offset),
                 "units": str(ax.units), "navigate": bool(ax.navigate)}
                for ax in sorted(s.axes_manager._axes, key=lambda a: a.index_in_array)]
        md = s.metadata
        acquisition, diagnostics = {}, []
        for label, key in _CURATED.items():
            present, value = _get(md, key)
            acquisition[label] = value if present else None
            diagnostics.append(f"{label} ({key}): {'present' if present else 'ABSENT'}")

        sig = inspect_signal_arrays(s.data, axes)
        report["signals"].append({
            "index": i, "type": type(s).__name__,
            "title": md.get_item("General.title") if md.has_item("General.title") else None,
            "shape": list(s.data.shape), "dtype": str(s.data.dtype),
            "array_axis_order": [ax["name"] for ax in axes],
            "axes": axes, "acquisition": acquisition, "diagnostics": diagnostics,
            "quicklook": sig["summary"],
            "full_metadata": md.as_dictionary(),
        })
        if plot:
            _plot_quicklook(path, i, sig, axes)

    return report


def inspect_signal_arrays(data: np.ndarray, axes: list[dict]) -> dict:
    """Compute the summed EDS spectrum and total-counts map (facts, no analysis)."""
    nav = tuple(ax["index_in_array"] for ax in axes if ax["navigate"])
    sig = tuple(ax["index_in_array"] for ax in axes if not ax["navigate"])
    d = data.astype(np.float64)
    summed_spectrum = d.sum(axis=nav) if nav else d
    total_map = d.sum(axis=sig) if sig else d
    e_ax = next(ax for ax in axes if not ax["navigate"])
    energy = e_ax["offset"] + e_ax["scale"] * np.arange(e_ax["size"])
    peak_ch = int(np.argmax(summed_spectrum)) if summed_spectrum.ndim == 1 else -1
    return {
        "energy": energy, "summed_spectrum": summed_spectrum, "total_map": total_map,
        "summary": {
            "summed_spectrum_peak_keV": float(energy[peak_ch]) if peak_ch >= 0 else None,
            "total_counts_min": float(total_map.min()), "total_counts_max": float(total_map.max()),
            "total_counts_sum": float(d.sum()),
        },
    }


def _plot_quicklook(path: Path, idx: int, sig: dict, axes: list[dict]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.suptitle("AXIOMM real-data inspection — STEM-EDS spectrum image "
                 f"(signal {idx}); quick-look, not analysis", fontsize=11)
    ax[0].plot(sig["energy"], sig["summed_spectrum"], lw=0.7, color="#222")
    ax[0].set_xlabel("Energy (keV)")
    ax[0].set_ylabel("summed counts")
    ax[0].set_title("Summed EDS spectrum (all pixels)")
    im = ax[1].imshow(sig["total_map"], cmap="inferno")
    ax[1].set_title("Total-counts map")
    ax[1].set_xticks([])
    ax[1].set_yticks([])
    fig.colorbar(im, ax=ax[1], fraction=0.046)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    dest = path.with_suffix(f".signal{idx}.quicklook.png")
    fig.savefig(dest, dpi=120)
    plt.close(fig)
    print(f"  quick-look -> {dest}")


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    return str(o)


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else os.environ.get("AXIOMM_REALDATA_BCF")
    if not path:
        print("Provide a .bcf path (arg) or set AXIOMM_REALDATA_BCF.", file=sys.stderr)
        return 2
    path = Path(path)
    if not path.is_file():
        print(f"Not a file: {path}", file=sys.stderr)
        return 2
    out_dir = Path(argv[2]) if len(argv) > 2 else path.parent
    try:
        report = inspect_bcf(path)
    except ImportError as exc:
        print(f"Reader unavailable (install the [hyperspy] extra): {exc}", file=sys.stderr)
        return 3
    dest = out_dir / f"{path.stem}.inspection.json"
    # strip the (large) full metadata from stdout but keep it in the file
    dest.write_text(json.dumps(report, indent=2, default=_json_default))
    s0 = report["signals"][0]
    print(f"Inspected {path.name}: {s0['type']} {s0['shape']} {s0['dtype']}")
    print(f"  array axis order: {s0['array_axis_order']}")
    print(f"  beam_energy={s0['acquisition']['beam_energy']} "
          f"live_time_s={s0['acquisition']['live_time_s']} "
          f"elements_in_file={s0['acquisition']['elements_in_file']}")
    print(f"  provenance report -> {dest}  (kept outside git)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
