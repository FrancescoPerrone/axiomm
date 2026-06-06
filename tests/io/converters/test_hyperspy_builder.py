"""Tests for :mod:`axiomm.io.converters.signals.hyperspy_builder` (spec §8)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

hs = pytest.importorskip("hyperspy.api")

from axiomm.io.converters.errors import SignalValidationError
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)
from axiomm.io.converters.signals.hyperspy_builder import (
    HyperSpyBuilder,
    build_hyperspy_signal,
)
from axiomm.io.converters.signals.validation import validate_axes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xrm_payload(
    *,
    shape: tuple[int, int, int] = (4, 3, 16),
    signal_kind: str = "signal1d",
    title: str | None = "test",
    metadata: dict | None = None,
    original_metadata: dict | None = None,
    diagnostics: list[Diagnostic] | None = None,
    provenance: SourceProvenance | None = None,
) -> AxiommSignalPayload:
    data = np.arange(np.prod(shape), dtype=np.float32).reshape(shape)
    axes = (
        AxisSpec(
            "x", "navigation", shape[0],
            units="µm", scale=1.0, index_in_array=0,
        ),
        AxisSpec(
            "y", "navigation", shape[1],
            units="µm", scale=2.0, index_in_array=1,
        ),
        AxisSpec(
            "Energy", "signal", shape[2],
            units="keV", scale=0.01, index_in_array=2,
        ),
    )
    return AxiommSignalPayload(
        data=data,
        axes=axes,
        signal_kind=signal_kind,
        metadata=metadata or {},
        original_metadata=original_metadata or {},
        provenance=provenance,
        diagnostics=diagnostics or [],
        title=title,
    )


def _hs_axes_by_index(signal):
    """Return a dict mapping numpy index_in_array -> hyperspy axis."""
    by_index = {}
    for ax in list(signal.axes_manager.navigation_axes) + list(
        signal.axes_manager.signal_axes
    ):
        by_index[ax.index_in_array] = ax
    return by_index


# ---------------------------------------------------------------------------
# Signal-kind resolution
# ---------------------------------------------------------------------------

def test_build_returns_signal1d_for_signal1d():
    signal = HyperSpyBuilder().build(_make_xrm_payload())
    assert isinstance(signal, hs.signals.Signal1D)


def test_build_returns_signal2d_for_signal2d():
    data = np.zeros((4, 32, 16), dtype=np.float32)
    axes = (
        AxisSpec("z", "navigation", 4, units="µm", scale=1.0, index_in_array=0),
        AxisSpec("y", "signal", 32, units="px", scale=1.0, index_in_array=1),
        AxisSpec("x", "signal", 16, units="px", scale=1.0, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=axes, signal_kind="signal2d",
    )
    signal = HyperSpyBuilder().build(payload)
    assert isinstance(signal, hs.signals.Signal2D)


def test_build_auto_resolves_to_signal1d_for_one_signal_axis():
    signal = HyperSpyBuilder().build(_make_xrm_payload(signal_kind="auto"))
    assert isinstance(signal, hs.signals.Signal1D)


def test_build_auto_resolves_to_signal2d_for_two_signal_axes():
    data = np.zeros((4, 32, 16), dtype=np.float32)
    axes = (
        AxisSpec("z", "navigation", 4, units="µm", scale=1.0, index_in_array=0),
        AxisSpec("y", "signal", 32, units="px", scale=1.0, index_in_array=1),
        AxisSpec("x", "signal", 16, units="px", scale=1.0, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=axes, signal_kind="auto",
    )
    signal = HyperSpyBuilder().build(payload)
    assert isinstance(signal, hs.signals.Signal2D)


def test_build_base_kind_returns_base_signal():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("c", "navigation", 16, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=axes, signal_kind="base",
    )
    signal = HyperSpyBuilder().build(payload)
    assert isinstance(signal, hs.signals.BaseSignal)


# ---------------------------------------------------------------------------
# Axis validation
# ---------------------------------------------------------------------------

def test_validate_axes_raises_when_axis_count_mismatch():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("Energy", "signal", 16, index_in_array=1),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError, match="ndim"):
        validate_axes(payload)


def test_validate_axes_raises_when_axis_size_mismatch():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 999, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 16, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError, match="size"):
        validate_axes(payload)


def test_validate_axes_raises_when_index_in_array_missing():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=None),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 16, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError, match="index_in_array"):
        validate_axes(payload)


def test_validate_axes_raises_when_index_in_array_out_of_bounds():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 16, index_in_array=99),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError, match="out-of-bounds"):
        validate_axes(payload)


def test_validate_axes_raises_when_indices_are_not_a_permutation():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=0),  # duplicate
        AxisSpec("Energy", "signal", 16, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError, match="permutation"):
        validate_axes(payload)


def test_validate_axes_raises_when_signal1d_has_zero_signal_axes():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("z", "navigation", 16, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError, match="signal axis"):
        validate_axes(payload)


def test_validate_axes_raises_when_signal2d_has_one_signal_axis():
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("y", "navigation", 3, index_in_array=1),
        AxisSpec("Energy", "signal", 16, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal2d",
    )
    with pytest.raises(SignalValidationError, match="signal axes"):
        validate_axes(payload)


def test_build_propagates_validation_errors():
    """Errors from validate_axes must bubble through HyperSpyBuilder.build()."""
    data = np.zeros((4, 3, 16), dtype=np.float32)
    bad_axes = (
        AxisSpec("x", "navigation", 4, index_in_array=0),
        AxisSpec("Energy", "signal", 16, index_in_array=1),
    )
    payload = AxiommSignalPayload(
        data=data, axes=bad_axes, signal_kind="signal1d",
    )
    with pytest.raises(SignalValidationError):
        HyperSpyBuilder().build(payload)


# ---------------------------------------------------------------------------
# Axis assignment correctness — the critical chunk-4 risk
# ---------------------------------------------------------------------------

def test_axis_names_match_axisspec_by_index_in_array_not_tuple_position():
    """HyperSpy reverses navigation_axes order vs numpy.

    For shape (4, 3, 16) Signal1D, HyperSpy's navigation_axes[0] is the
    axis at numpy index 1 (size 3), not numpy index 0 (size 4). The
    prototype's ``navigation_axes[0].name = 'x'`` therefore mislabelled
    the axes. Our builder must use ``index_in_array`` so axis names
    correspond to the actual numpy axes regardless of HyperSpy ordering.
    """
    signal = HyperSpyBuilder().build(_make_xrm_payload(shape=(4, 3, 16)))
    by_index = _hs_axes_by_index(signal)

    assert by_index[0].name == "x"
    assert by_index[0].size == 4
    assert by_index[1].name == "y"
    assert by_index[1].size == 3
    assert by_index[2].name == "Energy"
    assert by_index[2].size == 16


def test_navigation_axes_get_their_units_and_scale():
    signal = HyperSpyBuilder().build(_make_xrm_payload(shape=(4, 3, 16)))
    by_index = _hs_axes_by_index(signal)
    assert by_index[0].units == "µm"
    assert by_index[0].scale == pytest.approx(1.0)
    assert by_index[1].units == "µm"
    assert by_index[1].scale == pytest.approx(2.0)


def test_signal_axis_gets_kev_units_and_energy_scale():
    signal = HyperSpyBuilder().build(_make_xrm_payload(shape=(4, 3, 16)))
    sig_axes = list(signal.axes_manager.signal_axes)
    assert len(sig_axes) == 1
    ax = sig_axes[0]
    assert ax.units == "keV"
    assert ax.scale == pytest.approx(0.01)
    assert ax.name == "Energy"


def test_non_canonical_axis_order_is_reordered_transparently():
    """Payload with signal axis at numpy index 0 should still produce
    a correctly labelled Signal1D — the builder transposes the data
    internally so HyperSpy sees the trailing-signal-axis layout it expects.
    """
    data = np.arange(4 * 3 * 16, dtype=np.float32).reshape((16, 4, 3))
    axes = (
        AxisSpec("Energy", "signal", 16, units="keV", scale=0.01, index_in_array=0),
        AxisSpec("x", "navigation", 4, units="µm", scale=1.0, index_in_array=1),
        AxisSpec("y", "navigation", 3, units="µm", scale=2.0, index_in_array=2),
    )
    payload = AxiommSignalPayload(
        data=data, axes=axes, signal_kind="signal1d",
    )
    signal = HyperSpyBuilder().build(payload)

    assert isinstance(signal, hs.signals.Signal1D)
    # After internal transpose, the canonical layout is (x, y, Energy).
    assert signal.data.shape == (4, 3, 16)
    # And the data was transposed, not silently misread.
    assert np.array_equal(signal.data, np.transpose(data, (1, 2, 0)))
    # Axis names in the new canonical order.
    sig_axes = list(signal.axes_manager.signal_axes)
    assert sig_axes[0].name == "Energy"
    nav_names = sorted(
        a.name for a in signal.axes_manager.navigation_axes
    )
    assert nav_names == ["x", "y"]


# ---------------------------------------------------------------------------
# Metadata propagation under signal.metadata.AXIOMM
# ---------------------------------------------------------------------------

def test_axiomm_metadata_namespace_is_preserved():
    metadata = {
        "AXIOMM": {
            "reader": "xrmmap_h5",
            "config": {"counts_path": "/some/path"},
        },
    }
    payload = _make_xrm_payload(metadata=metadata)
    signal = HyperSpyBuilder().build(payload)
    assert signal.metadata.AXIOMM.reader == "xrmmap_h5"
    assert signal.metadata.AXIOMM.config.counts_path == "/some/path"


def test_title_becomes_general_title():
    payload = _make_xrm_payload(title="A21_054_map")
    signal = HyperSpyBuilder().build(payload)
    assert signal.metadata.General.title == "A21_054_map"


def test_provenance_recorded_under_axiomm_namespace():
    provenance = SourceProvenance(
        path=Path("/tmp/example.h5"),
        reader="xrmmap_h5",
        reader_version="0.0.0",
        input_hash="cafebabe",
    )
    payload = _make_xrm_payload(provenance=provenance)
    signal = HyperSpyBuilder().build(payload)
    prov = signal.metadata.AXIOMM.provenance
    assert prov.reader == "xrmmap_h5"
    assert prov.path == "/tmp/example.h5"
    assert prov.input_hash == "cafebabe"


def test_diagnostics_recorded_under_axiomm_namespace():
    diagnostics = [
        Diagnostic("info", "info_code", "info msg"),
        Diagnostic("warning", "warn_code", "warn msg", {"key": "value"}),
    ]
    payload = _make_xrm_payload(diagnostics=diagnostics)
    signal = HyperSpyBuilder().build(payload)
    diags = signal.metadata.AXIOMM.diagnostics
    assert isinstance(diags, list)
    codes = [d["code"] for d in diags]
    assert "info_code" in codes
    assert "warn_code" in codes
    warn = next(d for d in diags if d["code"] == "warn_code")
    assert warn["severity"] == "warning"
    assert warn["context"] == {"key": "value"}


def test_original_metadata_is_preserved():
    payload = _make_xrm_payload(
        original_metadata={"environ": {"Beam_Size": "1 µm"}, "rois": []},
    )
    signal = HyperSpyBuilder().build(payload)
    assert signal.original_metadata.environ.Beam_Size == "1 µm"


def test_non_axiomm_metadata_keys_are_preserved():
    payload = _make_xrm_payload(
        metadata={"Foo": {"bar": "baz"}, "AXIOMM": {"reader": "x"}},
    )
    signal = HyperSpyBuilder().build(payload)
    assert signal.metadata.Foo.bar == "baz"
    assert signal.metadata.AXIOMM.reader == "x"


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def test_build_hyperspy_signal_convenience_function():
    signal = build_hyperspy_signal(_make_xrm_payload())
    assert isinstance(signal, hs.signals.Signal1D)


# ---------------------------------------------------------------------------
# End-to-end: XRMMapH5Reader -> HyperSpyBuilder
# ---------------------------------------------------------------------------

def test_end_to_end_synthetic_reader_then_builder(synthetic_xrmmap_h5):
    """Reader → Builder round trip on the synthetic fixture."""
    pytest.importorskip("h5py")
    from axiomm.io.converters.readers.xrmmap_h5 import XRMMapH5Reader

    p = synthetic_xrmmap_h5("e2e.h5", shape=(4, 3, 16))
    payload = XRMMapH5Reader().read(p)
    signal = HyperSpyBuilder().build(payload)

    assert isinstance(signal, hs.signals.Signal1D)
    by_index = _hs_axes_by_index(signal)
    assert by_index[0].name == "x" and by_index[0].size == 4
    assert by_index[1].name == "y" and by_index[1].size == 3
    assert by_index[2].name == "Energy" and by_index[2].size == 16
    assert signal.metadata.AXIOMM.reader == "xrmmap_h5"
    assert signal.metadata.General.title == "e2e"


# ---------------------------------------------------------------------------
# Import-hygiene
# ---------------------------------------------------------------------------

def test_importing_builder_module_does_not_load_tkinter():
    for mod_name in list(sys.modules):
        if (
            mod_name in ("tkinter", "_tkinter")
            or mod_name.startswith("tkinter.")
        ):
            del sys.modules[mod_name]

    import importlib

    import axiomm.io.converters.signals.hyperspy_builder as mod

    importlib.reload(mod)

    leaked = sorted(
        m
        for m in sys.modules
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter.")
    )
    assert not leaked, f"builder leaked tkinter imports: {leaked!r}"
