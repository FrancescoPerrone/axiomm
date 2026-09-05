"""Bruker ``.bcf`` reader — STEM/SEM-EDS spectrum images into AXIOMM payloads.

A small, pluggable :class:`~axiomm.io.converters.readers.base.Reader` that turns
a Bruker composite file (``.bcf``) into a backend-neutral
:class:`AxiommSignalPayload` — the same object the analysis pipeline
(``decompose → cluster → …``) and the eventual ``axiomm.pipeline`` facade
consume. It reads the vendor format **at the edge** via RosettaSciIO/HyperSpy,
which stays an *optional* dependency: importing AXIOMM never imports HyperSpy,
and its absence raises a clear :class:`ReaderDependencyError`.

Headless core: this reader knows the file format only. It maps axes by
``index_in_array`` (never by tuple position), preserves the source metadata and
provenance, and makes no XRM-map assumptions. It classifies observed facts and
records absent metadata as diagnostics rather than inventing values.
"""

from __future__ import annotations

import hashlib
from collections import namedtuple
from pathlib import Path

from axiomm.io.converters.errors import ReaderDependencyError, SignalValidationError
from axiomm.io.converters.models import (
    AxiommSignalPayload,
    AxisSpec,
    Diagnostic,
    SourceProvenance,
)

READER_VERSION = "1"

#: Duck-typed axis facts, so :func:`build_payload` is testable without HyperSpy.
AxisInfo = namedtuple("AxisInfo", "index_in_array name size scale offset units navigate")

#: Curated, AXIOMM-relevant metadata (dotted paths into the signal metadata).
_CURATED = {
    "beam_energy": ("Acquisition_instrument.TEM.beam_energy",
                    "Acquisition_instrument.SEM.beam_energy"),
    "live_time_s": ("Acquisition_instrument.TEM.Detector.EDS.live_time",
                    "Acquisition_instrument.SEM.Detector.EDS.live_time"),
    "real_time_s": ("Acquisition_instrument.TEM.Detector.EDS.real_time",
                    "Acquisition_instrument.SEM.Detector.EDS.real_time"),
    "detector_type": ("Acquisition_instrument.TEM.Detector.EDS.detector_type",
                      "Acquisition_instrument.SEM.Detector.EDS.detector_type"),
    "elements_in_file": ("Sample.elements",),
    "acquisition_date": ("General.date",),
    "signal_type_source": ("Signal.signal_type",),
}


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _dig(md: dict, dotted: str):
    node = md
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return (False, None)
        node = node[part]
    return (True, node)


def build_payload(*, data, axes, metadata: dict, original_metadata: dict,
                  source_path: Path, input_hash: str, title: str | None = None,
                  lazy: bool = False, extra_diagnostics=None) -> AxiommSignalPayload:
    """Assemble an :class:`AxiommSignalPayload` from duck-typed signal facts.

    ``axes`` is an iterable of :class:`AxisInfo`. Pure and HyperSpy-free so it
    can be unit-tested offline.
    """
    ordered = sorted(axes, key=lambda a: a.index_in_array)
    axspecs = tuple(
        AxisSpec(name=a.name, role="navigation" if a.navigate else "signal",
                 size=int(a.size), units=(a.units or None),
                 scale=float(a.scale), offset=float(a.offset),
                 index_in_array=int(a.index_in_array))
        for a in ordered
    )
    n_signal = sum(1 for a in ordered if not a.navigate)
    if n_signal == 0:
        raise SignalValidationError("BCF signal has no signal axis; cannot build a payload.")
    signal_kind = "signal1d" if n_signal == 1 else ("signal2d" if n_signal == 2 else "base")

    if title is None:
        _present, title = _dig(metadata, "General.title")
    diagnostics = list(extra_diagnostics or [])
    acquisition: dict = {}
    for label, candidates in _CURATED.items():
        value, found_key = None, None
        for key in candidates:
            present, v = _dig(metadata, key)
            if present:
                value, found_key = v, key
                break
        acquisition[label] = value
        diagnostics.append(Diagnostic(
            "info" if found_key else "warning",
            "bcf_metadata_present" if found_key else "bcf_metadata_absent",
            f"{label}: {'present at ' + found_key if found_key else 'ABSENT'}"))

    axiomm_ns = {
        "reader": "bruker_bcf", "reader_version": READER_VERSION,
        "source_sha256": input_hash, "acquisition": acquisition,
        "lazy": bool(lazy),
    }
    return AxiommSignalPayload(
        data=data, axes=axspecs, signal_kind=signal_kind,
        metadata={"AXIOMM": axiomm_ns}, original_metadata=original_metadata,
        provenance=SourceProvenance(path=source_path, reader="bruker_bcf",
                                    reader_version=READER_VERSION, input_hash=input_hash),
        diagnostics=diagnostics, title=title)


def _select_spectrum_image(signals, diagnostics):
    """Choose the spectrum-image signal (>=3-D: nav + 1 signal axis)."""
    cubes = [s for s in signals if getattr(s.data, "ndim", 0) >= 3]
    if not cubes:
        raise SignalValidationError(
            "no spectrum-image signal (>=3-D) found in the BCF; "
            f"found {len(signals)} signal(s).")
    if len(cubes) > 1:
        diagnostics.append(Diagnostic(
            "warning", "bcf_multiple_spectrum_images",
            f"{len(cubes)} spectrum images present; using the first ({cubes[0].metadata.get_item('General.title', 'untitled')})."))
    return cubes[0]


class BrukerBCFReader:
    """Reader for Bruker ``.bcf`` EDS spectrum images (RosettaSciIO at the edge)."""

    name = "bruker_bcf"
    supported_extensions = (".bcf",)

    def can_read(self, path: str | Path) -> bool:
        return str(path).lower().endswith(".bcf")

    def read(self, path: str | Path, *, lazy: bool = True) -> AxiommSignalPayload:
        try:
            import hyperspy.api as hs
        except ImportError as exc:
            raise ReaderDependencyError(
                "reading Bruker .bcf needs RosettaSciIO/HyperSpy at the edge; "
                "install the [hyperspy] extra (HyperSpy is never a core dependency)."
            ) from exc

        path = Path(path)
        signals = hs.load(str(path), select_type="spectrum_image",
                          convert_units=True, lazy=lazy)
        signals = signals if isinstance(signals, list) else [signals]
        diagnostics: list[Diagnostic] = []
        sig = _select_spectrum_image(signals, diagnostics)

        axes = [AxisInfo(a.index_in_array, a.name, int(a.size), float(a.scale),
                         float(a.offset), (str(a.units) if a.units is not None else None),
                         bool(a.navigate))
                for a in sig.axes_manager._axes]
        title = sig.metadata.get_item("General.title") if sig.metadata.has_item("General.title") else None
        return build_payload(
            data=sig.data, axes=axes, metadata=sig.metadata.as_dictionary(),
            original_metadata=sig.original_metadata.as_dictionary(),
            source_path=path, input_hash=_sha256(path), title=title,
            lazy=lazy, extra_diagnostics=diagnostics)


__all__ = ["READER_VERSION", "AxisInfo", "BrukerBCFReader", "build_payload"]
