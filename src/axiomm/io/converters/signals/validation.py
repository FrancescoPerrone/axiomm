"""Axis validation for AXIOMM signal builders (spec §8.6).

The validator runs before a builder constructs a backend signal. It catches
the four common mistakes that lead to silently wrong outputs:

1. The number of :class:`AxisSpec` entries does not match ``data.ndim``.
2. An axis size does not match the corresponding data dimension.
3. The :attr:`AxisSpec.index_in_array` values do not form a complete
   permutation of ``[0, ndim)`` (missing, duplicated, or out-of-bounds).
4. The number of signal-role axes is wrong for the requested
   :class:`SignalKind`.

Validation is run in two places:

* by :func:`HyperSpyBuilder.build` before constructing a HyperSpy signal;
* by user code via :func:`validate_axes` when assembling a payload by hand.
"""

from __future__ import annotations

from axiomm.io.converters.errors import SignalValidationError
from axiomm.io.converters.models import AxiommSignalPayload, SignalKind


def validate_axes(
    payload: AxiommSignalPayload,
    *,
    expected_kind: SignalKind | None = None,
) -> None:
    """Validate that ``payload``'s axes are internally consistent.

    Parameters
    ----------
    payload
        The payload to validate.
    expected_kind
        Override ``payload.signal_kind`` for the signal-axis-count check.
        Builders pass the *resolved* kind (after ``"auto"`` resolution).

    Raises
    ------
    SignalValidationError
        If any of the checks listed in the module docstring fails.
    """
    axes = payload.axes
    n_axes = len(axes)

    data_ndim = getattr(payload.data, "ndim", None)
    if data_ndim is not None and n_axes != data_ndim:
        raise SignalValidationError(
            f"Number of AxisSpec entries ({n_axes}) does not match "
            f"data.ndim ({data_ndim})."
        )

    # Structural checks first: every axis must have a valid index_in_array,
    # and together they must form a complete permutation of [0, n_axes).
    indices: list[int] = []
    for axis in axes:
        if axis.index_in_array is None:
            raise SignalValidationError(
                f"AxisSpec name={axis.name!r} has no index_in_array set; "
                f"every axis must declare its position in the underlying array."
            )
        if not (0 <= axis.index_in_array < n_axes):
            raise SignalValidationError(
                f"AxisSpec name={axis.name!r} has out-of-bounds "
                f"index_in_array={axis.index_in_array} (n_axes={n_axes})."
            )
        indices.append(axis.index_in_array)

    if sorted(indices) != list(range(n_axes)):
        raise SignalValidationError(
            f"AxisSpec.index_in_array values do not form a complete "
            f"permutation of [0, {n_axes}); got {sorted(indices)!r}."
        )

    # Semantic check: axis sizes must agree with the data shape (only
    # meaningful once we know each axis has a unique, in-bounds index).
    data_shape = getattr(payload.data, "shape", None)
    if data_shape is not None and len(data_shape) == n_axes:
        for axis in axes:
            expected_size = data_shape[axis.index_in_array]
            if axis.size != expected_size:
                raise SignalValidationError(
                    f"AxisSpec name={axis.name!r} size {axis.size} does "
                    f"not match data shape at index "
                    f"{axis.index_in_array} ({expected_size})."
                )

    kind = expected_kind or payload.signal_kind
    n_signal = sum(1 for a in axes if a.role == "signal")

    if kind == "signal1d" and n_signal != 1:
        raise SignalValidationError(
            f"signal_kind={kind!r} requires exactly 1 signal axis; "
            f"got {n_signal}."
        )
    if kind == "signal2d" and n_signal != 2:
        raise SignalValidationError(
            f"signal_kind={kind!r} requires exactly 2 signal axes; "
            f"got {n_signal}."
        )
    # "auto" defers signal-count enforcement to the builder.
    # "base" accepts any signal count.


__all__ = ["validate_axes"]
