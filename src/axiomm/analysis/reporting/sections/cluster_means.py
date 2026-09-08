"""Spectra section — per-cluster mean spectrum with peak IDs (stage two, S4d).

The priority view: one crisp, theme-aware inline-SVG spectrum per cluster
(energy-calibrated), with identified lines drawn as labelled ticks over shaded
integration windows and their background level. Needs no matplotlib. Honours
``y_scale`` (linear/sqrt/log), ``max_clusters`` and ``energy_range`` options.
"""

from __future__ import annotations

import numpy as np

from axiomm.analysis.models import Diagnostic
from axiomm.analysis.reporting.models import ReportSection, Svg
from axiomm.analysis.reporting.svg import spectrum_svg


class ClusterMeansSection:
    id = "cluster_means"

    def applies(self, result) -> bool:
        return getattr(result, "cluster_means", None) is not None \
            and getattr(result, "payload", None) is not None

    def render(self, result, config) -> ReportSection:
        opts = config.options_for(self.id)
        y_scale = opts.get("y_scale", "linear")
        erange = opts.get("energy_range")
        max_clusters = int(opts.get("max_clusters", 8))

        means = result.cluster_means
        spectra = np.asarray(means.means, dtype=float)
        cluster_ids = [int(c) for c in np.asarray(means.cluster_ids)]
        counts = ([int(c) for c in np.asarray(means.pixel_counts)]
                  if getattr(means, "pixel_counts", None) is not None else [None] * len(cluster_ids))

        axis = next(a for a in result.payload.axes if a.role == "signal")
        scale = float(axis.scale)
        energies = float(axis.offset) + scale * np.arange(int(axis.size))
        peaks_by = {s.cluster_id: s for s in (getattr(result, "peaks", None) or ())}

        blocks: list = ["Mean spectrum per cluster. Shaded bands are the measured "
                        "line windows over their background; ticks mark identified lines."]
        diags: list[Diagnostic] = []
        shown = cluster_ids[:max_clusters]
        if len(cluster_ids) > max_clusters:
            diags.append(Diagnostic("info", "spectra_truncated",
                                    f"showing {max_clusters} of {len(cluster_ids)} clusters "
                                    "(raise the max_clusters option to see more)."))

        for i, cid in enumerate(shown):
            peaks = _peaks_for(peaks_by.get(cid), scale)
            px = counts[i]
            title = f"cluster {cid}" + (f" · {px} px" if px is not None else "")
            svg = spectrum_svg(energies, spectra[i], peaks, y_scale=y_scale,
                               energy_range=erange, title=title)
            blocks.append(Svg(svg, caption=title))

        return ReportSection("cluster_means", "Spectra", blocks, diagnostics=diags)


def _peaks_for(pset, scale: float) -> list[dict]:
    if pset is None:
        return []
    out = []
    for m in pset.measurements:
        if not getattr(m, "in_range", True):
            continue
        out.append({"label": m.label, "center_kev": float(m.center_kev),
                    "window_kev": int(m.n_channels) * scale, "background": float(m.background)})
    return out


__all__ = ["ClusterMeansSection"]
