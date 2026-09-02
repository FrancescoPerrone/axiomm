"""Tests for :mod:`axiomm.analysis.reference` (Stage two, Chunk S0)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from axiomm.analysis.errors import BackendNotFoundError
from axiomm.analysis.reference import (
    ReferenceLibrary,
    get_reference,
    references,
    register_reference,
)


def test_reference_library_is_frozen_with_version():
    lib = ReferenceLibrary(name="demo", version="1", description="d")
    assert lib.name == "demo"
    assert lib.version == "1"


def test_register_and_get_reference_roundtrips():
    @dataclass(frozen=True)
    class DemoLibrary(ReferenceLibrary):
        pass

    register_reference("demo_v1", lambda: DemoLibrary("demo", "1", ""))
    try:
        lib = get_reference("demo_v1")
        assert isinstance(lib, ReferenceLibrary)
        assert lib.name == "demo"
    finally:
        references.unregister("demo_v1")


def test_get_unknown_reference_raises():
    with pytest.raises(BackendNotFoundError):
        get_reference("does_not_exist")


def test_s0_reference_module_self_registers_nothing():
    # S0 registers no concrete library of its own; tools (e.g. mineralogy,
    # S3a) populate the shared registry. Checked in a subprocess so the
    # observation is not polluted by other imports in this session
    # (the shared `references` registry is a global singleton).
    import subprocess
    import sys

    code = (
        "from axiomm.analysis.reference import references;"
        "assert references.names() == [], references.names()"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
