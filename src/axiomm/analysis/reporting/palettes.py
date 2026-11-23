"""Categorical colour palettes for phase / cluster maps — a user-facing setting.

The palette a phase map is drawn with is **configuration, not a hard-coded
choice** (see the parameter-autonomy rule): ``batlowS`` is only the default.
A user — or a future UX colour-map picker — selects any palette by name
(a built-in below, or any Matplotlib colormap such as ``"tab20"`` / ``"Set2"``)
or by passing an explicit list of colours. :func:`resolve_palette` turns any of
those into ``n`` hex colours.

The default, ``batlowS``, is Fabio Crameri's *categorical* scientific colour
map: perceptually uniform, colour-vision-deficiency safe, and ordered so the
first ``n`` entries are maximally distinct — so many phases (and small grains)
stay separable, which a short wrap-around palette cannot guarantee.

Attribution: batlowS from Crameri, F. (2018), *Scientific colour maps*, Zenodo,
https://doi.org/10.5281/zenodo.1243862; see Crameri, Shephard & Heron (2020),
*The misuse of colour in science communication*, Nature Communications 11, 5444.
The values below are the published batlowS entries, embedded verbatim so the
core carries no extra dependency.
"""

from __future__ import annotations

from axiomm.analysis.errors import PayloadValidationError

#: Fabio Crameri's ``batlowS`` categorical map (100 entries, published order).
CRAMERI_BATLOWS: tuple[str, ...] = (
    "#011959", "#faccfa", "#828231", "#226061", "#f19d6b", "#4d734d", "#114360", "#fdb4b4",
    "#c09036", "#175262", "#fcbfd6", "#fca890", "#356a59", "#0d315d", "#a18a2b", "#677b3e",
    "#dd954d", "#08255b", "#fdaea2", "#fbc6e8", "#b18d2f", "#cf9340", "#91862d", "#2b655e",
    "#747e38", "#134b61", "#f8a27e", "#0f3b5f", "#416f53", "#1b5962", "#fdbac4", "#5a7745",
    "#e9995c", "#607942", "#477150", "#faa587", "#fdab9a", "#154f62", "#7b8034", "#6d7c3b",
    "#c8913b", "#e39754", "#f59f74", "#195662", "#b98f32", "#a98c2c", "#0e365e", "#103f60",
    "#537549", "#fbc9f1", "#26635f", "#99882c", "#124761", "#fdb7bc", "#1e5d62", "#8a842f",
    "#fdb1ab", "#fcc3df", "#fdbccd", "#30685c", "#051f5a", "#0b2b5c", "#3b6d56", "#d69446",
    "#ed9a62", "#447052", "#185462", "#246160", "#bd8f34", "#787f36", "#4a724e", "#fdafa7",
    "#ad8c2d", "#9d892b", "#fcbed1", "#28645f", "#f7a179", "#f39e70", "#50744b", "#95872c",
    "#0c2e5d", "#0a285c", "#8e852e", "#fca995", "#fcc4e3", "#114160", "#a58b2c", "#6a7b3d",
    "#031c5a", "#386c58", "#144d62", "#fdac9e", "#33695a", "#b58e30", "#134961", "#d29343",
    "#205e61", "#e69858", "#ef9b67", "#fba68c",
)

#: Okabe-Ito colour-vision-deficiency-safe qualitative set (8 entries).
OKABE_ITO: tuple[str, ...] = (
    "#0072B2", "#E69F00", "#009E73", "#CC79A7",
    "#56B4E9", "#D55E00", "#F0E442", "#000000",
)

#: Built-in named palettes shipped with AXIOMM (no Matplotlib needed).
BUILTIN_PALETTES: dict[str, tuple[str, ...]] = {
    "batlowS": CRAMERI_BATLOWS,
    "okabe_ito": OKABE_ITO,
}

#: The default phase/cluster-map palette.
DEFAULT_PALETTE = "batlowS"


def available_palettes() -> tuple[str, ...]:
    """Built-in palette names (any Matplotlib colormap name also works)."""
    return tuple(BUILTIN_PALETTES)


def _from_matplotlib(name: str, n: int) -> list[str] | None:
    """``n`` hex colours sampled from a Matplotlib colormap, or ``None`` if the
    name is unknown / Matplotlib is unavailable."""
    try:
        import matplotlib as mpl
        from matplotlib.colors import to_hex
    except Exception:
        return None
    try:
        cmap = mpl.colormaps[name].resampled(max(n, 1))
    except (KeyError, ValueError):
        return None
    return [to_hex(cmap(i)) for i in range(max(n, 1))]


def resolve_palette(spec, n: int, *, reserve: dict | None = None) -> list[str]:
    """Return ``n`` hex colours for ``n`` categories.

    ``spec`` is a built-in name (:data:`BUILTIN_PALETTES`), any Matplotlib
    colormap name, an explicit sequence of colours, or ``None`` (the default
    :data:`DEFAULT_PALETTE`). ``reserve`` is an optional ``{category_index:
    colour}`` override applied after resolution (e.g. a neutral grey pinned to
    the "unresolved" slot).

    **Capacity.** A Matplotlib colormap is resampled to ``n`` colours. A built-in
    palette or an explicit list has a **fixed length and cycles** (repeats) when ``n``
    exceeds it — the declared exhaustion policy. ``batlowS`` carries 100 distinct
    colours and ``okabe_ito`` 8, so colours do not repeat below those counts; for an
    arbitrary ``n`` without repetition, pass a Matplotlib colormap name.
    """
    if n <= 0:
        return []
    if spec is None:
        spec = DEFAULT_PALETTE

    base: list[str]
    if isinstance(spec, (list, tuple)):
        if not spec or not all(isinstance(c, str) and c for c in spec):
            raise PayloadValidationError(
                "an explicit palette must be a non-empty sequence of colour strings.")
        base = list(spec)
    elif isinstance(spec, str):
        if spec in BUILTIN_PALETTES:
            base = list(BUILTIN_PALETTES[spec])
        else:
            sampled = _from_matplotlib(spec, n)
            if sampled is None:
                raise PayloadValidationError(
                    f"unknown palette {spec!r}; use one of {available_palettes()} "
                    "or a Matplotlib colormap name, or pass an explicit list of colours.")
            base = sampled
    else:
        raise PayloadValidationError(
            f"palette must be a name, a list of colours, or None; got {type(spec).__name__}.")

    colours = [base[i % len(base)] for i in range(n)]
    if reserve:
        for idx, colour in reserve.items():
            if isinstance(idx, int) and 0 <= idx < n and isinstance(colour, str) and colour:
                colours[idx] = colour
    return colours


__all__ = [
    "BUILTIN_PALETTES",
    "CRAMERI_BATLOWS",
    "DEFAULT_PALETTE",
    "OKABE_ITO",
    "available_palettes",
    "resolve_palette",
]
