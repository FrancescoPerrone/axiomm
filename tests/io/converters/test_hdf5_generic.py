"""Tests for :mod:`axiomm.io.converters.readers.hdf5_generic` (Chunk 14).

The point of the generic reader is that it works on any XRM-shaped
HDF5 file at *any* paths, driven by a schema. So the tests cover:

* the XRM built-in schema produces the same payload shape as the
  bespoke `XRMMapH5Reader` on the synthetic XRM fixture
  (proving the schema correctly captures the XRM layout);
* a *custom* schema with non-XRM paths actually drives the reader
  (proving the schema parameter does its job — not just a
  decorative argument);
* the usual missing-path / can_read / dataset-not-found policies
  carry over from the helpers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

h5py = pytest.importorskip("h5py")

from axiomm.io.converters.calibration import ConversionMode
from axiomm.io.converters.errors import DatasetNotFoundError
from axiomm.io.converters.models import AxiommSignalPayload
from axiomm.io.converters.readers.hdf5_generic import (
    GenericHDF5MapReader,
    HDF5MapCalibration,
)
from axiomm.io.converters.readers.hdf5_schema import (
    HDF5MapSchema,
    XRMMAP_H5_SCHEMA,
)


# ---------------------------------------------------------------------------
# Constructor + protocol attributes
# ---------------------------------------------------------------------------

def test_generic_reader_advertises_extensions_and_default_name():
    r = GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA)
    assert r.name == "generic_hdf5_map"
    assert ".h5" in r.supported_extensions
    assert ".hdf5" in r.supported_extensions


def test_generic_reader_accepts_explicit_name():
    r = GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA, name="my_format")
    assert r.name == "my_format"


def test_generic_reader_uses_default_calibration_when_none_given():
    """Defaults are all None (Chunk 18) — every field enters the
    ladder as "not user-supplied" rather than as a silent value."""
    r = GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA)
    assert isinstance(r.calibration, HDF5MapCalibration)
    assert r.calibration.roi_limit_units is None
    assert r.calibration.energy_scale is None
    assert r.calibration.legacy_field_width_um is None
    assert r.calibration.field_width_um is None
    assert r.calibration.pixel_size_um is None


# ---------------------------------------------------------------------------
# Reader vs. XRMMapH5Reader equivalence on the synthetic fixture
# ---------------------------------------------------------------------------

def test_xrm_schema_produces_payload_with_expected_axes(synthetic_xrmmap_h5):
    """Using the XRM schema + matching scientific calibration on the same
    synthetic fixture should produce axes / data shape identical to
    what the bespoke XRMMapH5Reader produces."""
    p = synthetic_xrmmap_h5("synth.h5", shape=(4, 3, 16))
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        calibration=HDF5MapCalibration(
            energy_scale=40.96 / 4096,
            roi_limit_units="channel_index",
            legacy_field_width_um=500.0,
        ),
    )
    payload = reader.read(p)

    assert isinstance(payload, AxiommSignalPayload)
    assert payload.data.shape == (4, 3, 16)
    by_index = {a.index_in_array: a for a in payload.axes}
    assert by_index[0].name == "x" and by_index[0].size == 4
    assert by_index[1].name == "y" and by_index[1].size == 3
    assert by_index[2].name == "Energy" and by_index[2].size == 16
    # The synthetic fixture's environ has a beam size of "1 um" so the
    # nav scale is 1.0 µm — not 500/4 = 125.0 from the fallback.
    assert by_index[0].scale == pytest.approx(1.0)


def test_xrm_schema_extracts_environ_and_rois(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("synth.h5")
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        calibration=HDF5MapCalibration(
            energy_scale=0.01, roi_limit_units="channel_index",
        ),
    )
    payload = reader.read(p)
    assert "environ" in payload.original_metadata
    assert payload.original_metadata["environ"]["Experiment.Beam_Size__Nominal"] == "1 um"
    rois = payload.original_metadata["rois"]
    assert rois[0]["name"] == "Fe Ka"
    assert rois[0]["start"] == pytest.approx(6.40)


# ---------------------------------------------------------------------------
# Custom schema (the actual reason this reader exists)
# ---------------------------------------------------------------------------

def _write_custom_layout(path: Path, shape=(4, 3, 16)) -> Path:
    """Write an XRM-shaped HDF5 file at non-XRM paths."""
    rng = np.random.default_rng(0)
    data = rng.integers(0, 100, size=shape, dtype=np.int32)
    with h5py.File(path, "w") as f:
        f.create_dataset("/scan/data/counts", data=data)
        f.create_dataset(
            "/scan/metadata/names",
            data=np.array(["Beam_Size_Um", "Detector"], dtype="S64"),
        )
        f.create_dataset(
            "/scan/metadata/values",
            data=np.array(["3", "Custom"], dtype="S64"),
        )
    return path


def test_custom_schema_drives_path_lookup(tmp_path):
    """A non-XRM file at custom paths is readable via a custom schema —
    the schema parameter is what drives the reader, not the built-in
    XRM defaults."""
    p = _write_custom_layout(tmp_path / "custom.h5", shape=(4, 3, 16))
    schema = HDF5MapSchema(
        counts_path="/scan/data/counts",
        environ_name_path="/scan/metadata/names",
        environ_value_path="/scan/metadata/values",
        beam_size_key="Beam_Size_Um",
        # no rois in this fixture, so leave roi_* as None
    )
    reader = GenericHDF5MapReader(
        schema=schema, calibration=HDF5MapCalibration(energy_scale=0.005),
    )
    payload = reader.read(p)

    # Counts extracted from the custom path.
    assert payload.data.shape == (4, 3, 16)
    # Environ extracted via the custom path; beam-size lookup uses the
    # schema's key.
    assert payload.original_metadata["environ"]["Beam_Size_Um"] == "3"
    # ROIs absent → emitted as a diagnostic, not present in metadata.
    assert "rois" not in payload.original_metadata
    assert "roi_missing" in {d.code for d in payload.diagnostics}

    # Beam-size-driven nav scale: 3 µm parsed from environ.
    nav_axes = [a for a in payload.axes if a.role == "navigation"]
    assert all(a.scale == pytest.approx(3.0) for a in nav_axes)

    # Energy scale comes from the config, not the schema.
    sig_axis = next(a for a in payload.axes if a.role == "signal")
    assert sig_axis.scale == pytest.approx(0.005)


def test_can_read_returns_true_when_counts_path_present(tmp_path):
    p = _write_custom_layout(tmp_path / "custom.h5")
    schema = HDF5MapSchema(counts_path="/scan/data/counts")
    reader = GenericHDF5MapReader(schema=schema)
    assert reader.can_read(p) is True


def test_can_read_returns_false_when_counts_path_absent(tmp_path):
    p = _write_custom_layout(tmp_path / "custom.h5")
    schema = HDF5MapSchema(counts_path="/some/other/path")
    reader = GenericHDF5MapReader(schema=schema)
    assert reader.can_read(p) is False


def test_can_read_returns_false_for_wrong_extension(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"not hdf5")
    reader = GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA)
    assert reader.can_read(p) is False


def test_can_read_returns_false_for_garbage_with_h5_extension(tmp_path):
    p = tmp_path / "fake.h5"
    p.write_bytes(b"not an hdf5 file")
    reader = GenericHDF5MapReader(schema=XRMMAP_H5_SCHEMA)
    assert reader.can_read(p) is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_missing_counts_raises_dataset_not_found(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as f:
        f.create_dataset("/elsewhere", data=np.zeros((4, 3, 16)))
    schema = HDF5MapSchema(counts_path="/xrmmap/mcasum/counts")
    reader = GenericHDF5MapReader(schema=schema)
    with pytest.raises(DatasetNotFoundError) as exc:
        reader.read(p)
    msg = str(exc.value)
    assert "/xrmmap/mcasum/counts" in msg
    assert "schema=HDF5MapSchema" in msg


def test_non_3d_counts_raises_dataset_not_found(tmp_path):
    p = tmp_path / "x.h5"
    with h5py.File(p, "w") as f:
        # 2-D — wrong rank.
        f.create_dataset("/data", data=np.zeros((4, 16)))
    schema = HDF5MapSchema(counts_path="/data")
    reader = GenericHDF5MapReader(schema=schema)
    with pytest.raises(DatasetNotFoundError, match="3-D"):
        reader.read(p)


# ---------------------------------------------------------------------------
# AXIOMM namespace records the schema + config used
# ---------------------------------------------------------------------------

def test_metadata_records_schema_and_calibration(synthetic_xrmmap_h5):
    """Manifest reproducibility requires the full schema + calibration
    + mode to be in the AXIOMM namespace, so a later reader can
    reproduce the exact extraction."""
    p = synthetic_xrmmap_h5("synth.h5")
    reader = GenericHDF5MapReader(
        schema=XRMMAP_H5_SCHEMA,
        calibration=HDF5MapCalibration(
            energy_scale=0.01,
            roi_limit_units="channel_index",
            legacy_field_width_um=500.0,
        ),
    )
    payload = reader.read(p)
    converter = payload.metadata["AXIOMM"]["converter"]
    cfg = converter["config"]
    assert "schema" in cfg
    assert "calibration" in cfg
    assert "mode" in cfg
    assert cfg["schema"]["counts_path"] == "/xrmmap/mcasum/counts"
    assert cfg["calibration"]["energy_scale"] == 0.01
    assert cfg["calibration"]["roi_limit_units"] == "channel_index"
    assert cfg["calibration"]["legacy_field_width_um"] == 500.0
    assert cfg["mode"] == "generic"


# ---------------------------------------------------------------------------
# Import hygiene
# ---------------------------------------------------------------------------

def test_importing_generic_reader_does_not_load_tkinter():
    for m in list(sys.modules):
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter."):
            del sys.modules[m]
    import importlib
    import axiomm.io.converters.readers.hdf5_generic as mod
    importlib.reload(mod)
    leaked = [
        m for m in sys.modules
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter.")
    ]
    assert not leaked
