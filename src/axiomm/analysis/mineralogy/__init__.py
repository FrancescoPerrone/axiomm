"""Mineralogy tools (stage two, S3).

Sub-chunk S3a: the reference library. Importing this package registers
the default preset ``"minerals_default_v1"`` in
:data:`axiomm.analysis.reference.references` so ``get_reference`` resolves
it. Later sub-chunks add peak identification (S3b), Cliff-Lorimer
quantification (S3c), and structural matching + layered labels (S3d).
"""

from __future__ import annotations

from axiomm.analysis.reference import register_reference
from axiomm.analysis.mineralogy.reference import (
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.mineralogy._default_library import MINERALOGY_DEFAULT_V1

register_reference("minerals_default_v1", lambda: MINERALOGY_DEFAULT_V1)

__all__ = [
    "ElementRef",
    "MINERALOGY_DEFAULT_V1",
    "MineralEndmember",
    "MineralogyReference",
]
