"""Quantification reliability gate.

A GMM cluster mean is a statistical average over possibly mixed pixels, so
it is not automatically a valid quantitative phase spectrum. This tool
overlays a per-element and per-cluster verdict on a ``QuantResult``: the
raw result is never modified, and no physical cause is asserted.

**Honest vocabulary (see finding P3/P4).** Nothing here is called
"quantitative": the upstream weight percents are an *uncorrected
theoretical sensitivity-ratio estimate* (see
:mod:`axiomm.analysis.quant.cliff_lorimer`), so the best a cluster can
earn is ``reportable_estimate``. The per-element ``count_floor`` is a
crude net-count screening floor — **not** an analytically defined limit
of detection or quantification. A statistically defined LOD/LOQ is
deferred; the raw gross counts, background and window width needed to
compute one are retained on the ``QuantResult`` (fields
``gross_intensities`` / ``background_per_channel`` / ``window_channels``).

Verdicts:

* element ``reportable`` / ``below_count_floor`` / ``invalid``
* cluster ``reportable_estimate`` / ``exploratory_only`` / ``invalid``

Non-finite or out-of-range inputs never produce ``reportable`` /
``reportable_estimate`` — they produce ``invalid``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic

ElementStatus = Literal["reportable", "below_count_floor", "invalid"]
ClusterStatus = Literal["reportable_estimate", "exploratory_only", "invalid"]

#: The admissible vocabularies, exported so serialization can validate against them.
ELEMENT_STATUSES: frozenset[str] = frozenset({"reportable", "below_count_floor", "invalid"})
CLUSTER_STATUSES: frozenset[str] = frozenset({"reportable_estimate", "exploratory_only", "invalid"})


def _is_int(value: object) -> bool:
    """True for a real integer, rejecting bool (``True`` is not a count/id)."""
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class ReliabilityConfig:
    """Reliability thresholds (documented example defaults; caller-set).

    ``count_floor`` is a crude global net-count screening floor;
    ``element_count_floors`` overrides it per element symbol. Neither is an
    analytical LOD/LOQ — see the module docstring.
    """

    min_pixel_count: int = 20
    max_heterogeneity: float = 0.15
    min_total_counts: float = 1.0e4
    count_floor: float = 50.0
    element_count_floors: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _is_int(self.min_pixel_count):
            raise PayloadValidationError(
                f"ReliabilityConfig.min_pixel_count must be an integer (not bool); "
                f"got {self.min_pixel_count!r}."
            )
        for name in ("min_pixel_count", "max_heterogeneity", "min_total_counts", "count_floor"):
            v = float(getattr(self, name))
            if not math.isfinite(v) or v < 0:
                raise PayloadValidationError(
                    f"ReliabilityConfig.{name} must be finite and >= 0; got {getattr(self, name)!r}."
                )
        for sym, v in self.element_count_floors.items():
            if not math.isfinite(float(v)) or float(v) < 0:
                raise PayloadValidationError(
                    f"ReliabilityConfig.element_count_floors[{sym!r}] must be finite and >= 0; got {v!r}."
                )

    def floor_for(self, symbol: str) -> float:
        """Net-count floor for ``symbol`` (per-element override or global)."""
        return float(self.element_count_floors.get(symbol, self.count_floor))


@dataclass
class ReliabilityReport:
    """Per-cluster reliability verdict, overlaying a QuantResult."""

    cluster_status: str
    element_status: Mapping[str, str]
    reasons: tuple[str, ...]
    cluster_id: int | None = None
    provenance: AnalysisProvenance | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _classify_element(net: float, floor: float) -> str:
    """Element verdict: non-finite/negative net is ``invalid``, never reportable."""
    if not math.isfinite(net) or net < 0:
        return "invalid"
    if net < floor:
        return "below_count_floor"
    return "reportable"


def assess_reliability(quant, *, pixel_count, heterogeneity, total_counts,
                       config: ReliabilityConfig | None = None,
                       cluster_id: int | None = None) -> ReliabilityReport:
    """Assess one cluster's quantification against the reliability thresholds.

    Non-finite or out-of-range ``pixel_count`` / ``heterogeneity`` /
    ``total_counts`` yield ``cluster_status == "invalid"``; a cluster with no
    element above its count floor can never be ``reportable_estimate``.
    """
    config = config or ReliabilityConfig()
    if cluster_id is None:
        cluster_id = getattr(quant, "cluster_id", None)

    element_status = {
        sym: _classify_element(float(net), config.floor_for(sym))
        for sym, net in quant.net_intensities.items()
    }

    invalid_reasons: list[str] = []
    reasons: list[str] = []

    # --- input validity (P2): non-finite / impossible values are invalid --
    if isinstance(pixel_count, bool):
        invalid_reasons.append(f"pixel_count must be an integer, not bool ({pixel_count!r})")
        pc = float("nan")
    else:
        pc = float(pixel_count)
        if not math.isfinite(pc) or pc < 0 or pc != int(pc):
            invalid_reasons.append(f"pixel_count not a non-negative integer ({pixel_count!r})")
    if total_counts is None or not math.isfinite(float(total_counts)) or float(total_counts) < 0:
        invalid_reasons.append(f"total_counts not finite and >= 0 ({total_counts!r})")
    het_undefined = heterogeneity is None or (
        isinstance(heterogeneity, float) and math.isnan(heterogeneity)
    )
    if not het_undefined:
        h = float(heterogeneity)
        if not math.isfinite(h) or h < 0:
            invalid_reasons.append(f"heterogeneity out of range ({heterogeneity!r})")
    if any(v == "invalid" for v in element_status.values()):
        invalid_reasons.append("one or more element net intensities are non-finite or negative")

    # --- threshold reasons (only meaningful once inputs are valid) --------
    if not invalid_reasons:
        if pc < config.min_pixel_count:
            reasons.append(f"pixel_count {int(pc)} < {config.min_pixel_count}")
        if het_undefined:
            reasons.append("heterogeneity undefined (empty/singleton cluster)")
        elif float(heterogeneity) > config.max_heterogeneity:
            reasons.append(f"heterogeneity {float(heterogeneity):.3f} > {config.max_heterogeneity}")
        if float(total_counts) < config.min_total_counts:
            reasons.append(f"total_counts {float(total_counts):.0f} < {config.min_total_counts:.0f}")
        # P3: no reportable element -> cannot be a reportable estimate
        if not any(v == "reportable" for v in element_status.values()):
            reasons.append("no element above its net-count floor")

    if invalid_reasons:
        cluster_status = "invalid"
    elif reasons:
        cluster_status = "exploratory_only"
    else:
        cluster_status = "reportable_estimate"

    diagnostics: list[Diagnostic] = []
    below = [s for s, v in element_status.items() if v == "below_count_floor"]
    bad = [s for s, v in element_status.items() if v == "invalid"]
    if below:
        diagnostics.append(
            Diagnostic("warning", "below_count_floor",
                       f"elements below the net-count screening floor: {below}")
        )
    if bad:
        diagnostics.append(
            Diagnostic("error", "invalid_element_intensity",
                       f"elements with non-finite or negative net intensity: {bad}")
        )
    if cluster_status == "invalid":
        diagnostics.append(
            Diagnostic("error", "invalid_cluster_inputs",
                       "cluster cannot be assessed: " + "; ".join(invalid_reasons))
        )
    elif cluster_status == "exploratory_only":
        diagnostics.append(
            Diagnostic("warning", "exploratory_cluster",
                       "cluster mean not accepted as a reportable estimate: " + "; ".join(reasons))
        )

    provenance = AnalysisProvenance(
        tool="quant", backend="reliability",
        params={
            "cluster_id": cluster_id,
            "assessed_pixel_count": pixel_count,
            "assessed_heterogeneity": heterogeneity,
            "assessed_total_counts": total_counts,
            "reference_element": getattr(quant, "reference_element", None),
            "min_pixel_count": config.min_pixel_count,
            "max_heterogeneity": config.max_heterogeneity,
            "min_total_counts": config.min_total_counts,
            "count_floor": config.count_floor,
            "element_count_floors": dict(config.element_count_floors),
        },
    )
    return ReliabilityReport(
        cluster_status=cluster_status, element_status=element_status,
        reasons=tuple(invalid_reasons + reasons), cluster_id=cluster_id,
        provenance=provenance, diagnostics=diagnostics,
    )


def assess_cluster_reliability(quant_results, cluster_means,
                               config: ReliabilityConfig | None = None,
                               ) -> tuple[ReliabilityReport, ...]:
    """Assess each cluster's quantification, aligning by explicit ``cluster_id``.

    Identity — not sequence position — links a ``QuantResult`` to its cluster
    mean, and the match is required to be **one-to-one** (P8): every intended
    cluster is represented exactly once. A missing, duplicate, or unknown
    ``cluster_id`` is an error rather than a silent mis-alignment. The returned
    reports follow ``cluster_means.cluster_ids`` order regardless of the order
    of ``quant_results``.
    """
    config = config or ReliabilityConfig()
    if cluster_means.heterogeneity is None or cluster_means.total_counts is None:
        raise PayloadValidationError(
            "cluster_means is not enriched with heterogeneity/total_counts; "
            "recompute with compute_cluster_means."
        )

    expected_ids = [int(c) for c in cluster_means.cluster_ids]
    id_to_idx = {cid: i for i, cid in enumerate(expected_ids)}
    if len(id_to_idx) != len(expected_ids):
        raise PayloadValidationError("cluster_means.cluster_ids contains duplicates.")

    # Collect each result's identity, rejecting missing / non-integer / duplicate.
    by_id: dict[int, object] = {}
    for qr in quant_results:
        if qr.cluster_id is None:
            raise PayloadValidationError(
                "quant result has no cluster_id; cannot verify cluster identity."
            )
        if not _is_int(qr.cluster_id):
            raise PayloadValidationError(
                f"quant result cluster_id must be an integer (not bool); got {qr.cluster_id!r}."
            )
        cid = int(qr.cluster_id)
        if cid in by_id:
            raise PayloadValidationError(
                f"duplicate quant result cluster_id {cid}; each cluster must appear once."
            )
        by_id[cid] = qr

    # Require an exact bijection between the two id sets.
    got = set(by_id)
    expected = set(expected_ids)
    unknown = sorted(got - expected)
    missing = sorted(expected - got)
    if unknown:
        raise PayloadValidationError(
            f"quant result cluster_id(s) {unknown} not found in cluster_means.cluster_ids."
        )
    if missing:
        raise PayloadValidationError(
            f"no quant result for expected cluster_id(s) {missing}; "
            "every cluster must be represented exactly once."
        )

    reports: list[ReliabilityReport] = []
    for cid in expected_ids:
        i = id_to_idx[cid]
        reports.append(
            assess_reliability(
                by_id[cid],
                pixel_count=int(cluster_means.pixel_counts[i]),
                heterogeneity=float(cluster_means.heterogeneity[i]),
                total_counts=float(cluster_means.total_counts[i]),
                config=config,
                cluster_id=cid,
            )
        )
    return tuple(reports)


__all__ = ["CLUSTER_STATUSES", "ELEMENT_STATUSES", "ClusterStatus", "ElementStatus",
           "ReliabilityConfig", "ReliabilityReport",
           "assess_cluster_reliability", "assess_reliability"]
