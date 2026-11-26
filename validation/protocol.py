"""Sealed scenario grid, seeds and pilot/held-out allocation — committed before results.

The seeds below define the PILOT set. The held-out set uses a DISJOINT seed range
(``HELDOUT_SEED_BASE``) and is NOT executed in the pilot. ``manifest_hash()`` pins
the entire configuration so a later run can prove it used the sealed protocol.
"""
from __future__ import annotations

import hashlib
import json

# -- synthetic axis + lines ---------------------------------------------------
AXIS = {"n_channels": 1600, "scale_kev": 0.01, "offset_kev": 0.0}   # 0 .. 15.99 keV
LINE_SIGMA_KEV = 0.02           # narrow: ~3 sigma within the 0.06 keV half-window
BACKGROUND_PER_CH = 5.0
# Well-separated lines (keV): far apart relative to the 0.12 keV window + flanks.
LINES = [("Si", 1.740), ("Ca", 3.690), ("Fe", 6.400)]

# -- C1 high-signal strata (by injected peak AREA = total counts) -------------
# Chosen so systematic bias, not Poisson noise, governs the mean signed error.
HIGH_SIGNAL_STRATA = {"S_5k": 5000.0, "S_20k": 20000.0, "S_100k": 100000.0}
N_REPLICATES = 200              # independent Poisson realisations per stratum

# -- seed allocation (pilot vs disjoint held-out) -----------------------------
PILOT_SEED_BASE = 1_000_000
HELDOUT_SEED_BASE = 9_000_000   # reserved; untouched by the pilot

# -- C2 noisy-blank config ----------------------------------------------------
C2_BLANK_REPLICATES = 500
C2_BLANK_SEED_BASE = 2_000_000

# -- C3 preregistered positive intensity vector (named Si-referenced ratios) --
C3_EXCITATION_KEV = 15.0
C3_REFERENCE = "Si"
C3_NET_INTENSITIES = {"Mg": 800.0, "Al": 1200.0, "Si": 5000.0, "Ca": 3000.0, "Fe": 2500.0}
C3_RATIOS = [("Ca", "Si"), ("Fe", "Si"), ("Mg", "Si"), ("Al", "Si")]
C3_RTOL = 1e-10
C3_ATOL = 1e-12


def stratum_seed(base: int, stratum_index: int, rep: int) -> int:
    return int(base) + int(stratum_index) * 100_000 + int(rep)


def manifest_hash() -> str:
    payload = {
        "AXIS": AXIS, "LINE_SIGMA_KEV": LINE_SIGMA_KEV,
        "BACKGROUND_PER_CH": BACKGROUND_PER_CH, "LINES": LINES,
        "HIGH_SIGNAL_STRATA": HIGH_SIGNAL_STRATA, "N_REPLICATES": N_REPLICATES,
        "PILOT_SEED_BASE": PILOT_SEED_BASE, "HELDOUT_SEED_BASE": HELDOUT_SEED_BASE,
        "C2_BLANK_REPLICATES": C2_BLANK_REPLICATES, "C2_BLANK_SEED_BASE": C2_BLANK_SEED_BASE,
        "C3_EXCITATION_KEV": C3_EXCITATION_KEV, "C3_REFERENCE": C3_REFERENCE,
        "C3_NET_INTENSITIES": C3_NET_INTENSITIES, "C3_RATIOS": C3_RATIOS,
        "C3_RTOL": C3_RTOL, "C3_ATOL": C3_ATOL,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
