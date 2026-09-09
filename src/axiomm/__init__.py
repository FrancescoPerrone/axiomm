"""AXIOMM — Automated X-ray Intelligence for Organising Mineral Mapping.

A Python package for spectroscopy, applied to mineral-mapping workflows.

The recommended entry point is the pipeline::

    from axiomm import Pipeline
    result = Pipeline(beam_energy_kev=20).run("map.bcf")

The individual tools that make up that chain are one import away too, for when
you want to compose or tune a single stage::

    from axiomm import convert_file, decompose, cluster, quantify, render_report

Everything here is exposed **lazily** (PEP 562): a bare ``import axiomm`` — or
importing any submodule — stays minimal and free of import side effects; a heavy
backend (scikit-learn, xraylib, matplotlib, …) loads only when the tool that
needs it is actually used.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"

# Curated top-level surface: public name -> "module:attribute", resolved lazily.
_EXPORTS: dict[str, str] = {
    # the front door
    "Pipeline": "axiomm.pipeline:Pipeline",
    "run": "axiomm.pipeline:run",
    # converter
    "convert_file": "axiomm.io.converters:convert_file",
    "AxiommSignalPayload": "axiomm.io.converters.models:AxiommSignalPayload",
    "AxisSpec": "axiomm.io.converters.models:AxisSpec",
    # analysis stages (the compose path), in pipeline order
    "decompose": "axiomm.analysis.decomposition:decompose",
    "cluster": "axiomm.analysis.clustering:cluster",
    "compute_cluster_means": "axiomm.analysis.clustering:compute_cluster_means",
    "measure_peaks": "axiomm.analysis.peaks:measure_cluster_means",
    "compute_k_factors": "axiomm.analysis.quant:compute_k_factors",
    "quantify": "axiomm.analysis.quant:quantify_cluster_means",
    "assess_reliability": "axiomm.analysis.quant:assess_cluster_reliability",
    "match_minerals": "axiomm.analysis.mineralogy.match:match_clusters",
    "get_reference": "axiomm.analysis:get_reference",
    # reporting
    "render_report": "axiomm.analysis.reporting:render_report",
    "ReportConfig": "axiomm.analysis.reporting:ReportConfig",
}

__all__ = ["__version__", *sorted(_EXPORTS)]


def __getattr__(name: str):
    # PEP 562 lazy attribute access: import the target module (and its heavy
    # backend, if any) only when the name is actually requested.
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    module_path, _, attr = target.partition(":")
    return getattr(importlib.import_module(module_path), attr)


def __dir__() -> list[str]:
    return sorted(__all__)
