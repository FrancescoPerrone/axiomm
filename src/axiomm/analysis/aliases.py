"""Keyword-alias resolution for the plain-English public API.

Public functions gain plain-English aliases additively. At a function boundary the
canonical and alias parameters both default to :data:`UNSET` (an omission sentinel),
so "supplied" is distinguishable from "equal to the default" (a plain default cannot
tell the two apart). :func:`resolve_alias` returns whichever was supplied, raises a
named error when **both** are, and falls back to ``default`` (or raises, if the value
is required) when neither is.
"""

from __future__ import annotations

from axiomm.analysis.errors import PayloadValidationError


class _Unset:
    __slots__ = ()

    def __repr__(self) -> str:
        return "UNSET"


#: Sentinel for an omitted keyword argument (distinct from any real default).
UNSET = _Unset()


def resolve_alias(canonical_name, canonical, alias_name, alias, *, default=UNSET):
    """Return the one value supplied for a ``canonical``/``alias`` pair.

    Both supplied → :class:`PayloadValidationError` naming both. Neither → ``default``
    (or a named error if ``default`` is :data:`UNSET`, i.e. the value is required).
    """
    if canonical is not UNSET and alias is not UNSET:
        raise PayloadValidationError(f"pass either {canonical_name!r} or {alias_name!r}, not both.")
    if canonical is not UNSET:
        return canonical
    if alias is not UNSET:
        return alias
    if default is UNSET:
        raise PayloadValidationError(f"{canonical_name!r} (or {alias_name!r}) is required.")
    return default


__all__ = ["UNSET", "resolve_alias"]
