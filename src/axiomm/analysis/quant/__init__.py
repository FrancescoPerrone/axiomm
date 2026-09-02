"""EDS/XRF quantification tools (stage two, S3c).

General quantification (not mineralogy-specific): theoretical
Cliff-Lorimer k-factors (S3c-1) and Cliff-Lorimer element/oxide wt%
(S3c-2). The reliability gate (S3c-3) lands in a later sub-chunk. xraylib
is imported lazily by :func:`compute_k_factors`, so importing this package
never requires it.
"""

from __future__ import annotations

from axiomm.analysis.quant.kfactors import compute_k_factors
from axiomm.analysis.quant.cliff_lorimer import quantify, quantify_cluster_means
from axiomm.analysis.quant.models import KFactorSet, QuantResult
from axiomm.analysis.quant.reliability import (
    ReliabilityConfig,
    ReliabilityReport,
    assess_cluster_reliability,
    assess_reliability,
)
from axiomm.analysis.quant.io import read_kfactors, write_kfactors

__all__ = [
    "KFactorSet",
    "QuantResult",
    "ReliabilityConfig",
    "ReliabilityReport",
    "assess_cluster_reliability",
    "assess_reliability",
    "compute_k_factors",
    "quantify",
    "quantify_cluster_means",
    "read_kfactors",
    "write_kfactors",
]
