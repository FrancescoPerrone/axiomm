"""Raw-data navigator section — the summed-intensity map AXIOMM analyses, with a
click-to-open pixel-by-pixel spectrum navigator (see
:mod:`axiomm.analysis.reporting.navigator`).

Applies whenever the result carries its source payload (the raw cube). Binning is
configurable via the section options ``spatial_bin`` / ``energy_bin`` (defaults keep
the embedded, gzip-compressed cube small).
"""

from __future__ import annotations

from axiomm.analysis.reporting.models import Html, ReportSection
from axiomm.analysis.reporting.navigator import navigator_markup


class NavigatorSection:
    id = "navigator"

    def applies(self, result) -> bool:
        payload = getattr(result, "payload", None)
        data = getattr(payload, "data", None)
        return data is not None and getattr(data, "ndim", 0) == 3

    def render(self, result, config) -> ReportSection:
        opts = config.options_for(self.id)
        # Defaults keep the embedded (gzip-compressed) cube modest so every report
        # stays shareable; raise the resolution per run via the section options.
        markup = navigator_markup(
            result.payload,
            spatial_bin=int(opts.get("spatial_bin", 2)),
            energy_bin=int(opts.get("energy_bin", 16)),
        )
        note = ("Raw summed-intensity map — the data AXIOMM analyses, before reduction "
                "or clustering. Click the map to explore it pixel-by-pixel.")
        return ReportSection("navigator", "Raw map", [note, Html(markup)])


__all__ = ["NavigatorSection"]
