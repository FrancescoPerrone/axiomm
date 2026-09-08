"""Minerals section — exploratory candidate rankings (stage two, S4d).

Candidate matches with scores and evidence — never a validated identification.
Where the chemistry is outside the reference, the honest row is *unresolved*.
Honours a ``top_n`` option (default 3 candidates per cluster).
"""

from __future__ import annotations

from axiomm.analysis.reporting.models import ReportSection, Table


class MineralsSection:
    id = "minerals"

    def applies(self, result) -> bool:
        return bool(getattr(result, "minerals", None))

    def render(self, result, config) -> ReportSection:
        top_n = int(config.options_for(self.id).get("top_n", 3))
        rows = []
        for m in result.minerals:
            cid = m.cluster_id
            cands = list(m.candidates)[:top_n]
            if not cands:
                rows.append([cid, "unresolved", "—", "—", "—", "—"])
                continue
            for c in cands:
                rows.append([cid, c.name, c.family, round(float(c.score), 3),
                             c.n_informative_dims, round(float(c.dimension_coverage), 2)])
        table = Table(["cluster", "candidate", "family", "score", "dims used", "coverage"],
                      rows, "exploratory candidate rankings")
        note = ("Exploratory ranking, not an identification. 'unresolved' means the "
                "chemistry falls outside the reference — an honest abstention.")
        return ReportSection("minerals", "Minerals", [note, table])


__all__ = ["MineralsSection"]
