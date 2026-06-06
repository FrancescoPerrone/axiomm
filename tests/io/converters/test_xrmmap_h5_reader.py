"""Tests for :mod:`axiomm.io.converters.readers.xrmmap_h5` (spec §7, §20.2)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# h5py is a runtime dependency for the reader. Skip the whole module if it's
# not installed so the rest of the suite still runs in lean environments.
h5py = pytest.importorskip("h5py")

from axiomm.io.converters.errors import (
    DatasetNotFoundError,
    MetadataParseError,
)
from axiomm.io.converters.models import AxiommSignalPayload
from axiomm.io.converters.readers.xrmmap_h5 import (
    XRMMapH5Config,
    XRMMapH5Reader,
    decode_hdf5_string,
    decode_hdf5_string_array,
    parse_micrometre_value,
)


# -- parse_micrometre_value (spec §7.7) --------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        ("1um", 1.0),
        ("1 um", 1.0),
        ("1 µm", 1.0),     # µm with U+00B5 (micro sign)
        ("1 μm", 1.0),     # μm with U+03BC (Greek small letter mu)
        ("1.0um", 1.0),
        ("1.0 micrometer", 1.0),
        ("1.0 micrometre", 1.0),
        ("2.5 um", 2.5),
        ("0.1 µm", 0.1),
        ("1e-3 um", 1e-3),
        ("1", 1.0),  # bare numeric also accepted
    ],
)
def test_parse_micrometre_value_variants(value, expected):
    assert parse_micrometre_value(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "1.0 mm",          # wrong unit
        "1.0 nm",          # wrong unit
        "",
        "  ",
        "1.0 um extra",    # trailing garbage
        "1.0 micrometres", # plural unsupported
    ],
)
def test_parse_micrometre_value_raises_on_malformed(value):
    with pytest.raises(MetadataParseError):
        parse_micrometre_value(value)


def test_parse_micrometre_value_raises_on_non_string():
    with pytest.raises(MetadataParseError):
        parse_micrometre_value(1.0)  # type: ignore[arg-type]


# -- decode_hdf5_string (spec §7.6) ------------------------------------------

class TestDecodeHdf5String:
    def test_decodes_raw_bytes(self):
        assert decode_hdf5_string(b"hello") == "hello"

    def test_strips_null_padding(self):
        assert decode_hdf5_string(b"hello\x00\x00\x00") == "hello"

    def test_passes_str_through(self):
        assert decode_hdf5_string("hello") == "hello"

    def test_decodes_numpy_bytes_scalar(self):
        assert decode_hdf5_string(np.bytes_(b"hello")) == "hello"

    def test_decodes_zero_dim_array(self):
        assert decode_hdf5_string(np.array(b"hello")) == "hello"

    def test_raises_on_unsupported_type(self):
        with pytest.raises(TypeError):
            decode_hdf5_string(42)


class TestDecodeHdf5StringArray:
    def test_decodes_list_of_bytes(self):
        assert decode_hdf5_string_array([b"a", b"b", b"c"]) == ["a", "b", "c"]

    def test_decodes_numpy_array(self):
        arr = np.array([b"a", b"b"])
        assert decode_hdf5_string_array(arr) == ["a", "b"]

    def test_strips_null_padding_throughout(self):
        arr = np.array([b"hello\x00\x00", b"world\x00"])
        assert decode_hdf5_string_array(arr) == ["hello", "world"]

    def test_raises_on_unsupported_type(self):
        with pytest.raises(TypeError):
            decode_hdf5_string_array(42)


# -- XRMMapH5Config defaults (spec §17) --------------------------------------

def test_xrmmap_h5_config_defaults_match_spec_17():
    cfg = XRMMapH5Config()
    assert cfg.counts_path == "/xrmmap/mcasum/counts"
    assert cfg.environ_name_path == "/xrmmap/config/environ/name"
    assert cfg.environ_value_path == "/xrmmap/config/environ/value"
    assert cfg.roi_name_path == "/xrmmap/config/rois/name"
    assert cfg.roi_limits_path == "/xrmmap/config/rois/limits"
    assert cfg.beam_size_key == "Experiment.Beam_Size__Nominal"
    assert cfg.energy_scale == pytest.approx(40.96 / 4096)
    assert cfg.roi_limit_scale == pytest.approx(0.01)
    assert cfg.fallback_field_width_um == 500.0


def test_xrmmap_h5_config_is_frozen():
    cfg = XRMMapH5Config()
    with pytest.raises(Exception):  # FrozenInstanceError, defensive on Python version
        cfg.counts_path = "/other"  # type: ignore[misc]


# -- Reader protocol attributes ----------------------------------------------

def test_reader_advertises_name_and_extensions():
    r = XRMMapH5Reader()
    assert r.name == "xrmmap_h5"
    assert ".h5" in r.supported_extensions
    assert ".hdf5" in r.supported_extensions


# -- can_read ----------------------------------------------------------------

def test_xrmmap_can_read_valid_file(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("good.h5")
    assert XRMMapH5Reader().can_read(p) is True


def test_can_read_returns_false_for_wrong_extension(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"not hdf5")
    assert XRMMapH5Reader().can_read(p) is False


def test_can_read_returns_false_for_missing_file(tmp_path):
    assert XRMMapH5Reader().can_read(tmp_path / "missing.h5") is False


def test_can_read_returns_false_when_counts_absent(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("noprimary.h5", include_counts=False)
    assert XRMMapH5Reader().can_read(p) is False


def test_can_read_returns_false_for_garbage_with_h5_extension(tmp_path):
    p = tmp_path / "fake.h5"
    p.write_bytes(b"this is not an hdf5 file at all")
    assert XRMMapH5Reader().can_read(p) is False


# -- read: happy path --------------------------------------------------------

def test_read_returns_axiomm_signal_payload(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    assert isinstance(payload, AxiommSignalPayload)


def test_xrmmap_read_counts_shape(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("ok.h5", shape=(4, 3, 16))
    payload = XRMMapH5Reader().read(p)
    assert payload.data.shape == (4, 3, 16)


def test_read_axes_are_two_nav_one_signal_signal1d(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("ok.h5", shape=(4, 3, 16))
    payload = XRMMapH5Reader().read(p)

    assert payload.signal_kind == "signal1d"
    assert len(payload.axes) == 3
    nav = [a for a in payload.axes if a.role == "navigation"]
    sig = [a for a in payload.axes if a.role == "signal"]
    assert len(nav) == 2
    assert len(sig) == 1

    by_index = {a.index_in_array: a for a in payload.axes}
    assert by_index[0].name == "x" and by_index[0].size == 4
    assert by_index[1].name == "y" and by_index[1].size == 3
    assert by_index[2].name == "Energy" and by_index[2].size == 16


def test_read_navigation_axes_units_are_micrometres(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    for axis in (a for a in payload.axes if a.role == "navigation"):
        assert axis.units == "µm"


def test_read_signal_axis_has_kev_units_and_energy_scale(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    sig_axis = next(a for a in payload.axes if a.role == "signal")
    assert sig_axis.units == "keV"
    assert sig_axis.scale == pytest.approx(40.96 / 4096)


def test_xrmmap_extracts_config_metadata(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "ok.h5",
        environ={
            "Experiment.Beam_Size__Nominal": "2 um",
            "Detector.Model": "XYZ-100",
        },
    )
    payload = XRMMapH5Reader().read(p)
    environ = payload.original_metadata["environ"]
    assert environ["Experiment.Beam_Size__Nominal"] == "2 um"
    assert environ["Detector.Model"] == "XYZ-100"


def test_xrmmap_extracts_roi_metadata(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "ok.h5", rois=[("Fe Ka", 640, 670), ("Cu Ka", 800, 830)]
    )
    payload = XRMMapH5Reader().read(p)
    rois = payload.original_metadata["rois"]
    assert len(rois) == 2
    assert rois[0]["name"] == "Fe Ka"
    assert rois[0]["start"] == pytest.approx(6.40)
    assert rois[0]["end"] == pytest.approx(6.70)
    assert rois[1]["name"] == "Cu Ka"
    assert rois[1]["start"] == pytest.approx(8.00)


def test_read_beam_size_drives_navigation_scale(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "ok.h5", environ={"Experiment.Beam_Size__Nominal": "2.5 um"}
    )
    payload = XRMMapH5Reader().read(p)
    for axis in (a for a in payload.axes if a.role == "navigation"):
        assert axis.scale == pytest.approx(2.5)


def test_read_provenance_records_path_and_reader(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("ok.h5")
    payload = XRMMapH5Reader().read(p)
    assert payload.provenance is not None
    assert payload.provenance.path == p
    assert payload.provenance.reader == "xrmmap_h5"
    assert payload.provenance.reader_version is not None


def test_read_title_defaults_to_file_stem(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("A21_054.h5")
    payload = XRMMapH5Reader().read(p)
    assert payload.title == "A21_054"


def test_read_records_axiomm_namespace_metadata(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("ok.h5"))
    axiomm_meta = payload.metadata["AXIOMM"]
    assert axiomm_meta["reader"] == "xrmmap_h5"
    assert axiomm_meta["config"]["counts_path"] == "/xrmmap/mcasum/counts"


# -- read: missing-metadata branches (spec §7.8) -----------------------------

def test_missing_counts_dataset_raises(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("nocounts.h5", include_counts=False)
    with pytest.raises(DatasetNotFoundError) as exc:
        XRMMapH5Reader().read(p)
    msg = str(exc.value)
    assert "/xrmmap/mcasum/counts" in msg
    # Actionable: points the user at the config field they need to override.
    assert "counts_path" in msg


def test_missing_roi_metadata_warns_but_converts(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5("noroi.h5", include_rois=False)
    payload = XRMMapH5Reader().read(p)
    assert isinstance(payload, AxiommSignalPayload)
    codes = {d.code for d in payload.diagnostics}
    assert "roi_missing" in codes
    assert "rois" not in payload.original_metadata


def test_missing_environ_warns_and_falls_back(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "noenviron.h5", include_environ=False, shape=(10, 5, 16)
    )
    payload = XRMMapH5Reader().read(p)
    codes = {d.code for d in payload.diagnostics}
    assert "environ_missing" in codes
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    # fallback_field_width_um / xdim = 500 / 10 = 50
    assert nav_x.scale == pytest.approx(50.0)


def test_missing_beam_size_warns_and_falls_back(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "nobeam.h5", environ={"Other.Key": "value"}, shape=(10, 5, 16)
    )
    payload = XRMMapH5Reader().read(p)
    codes = {d.code for d in payload.diagnostics}
    assert "beam_size_missing" in codes
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    assert nav_x.scale == pytest.approx(500.0 / 10)


def test_unparseable_beam_size_warns_and_falls_back(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "badbeam.h5",
        environ={"Experiment.Beam_Size__Nominal": "wat"},
        shape=(10, 5, 16),
    )
    payload = XRMMapH5Reader().read(p)
    codes = {d.code for d in payload.diagnostics}
    assert "beam_size_unparseable" in codes
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    assert nav_x.scale == pytest.approx(500.0 / 10)


def test_disabling_fallback_uses_unit_scale_with_diagnostic(synthetic_xrmmap_h5):
    p = synthetic_xrmmap_h5(
        "nofallback.h5", include_environ=False, shape=(10, 5, 16)
    )
    config = XRMMapH5Config(fallback_field_width_um=None)
    payload = XRMMapH5Reader(config=config).read(p)
    codes = {d.code for d in payload.diagnostics}
    assert "navigation_scale_unknown" in codes
    nav_x = next(a for a in payload.axes if a.index_in_array == 0)
    assert nav_x.scale == pytest.approx(1.0)


# -- read: lazy flag ---------------------------------------------------------

def test_lazy_default_emits_downgrade_diagnostic(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("lazy.h5"))
    codes = {d.code for d in payload.diagnostics}
    assert "lazy_downgraded_to_eager" in codes


def test_lazy_false_does_not_emit_downgrade_diagnostic(synthetic_xrmmap_h5):
    payload = XRMMapH5Reader().read(synthetic_xrmmap_h5("eager.h5"), lazy=False)
    codes = {d.code for d in payload.diagnostics}
    assert "lazy_downgraded_to_eager" not in codes


# -- Config-override: the "different file structure" use case ----------------

def test_config_override_reads_file_with_alternative_paths(tmp_path):
    """A file with the same logical structure but different HDF5 paths
    is handled by passing a configured reader, no subclassing.
    """
    p = tmp_path / "alt.h5"
    rng = np.random.default_rng(0)
    with h5py.File(p, "w") as f:
        f.create_dataset(
            "/custom/group/counts",
            data=rng.integers(0, 10, size=(4, 3, 16), dtype=np.int32),
        )

    # Default config can't find the counts dataset.
    with pytest.raises(DatasetNotFoundError):
        XRMMapH5Reader().read(p)

    # Custom config does.
    config = XRMMapH5Config(counts_path="/custom/group/counts")
    payload = XRMMapH5Reader(config=config).read(p)
    assert payload.data.shape == (4, 3, 16)


# -- Side-effect hygiene -----------------------------------------------------

def test_importing_reader_module_does_not_load_tkinter():
    for mod_name in list(sys.modules):
        if (
            mod_name in ("tkinter", "_tkinter")
            or mod_name.startswith("tkinter.")
        ):
            del sys.modules[mod_name]

    # Re-import to be sure.
    import importlib
    import axiomm.io.converters.readers.xrmmap_h5 as mod

    importlib.reload(mod)

    leaked = sorted(
        m
        for m in sys.modules
        if m in ("tkinter", "_tkinter") or m.startswith("tkinter.")
    )
    assert not leaked, f"reader leaked tkinter imports: {leaked!r}"
