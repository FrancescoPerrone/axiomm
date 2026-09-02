"""Validating reshape of a signal payload to a (pixels, channels) matrix.

Shared by the analysis tools (PCA input, cluster-mean aggregation). Does
not merely reshape: it validates the signal-axis definition, navigation
shape consistency, numeric dtype, and finiteness, and returns enough
structure to rebuild navigation-shaped outputs safely.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiomm.analysis.errors import PayloadValidationError


@dataclass(frozen=True)
class FlattenedSignal:
    """A payload flattened to ``(n_pixels, n_channels)`` plus structure."""

    matrix: np.ndarray
    nav_shape: tuple[int, ...]
    n_pixels: int
    n_channels: int
    signal_index: int


def pixels_by_channels(payload) -> FlattenedSignal:
    """Validate ``payload`` and flatten it to a pixels-by-channels matrix."""
    signal_axes = [ax for ax in payload.axes if ax.role == "signal"]
    if len(signal_axes) != 1:
        raise PayloadValidationError(
            f"expected exactly one signal axis; got {len(signal_axes)}."
        )
    s = signal_axes[0].index_in_array
    if s is None:
        raise PayloadValidationError(
            "signal axis has no index_in_array; cannot locate it in the data array."
        )

    data = np.asarray(payload.data)
    if not np.issubdtype(data.dtype, np.number):
        raise PayloadValidationError(
            f"signal data must be numeric; got dtype {data.dtype}."
        )
    if not np.all(np.isfinite(data)):
        raise PayloadValidationError(
            "signal data contains non-finite values (NaN or inf)."
        )
    if s < 0 or s >= data.ndim:
        raise PayloadValidationError(
            f"signal axis index_in_array={s} out of range for data.ndim={data.ndim}."
        )

    for ax in payload.axes:
        idx = ax.index_in_array
        if idx is None:
            raise PayloadValidationError(f"axis {ax.name!r} has no index_in_array.")
        if idx < 0 or idx >= data.ndim:
            raise PayloadValidationError(
                f"axis {ax.name!r} index_in_array={idx} out of range for "
                f"data.ndim={data.ndim}."
            )
        if ax.size != data.shape[idx]:
            raise PayloadValidationError(
                f"axis {ax.name!r} declares size {ax.size} but data dim {idx} "
                f"has size {data.shape[idx]}."
            )

    n_channels = data.shape[s]
    nav_shape = tuple(dim for i, dim in enumerate(data.shape) if i != s)
    matrix = np.moveaxis(data, s, -1).reshape(-1, n_channels)
    n_pixels = matrix.shape[0]
    return FlattenedSignal(
        matrix=matrix,
        nav_shape=nav_shape,
        n_pixels=n_pixels,
        n_channels=n_channels,
        signal_index=s,
    )


__all__ = ["FlattenedSignal", "pixels_by_channels"]
