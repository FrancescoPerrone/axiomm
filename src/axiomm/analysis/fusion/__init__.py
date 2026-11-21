"""Multi-energy fusion (stage two, S8) — optional, additive, N-energy.

Combine several co-registered maps of one region, acquired at different
excitation energies, so each element is measured from the energy that best
excites it. Opt-in: the single-energy pipeline is unchanged, and a one-map group
makes fusion the identity. This chunk (S8.1) ships the group model and the
registration contract; selection, cross-energy normalization and the pipeline
hook follow.
"""

from __future__ import annotations

from axiomm.analysis.fusion.models import EnergyMap, MultiEnergyMapGroup
from axiomm.analysis.fusion.registration import verify_registration

__all__ = ["EnergyMap", "MultiEnergyMapGroup", "verify_registration"]
