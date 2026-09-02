"""EDS/XRF quantification tools (stage two, S3c).

General quantification (not mineralogy-specific): theoretical
Cliff-Lorimer k-factors (S3c-1). Cliff-Lorimer wt% (S3c-2) and the
reliability gate (S3c-3) land in later sub-chunks. xraylib is imported
lazily by :func:`compute_k_factors`, so importing this package never
requires it.
"""

from __future__ import annotations

from axiomm.analysis.quant.kfactors import compute_k_factors
from axiomm.analysis.quant.models import KFactorSet
from axiomm.analysis.quant.io import read_kfactors, write_kfactors

__all__ = ["KFactorSet", "compute_k_factors", "read_kfactors", "write_kfactors"]
