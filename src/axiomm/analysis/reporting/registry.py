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

#: Per-stage section renderers (id -> SectionRenderer instance).
#: Populated as stage sections land (S4b onward).
sections: Registry = Registry("report section")


__all__ = ["reporters", "sections"]
