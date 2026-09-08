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


__all__ = ["spectrum_svg"]
