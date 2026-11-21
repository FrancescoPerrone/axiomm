"""Registration contract for multi-energy fusion (stage two, S8 §5).

Fusion assumes the maps share a spatial grid, and **verifies** it — it never
resamples or aligns. :func:`verify_registration` checks every map against the
first: same navigation-axis count and sizes, and matching nav scale/offset
within tolerance. A mismatch is a loud, named :class:`RegistrationError`
(``strict``, the default) or a warning diagnostic (``strict=False``), never a
silent fusion of mis-aligned pixels.
"""

from __future__ import annotations

from axiomm.analysis.errors import RegistrationError
from axiomm.analysis.models import Diagnostic


def _nav_axes(payload):
    return [a for a in payload.axes if a.role == "navigation"]


def verify_registration(group, *, scale_rtol: float = 1e-3, offset_atol: float = 1e-3,
                        strict: bool = True) -> list[Diagnostic]:
    """Check every map in ``group`` shares the navigation grid of the first.

    ``scale_rtol`` is a relative tolerance on each nav axis' scale; ``offset_atol``
    an absolute tolerance (in the axis' units) on its offset. On a mismatch this
    raises :class:`RegistrationError` when ``strict`` (the default), or returns a
    ``registration_mismatch`` warning per offending map when ``strict=False``.
    Returns a ``registration_verified`` info diagnostic when all maps agree (a
    single-map group trivially verifies).
    """
    maps = list(group)
    ref = maps[0].payload
    ref_nav = _nav_axes(ref)
    diagnostics: list[Diagnostic] = []

    for em in maps[1:]:
        nav = _nav_axes(em.payload)
        problems: list[str] = []
        if len(nav) != len(ref_nav):
            problems.append(f"navigation-axis count {len(nav)} != {len(ref_nav)}")
        else:
            for i, (a, b) in enumerate(zip(ref_nav, nav, strict=True)):
                if a.size != b.size:
                    problems.append(f"nav axis {i} ({a.name}) size {b.size} != {a.size}")
                if (a.scale is not None and b.scale is not None
                        and abs(a.scale - b.scale) > scale_rtol * max(abs(a.scale), 1e-12)):
                    problems.append(f"nav axis {i} ({a.name}) scale {b.scale} != {a.scale}")
                if abs(float(a.offset) - float(b.offset)) > offset_atol:
                    problems.append(f"nav axis {i} ({a.name}) offset {b.offset} != {a.offset}")
        if problems:
            msg = (f"map at {em.excitation_kev} keV is not co-registered with the "
                   f"{maps[0].excitation_kev} keV reference: " + "; ".join(problems))
            if strict:
                raise RegistrationError(msg)
            diagnostics.append(Diagnostic("warning", "registration_mismatch", msg))

    if not diagnostics:
        grid = "×".join(str(a.size) for a in ref_nav)
        energies = [m.excitation_kev for m in maps]
        diagnostics.append(Diagnostic(
            "info", "registration_verified",
            f"{len(maps)} map(s) at {energies} keV share the navigation grid ({grid})."))
    return diagnostics


__all__ = ["verify_registration"]
