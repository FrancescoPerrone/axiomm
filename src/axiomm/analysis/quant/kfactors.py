"""Theoretical fluorescence-sensitivity ratios ("k-factors") from xraylib.

**Scientific caveat.** These "k-factors" are ratios of *theoretical
fluorescence cross-sections* (xraylib fundamental parameters) at the
excitation energy only. They correct for element-dependent fluorescence
yield / line branching, and nothing else: **detector efficiency and
geometry, absorption/self-absorption, secondary fluorescence and other
matrix effects, sample thickness, and the acquisition regime are all
omitted.** The downstream weight percents are therefore an *uncorrected
theoretical sensitivity-ratio estimate*, not a validated quantitative
composition — see :mod:`axiomm.analysis.quant.cliff_lorimer` and
``docs/user/analysis.md`` (Scientific assumptions & limitations).

xraylib is imported lazily behind :func:`_import_xraylib` (monkeypatchable
in tests); its absence raises :class:`AnalysisDependencyError`. Excitation
energy is required — no baked beamline value.
"""

from __future__ import annotations

import math

from axiomm.analysis.errors import AnalysisDependencyError, PayloadValidationError
from axiomm.analysis.models import AnalysisProvenance, Diagnostic
from axiomm.analysis.quant.models import KFactorSet

_LINE_ATTR = {"Ka": "KA_LINE", "La": "LA_LINE"}

_PHYSICAL_MODEL = (
    "uncorrected theoretical fluorescence cross-section ratio; omits "
    "detector efficiency/geometry, absorption/self-absorption, matrix "
    "effects, sample thickness, and acquisition regime"
)


def _import_xraylib():
    """Import xraylib (isolated so tests can monkeypatch it)."""
    import xraylib

    return xraylib


def compute_k_factors(elements, *, excitation_kev: float, reference: str = "Si") -> KFactorSet:
    """Theoretical fluorescence-sensitivity ratios ``k_{i,ref} = S_ref / S_i``.

    See the module docstring for the physical model these ratios do and do
    not include.
    """
    els = list(elements)
    symbols = [e.symbol for e in els]

    if not els:
        raise PayloadValidationError("no elements supplied.")
    duplicates = {s for s in symbols if symbols.count(s) > 1}
    if duplicates:
        raise PayloadValidationError(f"duplicate element symbols: {sorted(duplicates)}.")
    for el in els:
        if el.emission_line not in _LINE_ATTR:
            raise PayloadValidationError(
                f"element {el.symbol!r} has unsupported emission_line "
                f"{el.emission_line!r} (expected one of {sorted(_LINE_ATTR)})."
            )
        if el.atomic_number <= 0:
            raise PayloadValidationError(
                f"element {el.symbol!r} has non-positive atomic_number {el.atomic_number}."
            )
    if not (excitation_kev > 0 and excitation_kev == excitation_kev and excitation_kev != float("inf")):
        raise PayloadValidationError(f"excitation_kev must be finite and > 0; got {excitation_kev}.")
    if reference not in symbols:
        raise PayloadValidationError(f"reference {reference!r} not among elements {symbols}.")

    try:
        xl = _import_xraylib()
    except ImportError as exc:
        raise AnalysisDependencyError(
            "xraylib is required for theoretical k-factors; install the "
            "[quant] extra (note: xraylib often needs conda)."
        ) from exc

    xl.XRayInit()
    diagnostics: list[Diagnostic] = []
    sensitivities: dict[str, float] = {}
    line_method: dict[str, str] = {}
    for el in els:
        line = getattr(xl, _LINE_ATTR[el.emission_line])
        try:
            s = xl.CS_FluorLine_Kissel(el.atomic_number, line, excitation_kev)
            method = "CS_FluorLine_Kissel"
        except ValueError:
            # xraylib has no Kissel partial-cross-section for this Z/line at
            # this energy: fall back to the total-line cross-section and
            # record that the fallback (not Kissel) was used.
            s = xl.CS_FluorLine(el.atomic_number, line, excitation_kev)
            method = "CS_FluorLine"
            diagnostics.append(
                Diagnostic("info", "kfactor_fallback",
                           f"{el.symbol!r}: Kissel cross-section unavailable; "
                           f"used CS_FluorLine instead.")
            )
        sensitivities[el.symbol] = float(s)
        line_method[el.symbol] = method

    # A non-positive or non-finite sensitivity yields a meaningless k-factor.
    # Emitting NaN here only defers the failure to quantification / strict
    # serialization, which both reject it (finding 8): fail loudly and now.
    bad = sorted(
        sym for sym, s in sensitivities.items() if not (math.isfinite(s) and s > 0)
    )
    if bad:
        raise PayloadValidationError(
            f"xraylib returned a non-positive or non-finite fluorescence "
            f"sensitivity for element(s) {bad} at {excitation_kev} keV; "
            "cannot form k-factors. Check the excitation energy and emission lines."
        )

    s_ref = sensitivities[reference]
    k_factors: dict[str, float] = {sym: s_ref / s for sym, s in sensitivities.items()}

    all_kissel = all(m == "CS_FluorLine_Kissel" for m in line_method.values())
    provenance = AnalysisProvenance(
        tool="quant",
        backend="kfactors_theoretical",
        params={
            "method": ("xraylib FP, Kissel cross-sections" if all_kissel
                       else "xraylib FP, mixed (Kissel + CS_FluorLine fallback)"),
            "line_method": dict(line_method),
            "physical_model": _PHYSICAL_MODEL,
            "xraylib_version": getattr(xl, "__version__", "unknown"),
            "xraylib_backend": "xraylib",
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
