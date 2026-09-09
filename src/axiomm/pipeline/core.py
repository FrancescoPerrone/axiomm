"""The :class:`Pipeline` — AXIOMM's one-call front door.

Runs the trusted stage-two tools in order and returns one
:class:`PipelineResult`. Does as much as the data and settings support, skipping
honestly (with a diagnostic) rather than forcing a result. Heavy backends load
lazily inside :meth:`Pipeline.run`, so ``from axiomm import Pipeline`` is cheap.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np

from axiomm.analysis.clustering import GMMClusterer, GMMConfig, compute_cluster_means
from axiomm.analysis.errors import AnalysisDependencyError, PayloadValidationError
from axiomm.analysis.models import Diagnostic
from axiomm.analysis.peaks import measure_peaks
from axiomm.analysis.quant import (
    ReliabilityConfig,
    assess_cluster_reliability,
    compute_k_factors,
    quantify_cluster_means,
)
from axiomm.pipeline.config import PipelineConfig
from axiomm.pipeline.result import UNRESOLVED, PipelineResult

try:
    from axiomm import __version__ as _AXIOMM_VERSION
except Exception:  # pragma: no cover - version always importable in practice
    _AXIOMM_VERSION = "unknown"


class Pipeline:
    """Run the whole analysis with one call: ``Pipeline().run(source)``."""

    def __init__(self, config: PipelineConfig | None = None, **kwargs) -> None:
        if config is not None and kwargs:
            raise PayloadValidationError("pass a PipelineConfig or keyword settings, not both.")
        self.config = config or PipelineConfig(**kwargs)

    # -- ingestion -----------------------------------------------------------
    def _read_payload(self, source):
        """A payload passes through; a path is read via the converter's readers."""
        if hasattr(source, "axes") and hasattr(source, "data"):
            return source
        path = Path(source)
        from axiomm.io.converters.registry import readers
        candidates = [r for r in readers if r.can_read(path)]
        if not candidates:
            raise PayloadValidationError(
                f"no reader can read {path.name!r}; known readers: {readers.names()}.")
        if len(candidates) > 1:
            raise PayloadValidationError(
                f"multiple readers accept {path.name!r}: {[c.name for c in candidates]}.")
        return candidates[0].read(path, lazy=False)

    # -- run -----------------------------------------------------------------
    def run(self, source) -> PipelineResult:
        cfg = self.config
        diagnostics: list[Diagnostic] = []
        payload = self._read_payload(source)

        # dimensional reduction -> clustering -> cluster mean spectra (pluggable)
        reducer, n_components = self._resolve_reduction(cfg, diagnostics)
        decomp = reducer.decompose(payload, n_components=n_components)
        clusterer = self._resolve_clustering(cfg, diagnostics)
        clustering = clusterer.cluster(decomp)
        means = compute_cluster_means(clustering, payload)
        diagnostics += list(decomp.diagnostics) + list(clustering.diagnostics) + list(means.diagnostics)

        result_kwargs = dict(
            label_map=np.asarray(clustering.label_map), cluster_means=means,
            clustering=clustering, decomposition=decomp, payload=payload,
            config=self._config_dict(), diagnostics=diagnostics,
        )

        reference = self._resolve_reference(cfg.reference)
        if cfg.beam_energy_kev is None or reference is None:
            diagnostics.append(Diagnostic(
                "info", "minerals_skipped",
                "quantification + matching not run: set beam_energy_kev and a "
                "reference to enable them. Clusters and cluster spectra are returned."))
            result_kwargs["provenance"] = self._provenance(cfg, decomp, clustering, reference)
            return PipelineResult(**result_kwargs)

        # peaks -> quantification -> reliability -> mineral matching
        try:
            minerals_bundle = self._quantify_and_match(payload, means, reference, cfg, diagnostics)
        except AnalysisDependencyError as exc:
            diagnostics.append(Diagnostic(
                "warning", "minerals_skipped_dependency",
                f"quantification + matching skipped: {exc}"))
            result_kwargs["provenance"] = self._provenance(cfg, decomp, clustering, reference)
            return PipelineResult(**result_kwargs)

        peaks, quant, reliability, minerals = minerals_bundle
        phase_map = self._build_phase_map(clustering.label_map, means, minerals)
        result_kwargs.update(
            peaks=peaks, quantification=quant, reliability=reliability,
            minerals=minerals, phase_map=phase_map,
            provenance=self._provenance(cfg, decomp, clustering, reference),
        )
        return PipelineResult(**result_kwargs)

    # -- pluggable stage resolution ------------------------------------------
    def _resolve_reduction(self, cfg, diagnostics):
        """Return ``(decomposer, n_components)`` from ``cfg.reduction``.

        ``None`` -> today's seeded PCA. An instance is used as-is (it owns its
        own randomness). A name / ``{"name": ..., **ctor_kwargs}`` dict resolves
        through the S1 ``decomposers`` registry; the pipeline seed is threaded as
        ``random_state`` when the backend accepts it and the caller didn't set it.
        ``n_components`` stays the ``components`` knob unless the dict overrides it.
        """
        spec = cfg.reduction
        n_components = cfg.components
        if spec is None:
            from axiomm.analysis.decomposition.sklearn_pca import SklearnPCADecomposer
            return SklearnPCADecomposer(random_state=cfg.seed), n_components
        if hasattr(spec, "decompose"):
            diagnostics.append(Diagnostic(
                "info", "stage_instance_supplied",
                "reduction supplied as an instance; its own random_state governs "
                "reproducibility (the pipeline seed is not applied to it)."))
            return spec, n_components
        opts = {"name": spec} if isinstance(spec, str) else dict(spec)
        name = opts.pop("name")
        from axiomm.analysis.decomposition import decomposers
        cls = type(decomposers.get(name))  # registry yields instances; take the class
        if "n_components" in opts:
            n_components = opts.pop("n_components")
        if "random_state" not in opts and _accepts(cls, "random_state"):
            opts["random_state"] = cfg.seed
        return cls(**opts), n_components

    def _resolve_clustering(self, cfg, diagnostics):
        """Return a clusterer from ``cfg.clustering``.

        ``None`` -> today's seeded GMM. An instance is used as-is. A name /
        ``{"name": ..., **ctor_kwargs}`` dict resolves through the S2
        ``clusterers`` registry (which yields the class); ``n_clusters`` defaults
        to the ``groups`` knob and GMM backends are seeded from the pipeline seed.
        """
        spec = cfg.clustering
        if spec is None:
            return GMMClusterer(n_clusters=cfg.groups, config=GMMConfig(random_state=cfg.seed))
        if hasattr(spec, "cluster"):
            diagnostics.append(Diagnostic(
                "info", "stage_instance_supplied",
                "clustering supplied as an instance; its own n_clusters and "
                "random_state govern (the pipeline groups/seed are not applied to it)."))
            return spec
        opts = {"name": spec} if isinstance(spec, str) else dict(spec)
        name = opts.pop("name")
        from axiomm.analysis.clustering import clusterers
        cls = clusterers.get(name)  # registry yields the class
        # only fixed-k backends take n_clusters (GMM); density backends (HDBSCAN) don't
        if _accepts(cls, "n_clusters") and "n_clusters" not in opts:
            opts["n_clusters"] = cfg.groups
        if issubclass(cls, GMMClusterer) and "config" not in opts:
            opts["config"] = GMMConfig(random_state=cfg.seed)
        return cls(**opts)

    # -- stages --------------------------------------------------------------
    def _quantify_and_match(self, payload, means, reference, cfg, diagnostics):
        signal_axis = next(a for a in payload.axes if a.role == "signal")
        emin = float(signal_axis.offset)
        emax = float(signal_axis.offset) + float(signal_axis.scale) * (int(signal_axis.size) - 1)
        # in-range cations from the reference (structural elements like O/Br/I excluded)
        cations = reference.cations_in_range(emin, emax)
        if cfg.reference_element not in cations:
            raise PayloadValidationError(
                f"reference_element {cfg.reference_element!r} has no line in the spectrum's "
                f"energy range [{emin:.2f}, {emax:.2f}] keV; set reference_element to a "
                "measurable element.")
        peaks = measure_peaks(means, signal_axis, reference)

        k = compute_k_factors(reference.element_refs(cations),
                              excitation_kev=cfg.beam_energy_kev, reference=cfg.reference_element)
        quant_elements = list(reference.element_refs(cations))
        if "O" in reference.elements:
            quant_elements.append(reference.elements["O"])
        quant = quantify_cluster_means(list(peaks), k, quant_elements, reference_name=reference.name)
        reliability = assess_cluster_reliability(
            list(quant), means, config=cfg.reliability or ReliabilityConfig())

        from axiomm.analysis.mineralogy.match import MatchConfig, match_clusters
        minerals = match_clusters(list(quant), reference, reliabilities=list(reliability),
                                  config=cfg.match or MatchConfig())
        diagnostics += list(k.diagnostics)
        return peaks, quant, reliability, minerals

    def _build_phase_map(self, label_map, means, minerals):
        best = {}
        for m in minerals:
            top = m.best()
            best[int(m.cluster_id)] = top.name if top else UNRESOLVED
        label_map = np.asarray(label_map)
        phase = np.full(label_map.shape, UNRESOLVED, dtype=object)
        for cid, name in best.items():
            phase[label_map == cid] = name
        return phase

    # -- helpers -------------------------------------------------------------
    def _resolve_reference(self, reference):
        if reference is None:
            return None
        if isinstance(reference, str):
            from axiomm.analysis.reference import get_reference
            return get_reference(reference)
        return reference

    def _config_dict(self) -> dict:
        c = self.config
        return {"groups": c.groups, "components": c.components,
                "reduction": _stage_name(c.reduction, "pca"),
                "clustering": _stage_name(c.clustering, "gmm"),
                "reference": c.reference if isinstance(c.reference, str) else getattr(c.reference, "name", "custom"),
                "beam_energy_kev": c.beam_energy_kev,
                "reference_element": c.reference_element, "seed": c.seed}

    def _provenance(self, cfg, decomp, clustering, reference) -> dict:
        return {
            "tool": "axiomm.pipeline", "software_version": _AXIOMM_VERSION,
            "config": self._config_dict(),
            "decomposition": dict(decomp.provenance.params) if decomp.provenance else {},
            "clustering": dict(clustering.provenance.params) if clustering.provenance else {},
            "reference_name": getattr(reference, "name", None),
            "reference_version": getattr(reference, "version", None),
            "beam_energy_kev": cfg.beam_energy_kev,
        }


def _accepts(cls, param: str) -> bool:
    """Whether ``cls.__init__`` takes a keyword named ``param``."""
    try:
        return param in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins without a signature
        return False


def _stage_name(spec, default: str) -> str:
    """A short, provenance-friendly name for a stage spec."""
    if spec is None:
        return default
    if isinstance(spec, str):
        return spec
    if isinstance(spec, dict):
        return spec.get("name", "custom")
    return type(spec).__name__


def run(source, **kwargs) -> PipelineResult:
    """Convenience: ``axiomm.pipeline.run("map.bcf", beam_energy_kev=20)``."""
    return Pipeline(**kwargs).run(source)


__all__ = ["Pipeline", "run"]
