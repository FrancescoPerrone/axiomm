"""The :class:`Pipeline` — AXIOMM's one-call front door.

Runs the trusted stage-two tools in order and returns one
:class:`PipelineResult`. Does as much as the data and settings support, skipping
honestly (with a diagnostic) rather than forcing a result. Heavy backends load
lazily inside :meth:`Pipeline.run`, so ``from axiomm import Pipeline`` is cheap.
"""

from __future__ import annotations

import dataclasses
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
from axiomm.analysis.quant.overlaps import detect_line_overlaps
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

    def _normalize_payload(self, payload, diagnostics):
        """Put spectra on a *per incident photon* footing when the reader
        supplied an ``intensity_norm`` divisor (e.g. I0 with dead-time
        correction), dividing every pixel's spectrum by it.

        General: any flux/time-monitored map can carry ``intensity_norm``;
        when it is absent the payload is returned untouched and raw counts are
        used (no crash, no silent assumption). The divisor is median-scaled to
        1 so the normalisation reshapes relative pixel brightness without
        changing the data's overall magnitude, and bad pixels (``NaN``/non-
        positive divisor) keep their raw counts rather than becoming ``NaN``.
        The returned payload carries the normalised cube and clears
        ``intensity_norm`` so the step cannot be applied twice.
        """
        norm = getattr(payload, "intensity_norm", None)
        if norm is None:
            return payload
        data = np.asarray(payload.data, dtype=np.float64)
        norm = np.asarray(norm, dtype=np.float64)
        if norm.ndim != 2 or norm.shape != data.shape[:2]:
            diagnostics.append(Diagnostic(
                "warning", "normalization_skipped",
                f"intensity_norm shape {norm.shape} does not align with the "
                f"navigation grid {data.shape[:2]}; raw counts used."))
            return payload
        median = np.nanmedian(norm)
        if not np.isfinite(median) or median <= 0:
            diagnostics.append(Diagnostic(
                "warning", "normalization_skipped",
                "intensity_norm has no usable (finite, positive) values; raw counts used."))
            return payload
        scaled = norm / median
        # bad pixels (NaN / non-positive) divide by 1.0 -> left as raw counts
        usable = np.isfinite(scaled) & (scaled > 0)
        scaled = np.where(usable, scaled, 1.0)
        normalized = data / scaled[:, :, None]
        n_bad = int((~usable).sum())
        tail = f" ({n_bad} pixel(s) lacked a usable divisor and kept raw counts)." if n_bad else "."
        diagnostics.append(Diagnostic(
            "info", "normalization_applied",
            "spectra normalised per pixel by the incident-flux/dead-time divisor "
            "(intensity_norm), median-scaled to preserve overall magnitude" + tail))
        return dataclasses.replace(payload, data=normalized, intensity_norm=None)

    # -- run -----------------------------------------------------------------
    def run(self, source) -> PipelineResult:
        cfg = self.config
        diagnostics: list[Diagnostic] = []
        payload = self._read_payload(source)
        if cfg.normalize:
            payload = self._normalize_payload(payload, diagnostics)

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
        # classification (S7): turn matching evidence into species/family/unresolved
        # labels under the chosen policy. Evidence (minerals) is left untouched.
        from axiomm.analysis.mineralogy.classify import classify_clusters
        policy = self._resolve_classification(cfg, diagnostics)
        labels = classify_clusters(minerals, reference, policy)
        phase_map = self._build_phase_map(clustering.label_map, labels)
        result_kwargs.update(
            peaks=peaks, quantification=quant, reliability=reliability,
            minerals=minerals, labels=labels, phase_map=phase_map,
            provenance=self._provenance(cfg, decomp, clustering, reference, policy),
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

    def _resolve_classification(self, cfg, diagnostics):
        """Return a :class:`ClassificationPolicy` from ``cfg.classification``.

        ``None`` -> the default ``ThresholdPolicy``. An instance is used as-is.
        A name / ``{"name": ..., **opts}`` dict resolves through the S7
        ``classifiers`` registry (a bare name yields the preset instance; a dict
        with extra keys constructs that policy class with the overrides).
        """
        from axiomm.analysis.mineralogy.classify import ThresholdPolicy, classifiers
        spec = cfg.classification
        if spec is None:
            return ThresholdPolicy()
        if hasattr(spec, "classify"):
            diagnostics.append(Diagnostic(
                "info", "stage_instance_supplied",
                "classification supplied as an instance; its own settings govern "
                "the labels (named presets are not applied to it)."))
            return spec
        opts = {"name": spec} if isinstance(spec, str) else dict(spec)
        name = opts.pop("name")
        base = classifiers.get(name)       # the preset instance, carrying its registered settings
        if not opts:
            return base
        # Layer only the explicit overrides ONTO the preset, so e.g.
        # {"name": "conservative", "species_floor": 0.9} keeps conservative's
        # family_floor / allow_family rather than reverting them to class defaults.
        # (Classification presets carry non-default settings, unlike the reduction/
        # clustering registries whose entries sit at their constructor defaults.)
        if not dataclasses.is_dataclass(base):
            raise PayloadValidationError(
                f"classification preset {name!r} does not accept option overrides.")
        try:
            return dataclasses.replace(base, **opts)   # re-runs the policy's validation
        except TypeError as exc:
            raise PayloadValidationError(
                f"invalid option(s) for classification preset {name!r}: {exc}") from exc

    # -- stages --------------------------------------------------------------
    def _quantify_and_match(self, payload, means, reference, cfg, diagnostics):
        signal_axis = next(a for a in payload.axes if a.role == "signal")
        emin = float(signal_axis.offset)
        emax = float(signal_axis.offset) + float(signal_axis.scale) * (int(signal_axis.size) - 1)
        # in-range cations from the reference (structural elements like O/Br/I excluded)
        cations = list(reference.cations_in_range(emin, emax))
        # Honest quantification: drop user-excluded interferents, then refuse to
        # quantify emission lines the detector cannot resolve (report them, never
        # guess which element a blended peak belongs to).
        if cfg.exclude_elements:
            dropped = sorted(c for c in cations if c in cfg.exclude_elements)
            cations = [c for c in cations if c not in cfg.exclude_elements]
            if dropped:
                diagnostics.append(Diagnostic(
                    "info", "elements_excluded",
                    f"excluded from quantification by request: {dropped}."))
        for group in detect_line_overlaps(reference.line_energies(cations),
                                          cfg.line_resolution_kev):
            es = reference.line_energies(group)
            diagnostics.append(Diagnostic(
                "warning", "line_overlap",
                "emission lines overlap within "
                f"{cfg.line_resolution_kev} keV and cannot be resolved ("
                + ", ".join(f"{s} {es[s]:.3f} keV" for s in group)
                + "); excluded from the composition — resolve by excluding the "
                "interfering element via exclude_elements."))
            cations = [c for c in cations if c not in group]
        if cfg.reference_element not in cations:
            raise PayloadValidationError(
                f"reference_element {cfg.reference_element!r} is not available for "
                f"quantification: no line in the energy range [{emin:.2f}, {emax:.2f}] "
                "keV, or it was excluded / lost to a line overlap; choose a measurable, "
                "resolved reference_element.")
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

    def _build_phase_map(self, label_map, labels):
        """Per-pixel phase names from the S7 classification labels (UNRESOLVED
        where the policy abstained)."""
        name_by = {int(lab.cluster_id): (UNRESOLVED if lab.level == "unresolved" else lab.name)
                   for lab in labels}
        label_map = np.asarray(label_map)
        phase = np.full(label_map.shape, UNRESOLVED, dtype=object)
        for cid, name in name_by.items():
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
                "reference_element": c.reference_element, "seed": c.seed,
                "classification": _stage_name(c.classification, "family_aware")}

    def _provenance(self, cfg, decomp, clustering, reference, policy=None) -> dict:
        return {
            "tool": "axiomm.pipeline", "software_version": _AXIOMM_VERSION,
            "config": self._config_dict(),
            "decomposition": dict(decomp.provenance.params) if decomp.provenance else {},
            "clustering": dict(clustering.provenance.params) if clustering.provenance else {},
            "classification": policy.params() if policy is not None else None,
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
