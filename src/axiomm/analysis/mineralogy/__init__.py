"""Mineralogy tools (stage two, S3).

Sub-chunk S3a: the reference library. Importing this package registers
the default preset ``"minerals_default_v1"`` in
:data:`axiomm.analysis.reference.references` so ``get_reference`` resolves
it. Later sub-chunks add peak identification (S3b), Cliff-Lorimer
quantification (S3c), and structural matching + layered labels (S3d).
"""

from __future__ import annotations

from axiomm.analysis.mineralogy._default_library import MINERALOGY_DEFAULT_V1
from axiomm.analysis.mineralogy._default_library_v2 import (
    MINERALOGY_DEFAULT_V2,
    MINERALOGY_V2_BASIS_AUDIT,
)
from axiomm.analysis.mineralogy.reference import (
    COMPOSITION_BASES,
    ElementRef,
    MineralEndmember,
    MineralogyReference,
)
from axiomm.analysis.reference import register_reference

register_reference("minerals_default_v1", lambda: MINERALOGY_DEFAULT_V1)
register_reference("minerals_default_v2", lambda: MINERALOGY_DEFAULT_V2)

__all__ = [
    "COMPOSITION_BASES",
    "MINERALOGY_DEFAULT_V1",
    "MINERALOGY_DEFAULT_V2",
    "MINERALOGY_V2_BASIS_AUDIT",
    "ElementRef",
    "MineralEndmember",
    "MineralogyReference",
]
