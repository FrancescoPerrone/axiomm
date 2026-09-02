"""Tests for :mod:`axiomm.analysis.registry` (Stage two, Chunk S0)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from axiomm.analysis.errors import BackendNotFoundError
from axiomm.analysis.registry import Registry, discover_entry_points, load_into


class _Dummy:
    def __init__(self):
        self.name = "dummy"


def test_register_and_get_returns_fresh_instances():
    reg = Registry("backend")
    reg.register("dummy", _Dummy)
    a = reg.get("dummy")
    b = reg.get("dummy")
    assert isinstance(a, _Dummy)
    assert a is not b  # fresh instance per get


def test_get_unknown_raises_backend_not_found():
    reg = Registry("backend")
    with pytest.raises(BackendNotFoundError, match="nope"):
        reg.get("nope")


def test_names_are_sorted_and_membership_works():
    reg = Registry("backend")
    reg.register("beta", _Dummy)
    reg.register("alpha", _Dummy)
    assert reg.names() == ["alpha", "beta"]
    assert "alpha" in reg
    assert "missing" not in reg


def test_unregister_removes_entry():
    reg = Registry("backend")
    reg.register("dummy", _Dummy)
    reg.unregister("dummy")
    assert "dummy" not in reg


def test_unregister_unknown_raises():
    reg = Registry("backend")
    with pytest.raises(BackendNotFoundError):
        reg.unregister("ghost")


def test_string_factory_resolves_lazily():
    from collections import OrderedDict

    reg = Registry("backend")
    # Use a stdlib target so the string spec is always importable, no
    # matter how pytest imports the test files.
    reg.register("od", "collections:OrderedDict")
    # Registration must not import/instantiate eagerly; get() resolves it.
    obj = reg.get("od")
    assert isinstance(obj, OrderedDict)


def test_string_factory_without_colon_is_rejected():
    reg = Registry("backend")
    with pytest.raises(ValueError, match="module.path:AttributeName"):
        reg.register("bad", "no_colon_here")


def test_load_into_registers_discovered_entry_points():
    reg = Registry("decomposer")
    fake_eps = [
        SimpleNamespace(name="pca", value="some.mod:PCA"),
        SimpleNamespace(name="umap", value="other.mod:UMAP"),
    ]
    with patch(
        "axiomm.analysis.registry.importlib.metadata.entry_points",
        return_value=fake_eps,
    ):
        load_into(reg, "axiomm.decomposers")
    assert reg.names() == ["pca", "umap"]


def test_discover_entry_points_yields_name_value_pairs():
    fake_eps = [SimpleNamespace(name="gmm", value="mod:GMM")]
    with patch(
        "axiomm.analysis.registry.importlib.metadata.entry_points",
        return_value=fake_eps,
    ):
        pairs = list(discover_entry_points("axiomm.clusterers"))
    assert pairs == [("gmm", "mod:GMM")]
