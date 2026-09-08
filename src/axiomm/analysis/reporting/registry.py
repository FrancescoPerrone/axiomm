"""Registries for report backends and section renderers (stage two, S4).

Both mirror the S1/S2 backend registries: a stable string name resolves to a
fresh instance. New report *formats* register in :data:`reporters`; new stage
*sections* register in :data:`sections`. Resolving a name imports its backend
lazily, so importing this module never pulls matplotlib.
"""

from __future__ import annotations

from axiomm.analysis.registry import Registry

#: Report-format backends (name -> Reporter instance).
reporters: Registry = Registry("reporter")
reporters.register("html", "axiomm.analysis.reporting.html:HtmlReporter")

#: Per-stage section renderers (id -> SectionRenderer instance). Registered
#: lazily so importing this module pulls in neither numpy nor matplotlib.
sections: Registry = Registry("report section")
sections.register("overview", "axiomm.analysis.reporting.sections.overview:OverviewSection")
sections.register("decomposition",
                  "axiomm.analysis.reporting.sections.decomposition:DecompositionSection")
sections.register("clustering", "axiomm.analysis.reporting.sections.clustering:ClusteringSection")
sections.register("cluster_means",
                  "axiomm.analysis.reporting.sections.cluster_means:ClusterMeansSection")
sections.register("peaks", "axiomm.analysis.reporting.sections.peaks:PeaksSection")
sections.register("quant", "axiomm.analysis.reporting.sections.quant:QuantSection")
sections.register("reliability",
                  "axiomm.analysis.reporting.sections.reliability:ReliabilitySection")
sections.register("minerals", "axiomm.analysis.reporting.sections.minerals:MineralsSection")
sections.register("phase_map", "axiomm.analysis.reporting.sections.phase_map:PhaseMapSection")


__all__ = ["reporters", "sections"]
