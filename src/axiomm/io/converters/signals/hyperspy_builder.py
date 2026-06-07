"""HyperSpy-backed signal builder for the AXIOMM converter (spec §8).

:class:`HyperSpyBuilder` is the first concrete :class:`SignalBuilder`. It
takes a neutral :class:`AxiommSignalPayload` and constructs a HyperSpy
signal object (``Signal1D``, ``Signal2D`` or ``BaseSignal``), assigning
axis names / units / scales / offsets and copying AXIOMM metadata under a
stable ``signal.metadata.AXIOMM`` namespace.

The chief subtlety this builder hides from the rest of the package is
HyperSpy's reversed axis convention: HyperSpy's ``axes_manager`` orders
axes within each role group (navigation, signal) in *reverse* numpy order.
For a numpy array of shape ``(d0, d1, d2)`` with the trailing axis as the
signal, HyperSpy lists ``navigation_axes`` as ``[axis at numpy index 1,
axis at numpy index 0]`` — i.e. ``navigation_axes[0]`` is numpy axis 1.
This builder ignores that quirk: it maps :class:`AxisSpec` entries to
HyperSpy axes by their :attr:`index_in_array`, never by tuple position.
The prototype's ``navigation_axes[0].name = 'x'`` was wrong because of
this exact mismatch; using ``index_in_array`` is what fixes it.

If the payload's signal axes are not at the trailing positions of the
data array, the data is transposed *before* being handed to HyperSpy so
the HyperSpy constructor's "signal = trailing" assumption holds. The
neutral :class:`AxiommSignalPayload` is not modified; the transpose is
private to the builder.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import numpy as np

from axiomm.io.converters.errors import SignalValidationError
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    SignalKind,
)
from axiomm.io.converters.signals.validation import validate_axes

try:
    import hyperspy.api as _hs
except ImportError:  # pragma: no cover - exercised when hyperspy is absent
    _hs = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


_HYPERSPY_INSTALL_HINT = (
    "hyperspy is required for HyperSpyBuilder. "
    "Install with `pip install axiomm[hyperspy]` or `pip install hyperspy`."
)


def _require_hyperspy() -> None:
    if _hs is None:
        raise ImportError(_HYPERSPY_INSTALL_HINT)


# ---------------------------------------------------------------------------
# Signal-kind resolution
# ---------------------------------------------------------------------------

def _resolve_signal_kind(payload: AxiommSignalPayload) -> SignalKind:
    """Resolve ``"auto"`` deterministically; pass through other kinds."""
    if payload.signal_kind != "auto":
        return payload.signal_kind
    n_signal = sum(1 for a in payload.axes if a.role == "signal")
    if n_signal == 1:
        return "signal1d"
    if n_signal == 2:
        return "signal2d"
    return "base"


# ---------------------------------------------------------------------------
# Trailing-signal-axis layout
# ---------------------------------------------------------------------------

def _reorder_for_hyperspy(payload: AxiommSignalPayload):
    """Return (data, axes) with navigation axes first and signal axes trailing.

    Within each role group, axes keep their original relative order
    (sorted by ``index_in_array``) so the HyperSpy axes_manager retains
    the expected layout. If the payload is already in canonical order
    no transpose is performed.
    """
    nav = sorted(
        (a for a in payload.axes if a.role == "navigation"),
        key=lambda a: a.index_in_array,  # type: ignore[arg-type]
    )
    sig = sorted(
        (a for a in payload.axes if a.role == "signal"),
        key=lambda a: a.index_in_array,  # type: ignore[arg-type]
    )
    new_order = nav + sig
    permutation = [a.index_in_array for a in new_order]

    if permutation == list(range(payload.data.ndim)):
        return payload.data, payload.axes  # already canonical

    new_data = np.transpose(payload.data, permutation)
    new_axes = tuple(
        replace(spec, index_in_array=i) for i, spec in enumerate(new_order)
    )
    return new_data, new_axes


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class HyperSpyBuilder:
    """:class:`SignalBuilder` that constructs HyperSpy signal objects."""

    name = "hyperspy"

    def build(self, payload: AxiommSignalPayload) -> Any:
        """Build and return the HyperSpy signal (``Signal1D`` / ``Signal2D`` / ``BaseSignal``)."""
        _require_hyperspy()
        validate_axes(payload)

        kind = _resolve_signal_kind(payload)
        # Re-validate with the resolved kind (catches "auto" → wrong count).
        validate_axes(payload, expected_kind=kind)

        data, axes = _reorder_for_hyperspy(payload)
        signal = self._construct_signal(kind, data)
        self._assign_axes(signal, axes)
        self._assign_metadata(signal, payload)
        logger.info(
            "HyperSpyBuilder: built %s of shape %s", kind, tuple(data.shape)
        )
        return signal

    # -- helpers ------------------------------------------------------------

    def _construct_signal(self, kind: SignalKind, data: np.ndarray) -> Any:
        if kind == "signal1d":
            return _hs.signals.Signal1D(data)
        if kind == "signal2d":
            return _hs.signals.Signal2D(data)
        if kind == "base":
            return _hs.signals.BaseSignal(data)
        raise SignalValidationError(
            f"Unknown signal_kind {kind!r}; expected one of "
            f"'signal1d', 'signal2d', 'base', 'auto'."
        )

    def _assign_axes(self, signal: Any, axes) -> None:
        spec_by_index = {a.index_in_array: a for a in axes}
        all_hs_axes = list(signal.axes_manager.navigation_axes) + list(
            signal.axes_manager.signal_axes
        )
        for hs_axis in all_hs_axes:
            spec = spec_by_index.get(hs_axis.index_in_array)
            if spec is None:  # pragma: no cover - validation should prevent this
                continue
            hs_axis.name = spec.name
            if spec.units is not None:
                hs_axis.units = spec.units
            if spec.scale is not None:
                hs_axis.scale = spec.scale
            hs_axis.offset = spec.offset

    def _assign_metadata(
        self, signal: Any, payload: AxiommSignalPayload
    ) -> None:
        # Build the AXIOMM namespace from payload.metadata["AXIOMM"]
        # plus structured provenance and diagnostics.
        existing = (
            dict(payload.metadata.get("AXIOMM", {})) if payload.metadata else {}
        )
        axiomm_meta: dict[str, Any] = existing
        if payload.provenance is not None:
            axiomm_meta["provenance"] = {
                "path": str(payload.provenance.path),
                "reader": payload.provenance.reader,
                "reader_version": payload.provenance.reader_version,
                "input_hash": payload.provenance.input_hash,
            }
        if payload.diagnostics:
            axiomm_meta["diagnostics"] = [
                {
                    "severity": d.severity,
                    "code": d.code,
                    "message": d.message,
                    "context": dict(d.context),
                }
                for d in payload.diagnostics
            ]

        general: dict[str, Any] = {}
        if payload.title is not None:
            general["title"] = payload.title

        non_axiomm = (
            {k: v for k, v in payload.metadata.items() if k != "AXIOMM"}
            if payload.metadata
            else {}
        )

        if general:
            signal.metadata.add_dictionary({"General": general})
        if non_axiomm:
            signal.metadata.add_dictionary(non_axiomm)
        if axiomm_meta:
            signal.metadata.add_dictionary({"AXIOMM": axiomm_meta})

        if payload.original_metadata:
            signal.original_metadata.add_dictionary(payload.original_metadata)


def build_hyperspy_signal(payload: AxiommSignalPayload) -> Any:
    """Convenience: equivalent to ``HyperSpyBuilder().build(payload)``."""
    return HyperSpyBuilder().build(payload)


__all__ = ["HyperSpyBuilder", "build_hyperspy_signal"]
