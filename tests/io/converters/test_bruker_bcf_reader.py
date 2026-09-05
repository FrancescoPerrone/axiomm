"""Offline unit tests for the Bruker .bcf reader's payload mapping.

These exercise the HyperSpy-free core (:func:`build_payload`, axis mapping,
curated-metadata extraction, provenance) and registry resolution, with no
network, no HyperSpy import, and no .bcf file. The real-file read + pipeline is
a separate opt-in ``realdata`` test.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from axiomm.io.converters.readers.bruker_bcf import (
    AxisInfo,
    BrukerBCFReader,
    build_payload,
)


def _axes():
    # deliberately out of array order to prove mapping is by index_in_array
    return [
        AxisInfo(index_in_array=2, name="Energy", size=4, scale=0.01, offset=-0.48,
                 units="keV", navigate=False),
        AxisInfo(index_in_array=0, name="height", size=2, scale=0.2, offset=0.0,
                 units="nm", navigate=True),
        AxisInfo(index_in_array=1, name="width", size=3, scale=0.2, offset=0.0,
                 units="nm", navigate=True),
    ]


def _md(**over):
    md = {
        "General": {"title": "EDX", "date": "2020-04-28"},
        "Signal": {"signal_type": "EDS_TEM"},
        "Acquisition_instrument": {"TEM": {"beam_energy": 200.0, "Detector": {
            "EDS": {"live_time": 974.5, "real_time": 1015.6, "detector_type": "Custom"}}}},
        "Sample": {"elements": ["O", "Cu", "Y", "Ba"]},
    }
    md.update(over)
    return md


def test_build_payload_maps_axes_by_index_in_array():
    data = np.zeros((2, 3, 4), dtype=np.uint8)
    p = build_payload(data=data, axes=_axes(), metadata=_md(), original_metadata={},
                      source_path=Path("x.bcf"), input_hash="a" * 64)
    # axes ordered by index_in_array
    assert [a.index_in_array for a in p.axes] == [0, 1, 2]
    assert [a.role for a in p.axes] == ["navigation", "navigation", "signal"]
    energy = next(a for a in p.axes if a.role == "signal")
    assert energy.name == "Energy" and energy.units == "keV"
    assert energy.scale == pytest.approx(0.01) and energy.offset == pytest.approx(-0.48)
    assert p.signal_kind == "signal1d"


def test_build_payload_records_provenance_and_curated_metadata():
    p = build_payload(data=np.zeros((2, 3, 4)), axes=_axes(), metadata=_md(),
                      original_metadata={"foo": 1}, source_path=Path("x.bcf"),
                      input_hash="b" * 64)
    ns = p.metadata["AXIOMM"]
    assert ns["reader"] == "bruker_bcf" and ns["source_sha256"] == "b" * 64
    assert ns["acquisition"]["beam_energy"] == 200.0
    assert ns["acquisition"]["elements_in_file"] == ["O", "Cu", "Y", "Ba"]
    assert p.provenance.reader == "bruker_bcf" and p.provenance.input_hash == "b" * 64
    assert p.original_metadata == {"foo": 1} and p.title == "EDX"


def test_build_payload_diagnoses_absent_metadata():
    md = {"General": {"title": "EDX"}, "Signal": {}, "Acquisition_instrument": {}, "Sample": {}}
    p = build_payload(data=np.zeros((2, 3, 4)), axes=_axes(), metadata=md,
                      original_metadata={}, source_path=Path("x.bcf"), input_hash="c" * 64)
    assert p.metadata["AXIOMM"]["acquisition"]["beam_energy"] is None
    assert any(d.code == "bcf_metadata_absent" and "beam_energy" in d.message
               for d in p.diagnostics)


def test_payload_feeds_the_analysis_reshape():
    # the reader's payload must plug straight into the analysis pipeline
    from axiomm.analysis.reshape import pixels_by_channels
    data = np.arange(2 * 3 * 4, dtype=float).reshape(2, 3, 4)
    p = build_payload(data=data, axes=_axes(), metadata=_md(), original_metadata={},
                      source_path=Path("x.bcf"), input_hash="d" * 64)
    flat = pixels_by_channels(p)
    assert flat.n_pixels == 6 and flat.n_channels == 4


def test_reader_can_read_extension():
    r = BrukerBCFReader()
    assert r.can_read("sample.bcf") and r.can_read("SAMPLE.BCF")
    assert not r.can_read("sample.h5")


def test_registry_resolves_reader():
    # resolving the factory works and does not require a .bcf or HyperSpy import
    from axiomm.io.converters.registry import readers
    reader = readers.get("bruker_bcf")
    assert reader.name == "bruker_bcf"
    assert reader.supported_extensions == (".bcf",)
