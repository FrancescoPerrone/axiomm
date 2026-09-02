"""Theoretical Cliff-Lorimer k-factors from xraylib fundamental parameters.

Standalone quantification tool. xraylib is imported lazily behind
:func:`_import_xraylib` (monkeypatchable in tests); its absence raises a
clear :class:`AnalysisDependencyError`. Excitation energy is required —
no baked beamline value.
"""

from __future__ import annotations

from axiomm.analysis.errors import AnalysisDependencyError, PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.models import KFactorSet

_LINE_ATTR = {"Ka": "KA_LINE", "La": "LA_LINE"}


def _import_xraylib():
    """Import xraylib (isolated so tests can monkeypatch it)."""
    import xraylib

    return xraylib


def compute_k_factors(elements, *, excitation_kev: float, reference: str = "Si") -> KFactorSet:
    """Theoretical Cliff-Lorimer k-factors ``k_{i,ref} = S_ref / S_i``."""
    els = list(elements)
    symbols = [e.symbol for e in els]

    if excitation_kev <= 0:
        raise PayloadValidationError(
            f"excitation_kev must be > 0; got {excitation_kev}."
        )
    if reference not in symbols:
        raise PayloadValidationError(
            f"reference {reference!r} not among elements {symbols}."
        )

    try:
        xl = _import_xraylib()
    except ImportError as exc:
        raise AnalysisDependencyError(
            "xraylib is required for theoretical k-factors; install the "
            "[quant] extra (note: xraylib often needs conda)."
        ) from exc

    xl.XRayInit()
    sensitivities: dict[str, float] = {}
    for el in els:
        line = getattr(xl, _LINE_ATTR[el.emission_line])
        try:
            s = xl.CS_FluorLine_Kissel(el.atomic_number, line, excitation_kev)
        except Exception:  # noqa: BLE001 — xraylib call boundary; fall back
            s = xl.CS_FluorLine(el.atomic_number, line, excitation_kev)
        sensitivities[el.symbol] = float(s)

    s_ref = sensitivities.get(reference, 0.0)
    if s_ref <= 0:
        raise PayloadValidationError(
            f"reference {reference!r} has non-positive sensitivity {s_ref}."
        )

    diagnostics: list[Diagnostic] = []
    k_factors: dict[str, float] = {}
    for sym, s in sensitivities.items():
        if s > 0:
            k_factors[sym] = s_ref / s
        else:
            k_factors[sym] = float("nan")
            diagnostics.append(
                Diagnostic(
                    "warning",
                    "zero_sensitivity",
                    f"element {sym!r} has non-positive sensitivity; k-factor is NaN.",
                )
            )

    provenance = AnalysisProvenance(
        tool="quant",
        backend="kfactors_theoretical",
        params={
            "method": "theoretical (xraylib FP, Kissel cross-sections)",
            "xraylib_version": getattr(xl, "__version__", "unknown"),
            "excitation_kev": excitation_kev,
            "reference": reference,
        },
    )
    return KFactorSet(
        k_factors=k_factors,
        sensitivities=sensitivities,
        reference_element=reference,
        excitation_kev=excitation_kev,
        provenance=provenance,
        diagnostics=diagnostics,
    )


__all__ = ["compute_k_factors"]
