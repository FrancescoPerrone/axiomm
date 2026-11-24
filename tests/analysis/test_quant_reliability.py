"""Tests for the quantification reliability gate (Stage two, S3c-3).

Includes the gate-review adversarial cases (findings P2, P3, P4, P8):
non-finite / out-of-range inputs must never yield a reportable verdict,
a no-signal cluster is never a reportable estimate, and per-cluster
identity is validated rather than sequence position.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.analysis.quant.models import QuantResult
from axiomm.analysis.quant.reliability import (
    ReliabilityConfig,
    ReliabilityReport,
    assess_reliability,
)


def _quant(nets, cluster_id=None):
    return QuantResult(net_intensities=nets, wt_percent_element={}, wt_percent_oxide={},
                       reference_element="Si", cluster_id=cluster_id)


def test_config_and_report_construct():
    cfg = ReliabilityConfig()
    assert cfg.count_floor == 50.0
    assert cfg.floor_for("Si") == 50.0
    r = ReliabilityReport(cluster_status="reportable_estimate",
                          element_status={"Si": "reportable"}, reasons=())
    assert r.cluster_status == "reportable_estimate"


def test_reliability_config_defaults_are_frozen():
    # Baseline freeze: lock the default thresholds so a change is deliberate.
    cfg = ReliabilityConfig()
    assert cfg.min_pixel_count == 20
    assert cfg.max_heterogeneity == 0.15
    assert cfg.min_total_counts == 1.0e4
    assert cfg.count_floor == 50.0
    assert dict(cfg.element_count_floors) == {}


def test_reliability_floor_uses_counting_nets_when_given():
    # #4: the net-count floor is a counting-statistics screen, so it reads the RAW source
    # counts (counting_nets), not the monitor-normalized quant net. The two disagree on
    # purpose here to prove which one the floor uses.
    r = assess_reliability(_quant({"Si": 1.0}), pixel_count=100, heterogeneity=0.05,
                           total_counts=1.0e5, counting_nets={"Si": 500.0})
    assert r.element_status["Si"] == "reportable"                  # raw counts clear the floor
    assert r.provenance.params["counting_basis"] == "source_raw_counts"
    r2 = assess_reliability(_quant({"Si": 999.0}), pixel_count=100, heterogeneity=0.05,
                            total_counts=1.0e5, counting_nets={"Si": 1.0})
    assert r2.element_status["Si"] == "below_count_floor"          # raw counts below the floor
    # default (no counting_nets) still grades the quant net and records the legacy basis
    r3 = assess_reliability(_quant({"Si": 999.0}), pixel_count=100, heterogeneity=0.05,
                            total_counts=1.0e5)
    assert r3.element_status["Si"] == "reportable"
    assert r3.provenance.params["counting_basis"] == "quant_net"


def test_reliability_thresholds_are_inclusive_at_the_boundary():
    # Exactly at every default threshold -> reportable_estimate.
    r = assess_reliability(_quant({"Si": 50.0}), pixel_count=20,
                           heterogeneity=0.15, total_counts=1.0e4)
    assert r.cluster_status == "reportable_estimate"
    assert r.element_status["Si"] == "reportable"


@pytest.mark.parametrize("pc,het,tc", [
    (19, 0.15, 1.0e4),                                   # one below pixel floor
    (20, math.nextafter(0.15, math.inf), 1.0e4),         # just over heterogeneity
    (20, 0.15, math.nextafter(1.0e4, -math.inf)),        # just under total counts
])
def test_reliability_boundary_misses_are_exploratory(pc, het, tc):
    r = assess_reliability(_quant({"Si": 50.0}), pixel_count=pc,
                           heterogeneity=het, total_counts=tc)
    assert r.cluster_status == "exploratory_only"


def test_si_just_below_floor_is_below_count_floor_and_exploratory():
    r = assess_reliability(_quant({"Si": math.nextafter(50.0, -math.inf)}),
                           pixel_count=20, heterogeneity=0.15, total_counts=1.0e4)
    assert r.element_status["Si"] == "below_count_floor"
    assert r.cluster_status == "exploratory_only"   # its only element is below floor


def test_element_below_floor_flagged():
    r = assess_reliability(_quant({"Si": 100.0, "K": 6.0}), pixel_count=100,
                           heterogeneity=0.05, total_counts=1e5)
    assert r.element_status["K"] == "below_count_floor"
    assert r.element_status["Si"] == "reportable"
    assert r.cluster_status == "reportable_estimate"


def test_per_element_floor_override():
    cfg = ReliabilityConfig(element_count_floors={"K": 5.0})
    r = assess_reliability(_quant({"Si": 100.0, "K": 6.0}), pixel_count=100,
                           heterogeneity=0.05, total_counts=1e5, config=cfg)
    assert r.element_status["K"] == "reportable"   # 6 >= per-element floor 5


def test_clean_cluster_is_reportable_estimate():
    r = assess_reliability(_quant({"Si": 100.0}), pixel_count=100,
                           heterogeneity=0.05, total_counts=1e5)
    assert r.cluster_status == "reportable_estimate" and r.reasons == ()


# --- P2: non-finite / out-of-range inputs are invalid, never reportable ----
@pytest.mark.parametrize("nets,pc,het,tc", [
    ({"K": float("nan")}, 100, 0.05, 1e5),
    ({"K": float("inf")}, 100, 0.05, 1e5),
    ({"K": -5.0}, 100, 0.05, 1e5),
    ({"Si": 100.0}, 100, 0.05, float("nan")),
    ({"Si": 100.0}, 100, 0.05, float("inf")),
    ({"Si": 100.0}, -5, 0.05, 1e5),
    ({"Si": 100.0}, 100, float("inf"), 1e5),
    ({"Si": 100.0}, 100, -0.1, 1e5),
])
def test_nonfinite_inputs_are_invalid(nets, pc, het, tc):
    r = assess_reliability(_quant(nets), pixel_count=pc, heterogeneity=het, total_counts=tc)
    assert r.cluster_status == "invalid"
    assert "reportable" not in set(r.element_status.values()) or r.cluster_status == "invalid"


def test_invalid_config_rejected():
    for bad in (dict(count_floor=float("nan")), dict(min_pixel_count=-1),
                dict(max_heterogeneity=float("inf")), dict(min_total_counts=-1.0),
                dict(element_count_floors={"K": float("nan")})):
        with pytest.raises(PayloadValidationError):
            ReliabilityConfig(**bad)


# --- P3: a no-signal cluster is never a reportable estimate ----------------
def test_no_signal_cluster_not_reportable():
    r = assess_reliability(_quant({"Si": 0.0, "Fe": 0.0}), pixel_count=100,
                           heterogeneity=0.05, total_counts=1e5)
    assert r.cluster_status == "exploratory_only"
    assert any("no element above" in reason for reason in r.reasons)


@pytest.mark.parametrize("kw,frag", [
    (dict(pixel_count=5, heterogeneity=0.05, total_counts=1e5), "pixel_count"),
    (dict(pixel_count=100, heterogeneity=0.4, total_counts=1e5), "heterogeneity"),
    (dict(pixel_count=100, heterogeneity=0.05, total_counts=100.0), "total_counts"),
    (dict(pixel_count=100, heterogeneity=float("nan"), total_counts=1e5), "heterogeneity undefined"),
])
def test_cluster_flagged_exploratory(kw, frag):
    r = assess_reliability(_quant({"Si": 100.0}), **kw)
    assert r.cluster_status == "exploratory_only"
    assert any(frag in reason for reason in r.reasons)


def test_batch_pairs_with_enriched_cluster_means():
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    from axiomm.analysis.quant import assess_cluster_reliability
    cms = ClusterMeanSpectra(
        means=np.ones((2, 3)), pixel_counts=np.array([100, 5]),
        cluster_ids=np.array([0, 1]), n_clusters=2,
        heterogeneity=np.array([0.05, 0.05]), total_counts=np.array([1e5, 1e5]),
    )
    reports = assess_cluster_reliability(
        [_quant({"Si": 100.0}, cluster_id=0), _quant({"Si": 100.0}, cluster_id=1)], cms)
    assert reports[0].cluster_status == "reportable_estimate"
    assert reports[1].cluster_status == "exploratory_only"   # pixel_count 5 < 20


# --- P8: batch aligns by cluster_id, not sequence position -----------------
def test_batch_aligns_by_cluster_id_when_reordered():
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    from axiomm.analysis.quant import assess_cluster_reliability
    cms = ClusterMeanSpectra(
        means=np.ones((2, 3)), pixel_counts=np.array([100, 5]),
        cluster_ids=np.array([0, 1]), n_clusters=2,
        heterogeneity=np.array([0.05, 0.05]), total_counts=np.array([1e5, 1e5]),
    )
    # cluster 1 (5 px) passed first; identity must still map it to pixel_count 5
    reports = assess_cluster_reliability(
        [_quant({"Si": 100.0}, cluster_id=1), _quant({"Si": 100.0}, cluster_id=0)], cms)
    by_id = {r.cluster_id: r.cluster_status for r in reports}
    assert by_id[0] == "reportable_estimate"
    assert by_id[1] == "exploratory_only"


def test_batch_missing_cluster_id_raises():
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    from axiomm.analysis.quant import assess_cluster_reliability
    cms = ClusterMeanSpectra(
        means=np.ones((1, 3)), pixel_counts=np.array([100]),
        cluster_ids=np.array([0]), n_clusters=1,
        heterogeneity=np.array([0.05]), total_counts=np.array([1e5]),
    )
    with pytest.raises(PayloadValidationError, match="cluster_id"):
        assess_cluster_reliability([_quant({"Si": 100.0})], cms)


def test_batch_unknown_cluster_id_raises():
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    from axiomm.analysis.quant import assess_cluster_reliability
    cms = ClusterMeanSpectra(
        means=np.ones((1, 3)), pixel_counts=np.array([100]),
        cluster_ids=np.array([0]), n_clusters=1,
        heterogeneity=np.array([0.05]), total_counts=np.array([1e5]),
    )
    with pytest.raises(PayloadValidationError, match="not found"):
        assess_cluster_reliability([_quant({"Si": 100.0}, cluster_id=9)], cms)


def test_batch_on_unenriched_raises():
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    from axiomm.analysis.quant import assess_cluster_reliability
    cms = ClusterMeanSpectra(means=np.ones((1, 3)), pixel_counts=np.array([1]),
                             cluster_ids=np.array([0]), n_clusters=1)
    with pytest.raises(PayloadValidationError, match="enrich"):
        assess_cluster_reliability([_quant({"Si": 100.0}, cluster_id=0)], cms)


# --- finding 2: one-to-one batch identity (dup / missing / exactly-once) ----

def _two_cluster_means():
    from axiomm.analysis.clustering.models import ClusterMeanSpectra
    return ClusterMeanSpectra(
        means=np.ones((2, 3)), pixel_counts=np.array([100, 100]),
        cluster_ids=np.array([0, 1]), n_clusters=2,
        heterogeneity=np.array([0.05, 0.05]), total_counts=np.array([1e5, 1e5]),
    )


def test_batch_duplicate_cluster_id_raises():
    from axiomm.analysis.quant import assess_cluster_reliability
    with pytest.raises(PayloadValidationError, match="duplicate"):
        assess_cluster_reliability(
            [_quant({"Si": 100.0}, cluster_id=0), _quant({"Si": 100.0}, cluster_id=0)],
            _two_cluster_means())


def test_batch_missing_expected_cluster_raises():
    from axiomm.analysis.quant import assess_cluster_reliability
    with pytest.raises(PayloadValidationError, match="every cluster"):
        assess_cluster_reliability([_quant({"Si": 100.0}, cluster_id=0)], _two_cluster_means())


def test_batch_requires_exact_bijection():
    from axiomm.analysis.quant import assess_cluster_reliability
    reports = assess_cluster_reliability(
        [_quant({"Si": 100.0}, cluster_id=1), _quant({"Si": 100.0}, cluster_id=0)],
        _two_cluster_means())
    assert [r.cluster_id for r in reports] == [0, 1]   # cluster_means order


# --- finding 7: integral, non-Boolean min_pixel_count and cluster IDs -------

def test_bool_min_pixel_count_rejected():
    with pytest.raises(PayloadValidationError, match="min_pixel_count"):
        ReliabilityConfig(min_pixel_count=True)


def test_float_min_pixel_count_rejected():
    with pytest.raises(PayloadValidationError, match="min_pixel_count"):
        ReliabilityConfig(min_pixel_count=20.0)


def test_bool_pixel_count_is_invalid():
    r = assess_reliability(_quant({"Si": 100.0}), pixel_count=True,
                           heterogeneity=0.02, total_counts=1e5)
    assert r.cluster_status == "invalid"


def test_batch_bool_cluster_id_rejected():
    from axiomm.analysis.quant import assess_cluster_reliability
    with pytest.raises(PayloadValidationError, match="integer"):
        assess_cluster_reliability([_quant({"Si": 100.0}, cluster_id=True)], _two_cluster_means())
