"""Basis-aware conversion to molar/element proportions (S3d core correctness).

Every cluster and every reference endmember is converted to the **same**
molar/element-proportion basis before scoring, so mass fractions are never
compared to atom-count (stoichiometric) vectors. The conversion depends on the
declared basis:

* ``atom_counts`` — the values are counts (or already-normalised proportions);
  normalise over the included elements.
* ``element_mass_fraction`` — elemental wt%; moles ``= wt / atomic_weight``,
  then normalise.
* ``oxide_mass_fraction`` — oxide wt%; **cation moles**
  ``= n_cation · wt / oxide_molecular_mass`` (using the oxide's molecular mass
  and stoichiometry, *not* wt / atomic_weight), with F/S/Cl and other
  oxide-less elements treated as element wt%; then normalise.

The included basis excludes O and the reference's ``structural_exclude`` set,
but retains the measured structural elements F/S/Cl.
"""

from __future__ import annotations

import math

from axiomm.analysis.errors import PayloadValidationError


def included_elements(reference, extra_exclude=frozenset()) -> tuple[str, ...]:
    """Reference elements kept for matching (O + structural_exclude + config removed)."""
    excluded = set(reference.structural_exclude) | set(extra_exclude)
    return tuple(sym for sym in reference.element_order() if sym not in excluded)


def _oxide_molecular_mass(element_ref, o_weight: float) -> tuple[float, int]:
    """Return (oxide molecular mass, n_cation) for an element with an oxide form."""
    _name, n_cat, n_o = element_ref.oxide_form
    return n_cat * element_ref.atomic_weight + n_o * o_weight, n_cat


def to_molar_proportions(composition, basis: str, reference,
                         *, allowed: set[str]) -> dict[str, float]:
    """Convert a composition (in ``basis``) to molar/element proportions.

    Only elements in ``allowed`` (the shared, non-excluded, non-censored set)
    contribute; the result is normalised over them. Raises on a non-finite or
    negative value, a missing/invalid atomic weight, or a missing oxide form
    where the basis requires one.
    """
    if basis is None:
        raise PayloadValidationError(
            "composition has no declared basis (unaudited); refuse to guess. "
            "Use a basis-audited reference (e.g. MINERALOGY_DEFAULT_V2)."
        )
    o_weight = reference.elements["O"].atomic_weight if "O" in reference.elements else 15.999
    moles: dict[str, float] = {}
    for sym, raw in composition.items():
        if sym not in allowed:
            continue
        value = float(raw)
        if not (math.isfinite(value) and value >= 0):
            raise PayloadValidationError(
                f"composition value for {sym!r} must be finite and >= 0; got {raw!r}."
            )
        if value == 0:
            continue
        if basis == "atom_counts":
            moles[sym] = moles.get(sym, 0.0) + value
        elif basis == "element_mass_fraction":
            aw = _atomic_weight(reference, sym)
            moles[sym] = moles.get(sym, 0.0) + value / aw
        elif basis == "oxide_mass_fraction":
            el = reference.elements.get(sym)
            if el is not None and el.oxide_form is not None:
                ox_mass, n_cat = _oxide_molecular_mass(el, o_weight)
                moles[sym] = moles.get(sym, 0.0) + n_cat * value / ox_mass
            else:  # F/S/Cl and other oxide-less elements are element wt%
                moles[sym] = moles.get(sym, 0.0) + value / _atomic_weight(reference, sym)
        else:
            raise PayloadValidationError(f"unknown composition basis {basis!r}.")
    total = sum(moles.values())
    if total <= 0:
        return {}
    return {sym: m / total for sym, m in moles.items()}


def _atomic_weight(reference, sym: str) -> float:
    el = reference.elements.get(sym)
    if el is None or not (math.isfinite(el.atomic_weight) and el.atomic_weight > 0):
        raise PayloadValidationError(
            f"element {sym!r} has no valid atomic weight for basis conversion."
        )
    return float(el.atomic_weight)


__all__ = ["included_elements", "to_molar_proportions"]
