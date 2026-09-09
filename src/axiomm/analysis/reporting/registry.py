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
sections.register("overview", "axiomm.analysis.reporting.section_renderers.overview:OverviewSection")
sections.register("decomposition",
                  "axiomm.analysis.reporting.section_renderers.decomposition:DecompositionSection")
sections.register("clustering", "axiomm.analysis.reporting.section_renderers.clustering:ClusteringSection")
sections.register("embedding", "axiomm.analysis.reporting.section_renderers.embedding:EmbeddingSection")
sections.register("cluster_means",
                  "axiomm.analysis.reporting.section_renderers.cluster_means:ClusterMeansSection")
sections.register("peaks", "axiomm.analysis.reporting.section_renderers.peaks:PeaksSection")
sections.register("quant", "axiomm.analysis.reporting.section_renderers.quant:QuantSection")
sections.register("reliability",
                  "axiomm.analysis.reporting.section_renderers.reliability:ReliabilitySection")
sections.register("minerals", "axiomm.analysis.reporting.section_renderers.minerals:MineralsSection")
sections.register("phase_map", "axiomm.analysis.reporting.section_renderers.phase_map:PhaseMapSection")


__all__ = ["reporters", "sections"]
