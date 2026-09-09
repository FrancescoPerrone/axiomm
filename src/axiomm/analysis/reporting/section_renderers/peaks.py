"""Peaks section — the net-intensity table behind the spectra (stage two, S4d)."""

from __future__ import annotations

from axiomm.analysis.reporting.models import ReportSection, Table


class PeaksSection:
    id = "peaks"

    def applies(self, result) -> bool:
        return bool(getattr(result, "peaks", None))

    def render(self, result, config) -> ReportSection:
        rows = []
        for pset in result.peaks:
            cid = pset.cluster_id
            for m in sorted(pset.measurements, key=lambda m: m.center_kev):
                if not getattr(m, "in_range", True):
                    continue
                rows.append([cid, m.label, round(float(m.center_kev), 3),
                             round(float(m.net), 1), round(float(m.gross), 1),
                             round(float(m.background), 2), int(m.n_channels)])
        table = Table(["cluster", "line", "centre keV", "net", "gross", "bkg / ch", "window ch"],
                      rows, "net line intensities")
        note = ("Net = gross - background * window. Net can be negative when the "
                "background is over-subtracted - a diagnostic, not an error.")
        return ReportSection("peaks", "Peaks", [note, table])


__all__ = ["PeaksSection"]
