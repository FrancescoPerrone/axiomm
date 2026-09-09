"""Bespoke, theme-aware SVG for spectra (stage two, S4d).

Hand-built inline SVG — no matplotlib — so the priority plot is crisp at any zoom
(phone included), tiny, and **theme-aware**: axes and text use ``currentColor`` and
the data line uses ``var(--accent, ...)``, so an inline spectrum takes the page's
ink and accent in both light and dark, with fallbacks when those tokens are absent
(e.g. a stand-alone report). Peak identification is drawn as a shaded integration
window over its background level with a labelled tick at the line energy.
"""

from __future__ import annotations

from html import escape

import numpy as np

_ACCENT = "var(--accent, #0d7d88)"
_WINDOW = "var(--peak-window, #d9a441)"

#: A curated categorical palette that reads on both light and dark grounds.
_CATEGORICAL = (
    "#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2",
    "#ff9da6", "#9d755d", "#eeca3b", "#b39ddb", "#8cd17d", "#d37295",
)


def scatter_svg(x, y, labels, *, categories, labels_text=None, width=520, height=380,
                title=None, axis_labels=("comp 1", "comp 2"), max_points=3000, seed=0):
    """Inline SVG scatter of an embedding, coloured by category (cluster).

    Points are drawn per category so each colour is set once; large point clouds
    are randomly subsampled to ``max_points`` (a note is the caller's job). Axes
    and text use ``currentColor`` so the plot adapts to the page theme; the
    category ``-1`` (HDBSCAN noise) is drawn muted. Returns SVG markup.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    labels = np.asarray(labels)
    n = x.size
    if n > max_points:
        sel = np.random.default_rng(seed).choice(n, size=max_points, replace=False)
        x, y, labels = x[sel], y[sel], labels[sel]

    ml, mr, mt, mb = 8, 96, (22 if title else 8), 26
    pw, ph = width - ml - mr, height - mt - mb
    xlo, xhi = float(np.min(x)), float(np.max(x))
    ylo, yhi = float(np.min(y)), float(np.max(y))
    xpad = (xhi - xlo or 1.0) * 0.04
    ypad = (yhi - ylo or 1.0) * 0.04
    xlo, xhi, ylo, yhi = xlo - xpad, xhi + xpad, ylo - ypad, yhi + ypad

    def sx(v):
        return ml + (v - xlo) / (xhi - xlo) * pw

    def sy(v):
        return mt + ph - (v - ylo) / (yhi - ylo) * ph

    labels_text = labels_text or {c: str(c) for c in categories}
    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'font-family="\'IBM Plex Mono\', ui-monospace, monospace" font-size="10">'
    ]
    if title:
        parts.append(f'<text x="{ml}" y="14" font-size="11" fill="currentColor" '
                     f'font-weight="500">{escape(title)}</text>')
    # plot frame
    parts.append(f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="none" '
                 f'stroke="currentColor" stroke-opacity="0.25"/>')
    parts.append(f'<text x="{ml + pw / 2:.0f}" y="{height - 6}" text-anchor="middle" '
                 f'fill="currentColor" fill-opacity="0.6">{escape(axis_labels[0])}</text>')
    parts.append(f'<text x="12" y="{mt + ph / 2:.0f}" text-anchor="middle" '
                 f'fill="currentColor" fill-opacity="0.6" '
                 f'transform="rotate(-90 12 {mt + ph / 2:.0f})">{escape(axis_labels[1])}</text>')

    # points, grouped by category
    for i, cat in enumerate(categories):
        mask = labels == cat
        if not np.any(mask):
            continue
        muted = (cat == -1)
        color = "currentColor" if muted else _CATEGORICAL[i % len(_CATEGORICAL)]
        op = "0.35" if muted else "0.8"
        pts = "".join(f'<circle cx="{sx(px):.1f}" cy="{sy(py):.1f}" r="2"/>'
                      for px, py in zip(x[mask], y[mask], strict=True))
        parts.append(f'<g fill="{color}" fill-opacity="{op}">{pts}</g>')

    # legend
    ly = mt + 4
    for i, cat in enumerate(categories):
        muted = (cat == -1)
        color = "currentColor" if muted else _CATEGORICAL[i % len(_CATEGORICAL)]
        op = "0.4" if muted else "0.85"
        parts.append(f'<rect x="{ml + pw + 12}" y="{ly}" width="9" height="9" rx="2" '
                     f'fill="{color}" fill-opacity="{op}"/>')
        parts.append(f'<text x="{ml + pw + 25}" y="{ly + 8}" fill="currentColor" '
                     f'fill-opacity="0.75">{escape(str(labels_text.get(cat, cat)))}</text>')
        ly += 15
    parts.append("</svg>")
    return "".join(parts)


def _nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    if not np.isfinite([lo, hi]).all() or hi <= lo:
        return [lo]
    raw = (hi - lo) / target
    mag = 10 ** np.floor(np.log10(raw))
    step = min([1, 2, 5, 10], key=lambda m: abs(m * mag - raw)) * mag
    start = np.ceil(lo / step) * step
    return [round(start + i * step, 6) for i in range(int((hi - start) / step) + 1)]


def _fmt_counts(v: float) -> str:
    if v >= 1000:
        return f"{v/1000:.1f}k"
    return f"{v:.0f}"


def _transform(y: np.ndarray, scale: str):
    if scale == "log":
        return np.log10(np.clip(y, 1.0, None))
    if scale == "sqrt":
        return np.sqrt(np.clip(y, 0.0, None))
    return np.clip(y, 0.0, None)


def spectrum_svg(energies, counts, peaks=(), *, y_scale: str = "linear",
                 width: int = 680, height: int = 220, energy_range=None,
                 title: str | None = None) -> str:
    """Return inline SVG markup for one energy-calibrated spectrum with peak IDs."""
    e = np.asarray(energies, dtype=float)
    y = np.asarray(counts, dtype=float)
    ml, mr, mt, mb = 46, 14, (26 if title else 12), 28
    pw, ph = width - ml - mr, height - mt - mb

    lo, hi = (energy_range if energy_range else (float(e.min()), float(e.max())))
    yt = _transform(y, y_scale)
    ymax = float(yt.max()) or 1.0

    def sx(v):
        return ml + (v - lo) / (hi - lo) * pw

    def sy(v):
        return mt + ph - (v / ymax) * ph

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'font-family="\'IBM Plex Mono\', ui-monospace, monospace" font-size="10">'
    ]
    if title:
        parts.append(f'<text x="{ml}" y="14" font-size="11" fill="currentColor" '
                     f'font-weight="500">{escape(title)}</text>')

    # axes
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" '
                 f'stroke="currentColor" stroke-opacity="0.35"/>')
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" '
                 f'stroke="currentColor" stroke-opacity="0.35"/>')
    for xt in _nice_ticks(lo, hi):
        x = sx(xt)
        parts.append(f'<line x1="{x:.1f}" y1="{mt+ph}" x2="{x:.1f}" y2="{mt+ph+4}" '
                     f'stroke="currentColor" stroke-opacity="0.5"/>')
        parts.append(f'<text x="{x:.1f}" y="{mt+ph+16}" text-anchor="middle" '
                     f'fill="currentColor" fill-opacity="0.7">{xt:g}</text>')
    parts.append(f'<text x="{ml+pw}" y="{mt+ph+16}" text-anchor="end" '
                 f'fill="currentColor" fill-opacity="0.55">keV</text>')
    for yv in (0.0, ymax):
        Y = sy(yv)
        raw = (10 ** yv if y_scale == "log" else yv**2 if y_scale == "sqrt" else yv)
        parts.append(f'<text x="{ml-6}" y="{Y+3:.1f}" text-anchor="end" '
                     f'fill="currentColor" fill-opacity="0.7">{_fmt_counts(raw)}</text>')

    # peak windows + background + labels (behind the trace)
    placed: list[tuple[float, float]] = []   # (x, y) of placed labels, for de-collision
    for pk in peaks:
        c = float(pk["center_kev"])
        if not (lo <= c <= hi):
            continue
        half = float(pk.get("window_kev", 0.0)) / 2.0
        x0, x1 = sx(c - half), sx(c + half)
        apex = float(np.interp(c, e, yt))
        parts.append(f'<rect x="{x0:.1f}" y="{mt}" width="{max(x1-x0,1):.1f}" '
                     f'height="{ph:.1f}" fill="{_WINDOW}" fill-opacity="0.12"/>')
        bg = pk.get("background")
        if bg is not None:
            by = sy(_transform(np.array([float(bg)]), y_scale)[0])
            parts.append(f'<line x1="{x0:.1f}" y1="{by:.1f}" x2="{x1:.1f}" y2="{by:.1f}" '
                         f'stroke="currentColor" stroke-opacity="0.45" stroke-dasharray="3 2"/>')
        lx = sx(c)
        ly = sy(apex) - 6
        near = [py for px, py in placed if abs(lx - px) < 34]
        if near:                       # stack above the highest nearby label
            ly = min(min(near) - 11, ly)
        ly = max(ly, mt + 8)           # never leave the plot area
        placed.append((lx, ly))
        parts.append(f'<line x1="{lx:.1f}" y1="{sy(apex):.1f}" x2="{lx:.1f}" y2="{ly+2:.1f}" '
                     f'stroke="currentColor" stroke-opacity="0.4"/>')
        parts.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                     f'fill="currentColor" font-size="9">{escape(str(pk["label"]))}</text>')

    # the spectrum trace
    step = max(1, len(e) // (pw * 2 if pw > 0 else 1))
    pts = " ".join(f"{sx(e[i]):.1f},{sy(yt[i]):.1f}" for i in range(0, len(e), step))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{_ACCENT}" '
                 f'stroke-width="1.4" stroke-linejoin="round"/>')
    parts.append("</svg>")
    return "".join(parts)


__all__ = ["scatter_svg", "spectrum_svg"]
