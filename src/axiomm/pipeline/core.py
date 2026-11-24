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


#: Plain-English facade aliases: friendly keyword -> canonical ``PipelineConfig`` field.
#: (``beam_energy`` is handled separately because its value is parsed to keV.)
_FACADE_ALIASES = {
    "clusters": "groups",
    "library": "reference",
    "naming_policy": "classification",
}


def _signal_axis(payload):
    """The payload's signal (energy) axis."""
    return next(a for a in payload.axes if a.role == "signal")


def _signal_range(axis):
    """``(emin, emax)`` keV spanned by a signal axis (unit-aware: an eV axis or a
    non-zero offset is resolved to keV exactly as the peak integration does)."""
    from axiomm.analysis.peaks.energy import resolve_energy_axis
    grid = resolve_energy_axis(axis, int(axis.size))
    return float(grid[0]), float(grid[-1])


class Pipeline:
    """Run the whole analysis with one call: ``Pipeline().run(source)``.

    Settings read as plain English (every name has a canonical alias that also works):
    ``beam_energy="13.55 keV"`` (or ``beam_energy_kev=13.55``), ``clusters=7`` (``groups``),
    ``library="minerals_default_v2"`` (``reference``), ``naming_policy="family_aware"``
    (``classification``), ``exclude_elements=["Ba"]``. Passing a word *and* its alias is an error.
    """

    def __init__(self, config: PipelineConfig | None = None, **kwargs) -> None:
        if config is not None and kwargs:
            raise PayloadValidationError("pass a PipelineConfig or keyword settings, not both.")
        self.config = config or PipelineConfig(**self._resolve_aliases(kwargs))

    @staticmethod
    def _resolve_aliases(kwargs: dict) -> dict:
        """Map plain-English keywords to canonical ``PipelineConfig`` fields, parsing
        ``beam_energy`` to keV. Supplying both a word and its alias is a named error."""
        kwargs = dict(kwargs)
        if "beam_energy" in kwargs:
            if "beam_energy_kev" in kwargs:
                raise PayloadValidationError("pass either 'beam_energy' or 'beam_energy_kev', not both.")
            from axiomm.analysis.units import parse_energy_kev
            kwargs["beam_energy_kev"] = parse_energy_kev(kwargs.pop("beam_energy"))
        for friendly, canonical in _FACADE_ALIASES.items():
            if friendly in kwargs:
                if canonical in kwargs:
                    raise PayloadValidationError(f"pass either {friendly!r} or {canonical!r}, not both.")
                kwargs[canonical] = kwargs.pop(friendly)
        return kwargs

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

    def _normalize_cross_map(self, payload, diagnostics):
        """Cross-acquisition comparability normalisation for the FUSED QUANT (#3).

        Divides by the **raw** ``intensity_norm`` (I0/dead-time) *without* the per-map
        median rescale that ``_normalize_payload`` applies, so two maps land on one
        per-incident-photon scale and an exposure/monitor difference cancels across
        energies. The cube stays **finite** (an invalid-divisor pixel keeps its raw
        counts, divided by 1); an explicit **validity mask** (navigation-shaped, ``False``
        at invalid pixels) is returned so the cluster means exclude them without writing
        ``NaN`` (which the strict reshape validation rejects). Returns ``(payload_or_None,
        valid_mask_or_None, comparable)``: without a usable ``intensity_norm`` the
        cross-energy scale cannot be established, and the caller withholds the composition.
        """
        norm = getattr(payload, "intensity_norm", None)
        if norm is None:
            return None, None, False
        data = np.asarray(payload.data, dtype=np.float64)
        norm = np.asarray(norm, dtype=np.float64)
        if norm.ndim != 2 or norm.shape != data.shape[:2]:
            diagnostics.append(Diagnostic(
                "warning", "cross_map_normalization_skipped",
                f"intensity_norm shape {norm.shape} does not align with the nav grid "
                f"{data.shape[:2]}; cross-energy comparability cannot be established."))
            return None, None, False
        usable = np.isfinite(norm) & (norm > 0)
        if not usable.any():
            diagnostics.append(Diagnostic(
                "warning", "cross_map_normalization_skipped",
                "intensity_norm has no usable (finite, positive) values; cross-energy "
                "comparability cannot be established."))
            return None, None, False
        div = np.where(usable, norm, 1.0)        # invalid pixels -> /1 (finite); masked out via valid_mask
        normalized = data / div[:, :, None]
        n_bad = int((~usable).sum())
        diagnostics.append(Diagnostic(
            "info", "cross_map_normalization_applied",
            "fused-quant spectra divided by the raw incident-flux/dead-time divisor "
            "(intensity_norm) on a common per-incident-photon scale across energies"
            + (f"; {n_bad} invalid-divisor pixel(s) excluded from the means." if n_bad else ".")))
        return dataclasses.replace(payload, data=normalized, intensity_norm=None), usable, True

    # -- run -----------------------------------------------------------------
    def run(self, source) -> PipelineResult:
        from axiomm.analysis.fusion.models import MultiEnergyMapGroup
        if isinstance(source, MultiEnergyMapGroup):
            return self._run_fused(source)   # S8 multi-energy path (opt-in)
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
    def _cations_for_quant(self, payload, reference, cfg, diagnostics):
        """In-range, honestly-filtered cations + the signal axis (single-energy path)."""
        signal_axis = _signal_axis(payload)
        emin, emax = _signal_range(signal_axis)
        cations = self._filter_cations(
            reference.cations_in_range(emin, emax), reference, cfg, diagnostics,
            where=f"the energy range [{emin:.2f}, {emax:.2f}] keV")
        return cations, signal_axis

    def _filter_cations(self, cations, reference, cfg, diagnostics, *, where):
        """Honest quantification: drop user-excluded interferents, then refuse to
        quantify emission lines the detector cannot resolve (report them, never guess
        which element a blended peak belongs to). ``where`` names the range for errors."""
        cations = list(cations)
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
                f"quantification: no line in {where}, or it was excluded / lost to a line "
                "overlap; choose a measurable, resolved reference_element.")
        return cations

    def _quant_elements(self, reference, cation_refs):
        """The element refs to quantify: the cations plus O when the reference has it."""
        quant_elements = list(cation_refs)
        if "O" in reference.elements:
            quant_elements.append(reference.elements["O"])
        return quant_elements

    def _resolve_energy_selection(self, cfg):
        """The fusion per-element energy-selection policy: a name, a policy instance, or
        ``None`` (the default ``best_excited``). ``select_energies`` resolves a name."""
        return cfg.energy_selection

    def _quantify_and_match(self, payload, means, reference, cfg, diagnostics):
        cations, signal_axis = self._cations_for_quant(payload, reference, cfg, diagnostics)
        peaks = measure_peaks(means, signal_axis, reference)

        k = compute_k_factors(reference.element_refs(cations),
                              excitation_kev=cfg.beam_energy_kev, reference=cfg.reference_element)
        quant_elements = self._quant_elements(reference, reference.element_refs(cations))
        quant = quantify_cluster_means(list(peaks), k, quant_elements, reference_name=reference.name)
        reliability = assess_cluster_reliability(
            list(quant), means, config=cfg.reliability or ReliabilityConfig())

        from axiomm.analysis.mineralogy.match import MatchConfig, match_clusters
        minerals = match_clusters(list(quant), reference, reliabilities=list(reliability),
                                  config=cfg.match or MatchConfig())
        diagnostics += list(k.diagnostics)
        return peaks, quant, reliability, minerals

    # -- multi-energy fusion path (S8, opt-in) -------------------------------
    def _run_fused(self, group) -> PipelineResult:
        """Run the analysis over a co-registered multi-energy map group: each
        element is quantified from the energy that best excites it. The
        single-payload path (``run`` above) is untouched."""
        from axiomm.analysis.fusion import verify_registration
        cfg = self.config
        diagnostics: list[Diagnostic] = []
        diagnostics += verify_registration(group)   # raises RegistrationError on a grid mismatch

        # Normalize each map (I0 / dead-time), then cluster once on the highest-energy
        # map (broadest mid-Z contrast); the shared labels apply to every map.
        ems = sorted(group, key=lambda m: m.excitation_kev)
        payloads = {em.excitation_kev: (self._normalize_payload(em.payload, diagnostics)
                                        if cfg.normalize else em.payload) for em in ems}
        cluster_basis = (f"the {ems[-1].excitation_kev} keV map"
                         if cfg.fusion_clustering == "primary" or len(payloads) == 1
                         else "fused features from all energies")
        diagnostics.append(Diagnostic(
            "info", "fusion_engaged",
            f"multi-energy fusion over {sorted(payloads)} keV; clustering on {cluster_basis}."))
        # Default multi-energy behaviour is the conservative baseline: cluster on the primary
        # (highest-energy) map and apply NO automatic bridge cross-calibration
        # (``fusion_clustering="primary"`` + ``fusion_cross_cal="none"``). The cross-energy
        # comparability guard (#3, below) still puts the fused composition on a per-incident-photon
        # scale. Opting into fused clustering and/or the bridge is EXPERIMENTAL: a single per-energy
        # bridge scalar is a coarse model and fused clustering mixes energies' loadings, so the
        # cross-energy wt% is not guaranteed comparable. Flag that choice loudly (reports + saved
        # provenance), never silently.
        experimental = cfg.fusion_clustering == "fused" or cfg.fusion_cross_cal == "bridge"
        if experimental:
            diagnostics.append(Diagnostic(
                "warning", "fusion_experimental",
                "multi-energy fusion cross-energy composition is EXPERIMENTAL: fused clustering "
                "and/or bridge cross-calibration are active (the conservative default is "
                "primary-map clustering with no bridge), so the fused composition is not "
                "guaranteed to be on a common physical scale. Treat the composition as "
                "exploratory; phase identification is more robust than the cross-energy wt%."))
        primary = payloads[ems[-1].excitation_kev]

        reducer, n_components = self._resolve_reduction(cfg, diagnostics)
        clusterer = self._resolve_clustering(cfg, diagnostics)
        decomp, cluster_features = self._fused_cluster_features(
            payloads, primary, reducer, n_components, cfg, diagnostics)
        clustering = clusterer.cluster(cluster_features)
        means = compute_cluster_means(clustering, primary)
        diagnostics += list(decomp.diagnostics) + list(clustering.diagnostics) + list(means.diagnostics)

        result_kwargs = dict(
            label_map=np.asarray(clustering.label_map), cluster_means=means,
            clustering=clustering, decomposition=decomp, payload=primary,
            config=self._config_dict(), diagnostics=diagnostics,
        )
        reference = self._resolve_reference(cfg.reference)
        if reference is None:
            diagnostics.append(Diagnostic(
                "info", "minerals_skipped",
                "fusion needs a reference to quantify + match; clusters returned."))
            result_kwargs["provenance"] = self._provenance(
                cfg, decomp, clustering, reference, fusion_experimental=experimental)
            return PipelineResult(**result_kwargs)

        # Cross-energy comparability guard (#3): the fused QUANT uses a cross-map
        # normalisation (per-incident-photon, no per-map median) so exposure/monitor
        # differences cancel. Without a usable intensity_norm on every map (or with
        # normalization off) comparability cannot be established -> withhold the fused
        # COMPOSITION, keep clusters + per-acquisition evidence.
        quant_payloads: dict = {}
        quant_masks: dict = {}
        comparable = bool(cfg.normalize)
        for em in ems:
            qp, mask, ok = (self._normalize_cross_map(em.payload, diagnostics)
                            if cfg.normalize else (None, None, False))
            quant_payloads[em.excitation_kev] = qp
            quant_masks[em.excitation_kev] = mask
            comparable = comparable and ok
        if not comparable:
            diagnostics.append(Diagnostic(
                "warning", "fusion_composition_withheld",
                "cross-energy comparability could not be established (a map lacks a usable "
                "intensity_norm, or normalization is off), so fused composition is WITHHELD; "
                "clusters and per-acquisition evidence are returned. Normalise the maps "
                "comparably, or quantify each acquisition single-energy."))
            result_kwargs["provenance"] = self._provenance(
                cfg, decomp, clustering, reference, fusion_experimental=experimental)
            return PipelineResult(**result_kwargs)
        # Per-cluster support guard (#3 robustness): a cluster whose pixels are ALL
        # invalid-divisor in one arm has a NaN mean there, which the peak measurer would
        # reject — aborting the whole run on one dead region. Detect it and WITHHOLD
        # composition (clusters + evidence retained), consistent with the comparability
        # guard, rather than crashing. Retaining the UNAFFECTED clusters while withholding
        # only the affected ones is a deferred refinement (fusion design spec §13).
        labels_flat = np.asarray(clustering.labels).reshape(-1)
        missing = [(em.excitation_kev, int(cid))
                   for em in ems if quant_masks.get(em.excitation_kev) is not None
                   for cid in np.asarray(means.cluster_ids)
                   if (labels_flat == cid).any()
                   and not ((labels_flat == cid)
                            & np.asarray(quant_masks[em.excitation_kev], dtype=bool).reshape(-1)).any()]
        if missing:
            where = ", ".join(f"cluster {c} @ {e} keV" for e, c in missing)
            diagnostics.append(Diagnostic(
                "warning", "fusion_cluster_support_missing",
                f"{where}: a whole cluster has no valid (finite, positive-divisor) pixels in that "
                "map, so its fused composition cannot be measured there; composition is WITHHELD "
                "(clusters and per-acquisition evidence retained) rather than aborting the run. "
                "Supply comparable normalisation for every cluster, or quantify single-energy."))
            result_kwargs["provenance"] = self._provenance(
                cfg, decomp, clustering, reference, fusion_experimental=experimental)
            return PipelineResult(**result_kwargs)
        try:
            bundle = self._quantify_and_match_fused(
                group, quant_payloads, quant_masks, clustering, means, reference, cfg, diagnostics)
        except AnalysisDependencyError as exc:
            diagnostics.append(Diagnostic(
                "warning", "minerals_skipped_dependency",
                f"fused quantification + matching skipped: {exc}"))
            result_kwargs["provenance"] = self._provenance(
                cfg, decomp, clustering, reference, fusion_experimental=experimental)
            return PipelineResult(**result_kwargs)

        peaks, quant, reliability, minerals = bundle
        from axiomm.analysis.mineralogy.classify import classify_clusters
        policy = self._resolve_classification(cfg, diagnostics)
        labels = classify_clusters(minerals, reference, policy)
        phase_map = self._build_phase_map(clustering.label_map, labels)
        result_kwargs.update(
            peaks=peaks, quantification=quant, reliability=reliability,
            minerals=minerals, labels=labels, phase_map=phase_map,
            provenance=self._provenance(cfg, decomp, clustering, reference, policy,
                                        fusion_experimental=experimental),
        )
        return PipelineResult(**result_kwargs)

    def _fused_cluster_features(self, payloads, primary, reducer, n_components, cfg, diagnostics):
        """Return ``(primary_decomposition, features_to_cluster_on)``.

        ``fusion_clustering="primary"`` (the default) clusters on the highest-energy
        map alone — one segmentation, no cross-energy mixing. The opt-in
        ``"fused"`` mode instead clusters on the standardized, concatenated
        per-energy loadings, so a phase distinguished only at a low energy (e.g.
        P-rich apatite) can form its own cluster, at the cost of mixing energies'
        features. The reported decomposition is always the primary map's, for a
        consistent single-energy scree/factors view."""
        primary_decomp = reducer.decompose(primary, n_components=n_components)
        if cfg.fusion_clustering != "fused" or len(payloads) == 1:
            return primary_decomp, primary_decomp
        from types import SimpleNamespace
        blocks = []
        for e in sorted(payloads):
            d = (primary_decomp if payloads[e] is primary
                 else reducer.decompose(payloads[e], n_components=n_components))
            loadings = np.asarray(d.loadings, dtype=float)
            std = loadings.std(axis=0, keepdims=True)
            blocks.append((loadings - loadings.mean(axis=0, keepdims=True)) / np.where(std > 0, std, 1.0))
        features = SimpleNamespace(loadings=np.hstack(blocks), nav_shape=primary_decomp.nav_shape)
        diagnostics.append(Diagnostic(
            "info", "fusion_clustering_fused",
            f"clustered on fused features from {sorted(payloads)} keV "
            f"({features.loadings.shape[1]} combined components) so low-energy-only "
            "phases can separate."))
        return primary_decomp, features

    def _quantify_and_match_fused(self, group, payloads, quant_masks, clustering, primary_means,
                                  reference, cfg, diagnostics):
        from axiomm.analysis.fusion import (
            bridge_cross_calibration,
            fuse_peak_sets,
            fused_k_factors,
            select_energies,
        )
        from axiomm.analysis.fusion.selection import element_edge_kev
        # Eligible cations = union of each map's in-range cations (maps may span
        # different energy ranges / calibrations), then the usual honest filtering.
        ranges = [_signal_range(_signal_axis(p)) for p in payloads.values()]
        union = set().union(*[set(reference.cations_in_range(lo, hi)) for lo, hi in ranges])
        cations = self._filter_cations(
            sorted(union), reference, cfg, diagnostics,
            where=f"any map's range (union {[(round(lo, 2), round(hi, 2)) for lo, hi in ranges]} keV)")
        element_refs = reference.element_refs(cations)

        # Measure every cation on each energy's cluster means, each map on its OWN
        # spectral axis (never the primary's), so differently-calibrated maps integrate
        # at the right channels.
        per_energy_peaks = {
            e: tuple(measure_peaks(
                compute_cluster_means(clustering, payload, valid_mask=quant_masks.get(e)),
                _signal_axis(payload), reference))
            for e, payload in payloads.items()
        }
        # Choose each element's best-excited energy (pluggable policy), then fuse.
        source_energy, sel_diag = select_energies(
            group, element_refs, policy=self._resolve_energy_selection(cfg))
        diagnostics += sel_diag
        if source_energy.get(cfg.reference_element) is None:
            raise PayloadValidationError(
                f"reference_element {cfg.reference_element!r} is not excited by any supplied "
                "energy in the group; choose a reference measurable by one of the energies.")
        # Bridge-element cross-calibration: elements measurable at >1 energy set a
        # per-energy scale that rebalances the light-vs-mid-Z footing (folded into k).
        scale = None
        if cfg.fusion_cross_cal == "bridge":
            per_energy_net = {
                e: {ps.cluster_id: {m.label: m.net for m in ps.measurements} for ps in psets}
                for e, psets in per_energy_peaks.items()}
            cluster_weights = {int(cid): int(pc) for cid, pc
                               in zip(primary_means.cluster_ids, primary_means.pixel_counts, strict=True)}
            scale, cc_diag = bridge_cross_calibration(
                per_energy_net, element_refs, list(payloads),
                reference_energy=source_energy[cfg.reference_element], edge_fn=element_edge_kev,
                cluster_weights=cluster_weights, dispersion_limit=cfg.bridge_dispersion_limit,
                on_low_confidence=cfg.bridge_low_confidence)
            diagnostics += cc_diag
        fused_peaks = fuse_peak_sets(per_energy_peaks, source_energy)
        source_refs = [r for r in element_refs if source_energy.get(r.symbol) is not None]
        k = fused_k_factors(source_refs, source_energy, reference=cfg.reference_element, scale=scale)
        quant_elements = self._quant_elements(reference, source_refs)
        quant = quantify_cluster_means(list(fused_peaks), k, quant_elements, reference_name=reference.name)
        reliability = assess_cluster_reliability(
            list(quant), primary_means, config=cfg.reliability or ReliabilityConfig())
        from axiomm.analysis.mineralogy.match import MatchConfig, match_clusters
        minerals = match_clusters(list(quant), reference, reliabilities=list(reliability),
                                  config=cfg.match or MatchConfig())
        diagnostics += list(k.diagnostics)
        return fused_peaks, quant, reliability, minerals

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
                "classification": _stage_name(c.classification, "family_aware"),
                # effective settings that change the result — needed to reproduce a run
                "normalize": c.normalize,
                "exclude_elements": sorted(c.exclude_elements),
                "line_resolution_kev": c.line_resolution_kev,
                "fusion_clustering": c.fusion_clustering,
                "fusion_cross_cal": c.fusion_cross_cal,
                "bridge_dispersion_limit": c.bridge_dispersion_limit,
                "bridge_low_confidence": c.bridge_low_confidence,
                "energy_selection": _stage_name(c.energy_selection, "best_excited")}

    def _provenance(self, cfg, decomp, clustering, reference, policy=None,
                    *, fusion_experimental=None) -> dict:
        prov = {
            "tool": "axiomm.pipeline", "software_version": _AXIOMM_VERSION,
            "config": self._config_dict(),
            "decomposition": dict(decomp.provenance.params) if decomp.provenance else {},
            "clustering": dict(clustering.provenance.params) if clustering.provenance else {},
            "classification": policy.params() if policy is not None else None,
            "reference_name": getattr(reference, "name", None),
            "reference_version": getattr(reference, "version", None),
            "beam_energy_kev": cfg.beam_energy_kev,
        }
        if fusion_experimental is not None:
            # carried into saved/exported results so the experimental status travels with them
            prov["fusion_experimental"] = bool(fusion_experimental)
        return prov


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
