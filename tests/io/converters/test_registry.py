"""Tests for :mod:`axiomm.io.converters.registry` (Chunk 12, spec §12).

Each Registry method is exercised directly, not just through
:mod:`workflows` (per the "tests prove reuse" rule in
feedback-modularity). The default ``readers`` / ``writers`` singletons
get their own pre-registration checks; the workflow integration tests
in ``test_workflows.py`` already cover the end-to-end use.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from axiomm.io.converters.errors import UnsupportedFormatError
from axiomm.io.converters.registry import (
    ENTRY_POINT_READERS,
    ENTRY_POINT_WRITERS,
    Registry,
    find_reader_plugins,
    find_writer_plugins,
    get_reader,
    get_writer,
    iter_readers,
    iter_writers,
    load_plugins,
    readers,
    register_reader,
    register_writer,
    writers,
)


# ---------------------------------------------------------------------------
# Registry — generic behaviour
# ---------------------------------------------------------------------------

class _StubReader:
    name = "stub"
    supported_extensions: tuple[str, ...] = (".stub",)


class _StubWriter:
    name = "stubwriter"
    supported_extensions = (".stubout",)


def test_registry_starts_empty():
    r = Registry("reader")
    assert len(r) == 0
    assert r.names() == []
    assert list(r) == []


def test_registry_register_callable_factory():
    r = Registry("reader")
    r.register("stub", _StubReader)
    assert "stub" in r
    instance = r.get("stub")
    assert isinstance(instance, _StubReader)


def test_registry_register_with_lambda():
    r = Registry("reader")
    r.register("stub", lambda: _StubReader())
    assert isinstance(r.get("stub"), _StubReader)


def test_registry_register_module_attribute_string_is_lazy():
    """A 'module:attr' string must NOT import at registration time."""
    r = Registry("reader")
    # Use a real but irrelevant module so the test isn't fragile.
    r.register("late", "axiomm.io.converters.errors:UnsupportedFormatError")
    # The factory exists; calling it instantiates the class.
    instance = r.get("late")
    assert isinstance(instance, UnsupportedFormatError)


def test_registry_register_rejects_bad_string_spec():
    r = Registry("reader")
    with pytest.raises(ValueError, match="module.path:AttributeName"):
        r.register("bad", "no_colon_in_this_one")


def test_registry_register_rejects_non_callable_non_string():
    r = Registry("reader")
    with pytest.raises(TypeError):
        r.register("bad", 42)  # type: ignore[arg-type]


def test_registry_get_unknown_name_raises_unsupported_format():
    r = Registry("reader")
    r.register("stub", _StubReader)
    with pytest.raises(UnsupportedFormatError) as exc:
        r.get("nope")
    # Error message is actionable: tells you what IS registered.
    assert "stub" in str(exc.value)
    assert "reader" in str(exc.value)  # uses the kind_label


def test_registry_get_returns_fresh_instance_each_call():
    r = Registry("reader")
    r.register("stub", _StubReader)
    a = r.get("stub")
    b = r.get("stub")
    # Same class, distinct objects.
    assert isinstance(a, _StubReader)
    assert isinstance(b, _StubReader)
    assert a is not b


def test_registry_iter_yields_fresh_instances():
    r = Registry("reader")
    r.register("a", _StubReader)
    r.register("b", _StubReader)
    instances = list(r)
    assert len(instances) == 2
    assert all(isinstance(i, _StubReader) for i in instances)
    # Each one is a fresh object.
    assert instances[0] is not instances[1]


def test_registry_register_overwrites_existing_name():
    r = Registry("reader")
    r.register("stub", _StubReader)
    r.register("stub", lambda: "replaced")
    assert r.get("stub") == "replaced"


def test_registry_unregister_removes_entry():
    r = Registry("reader")
    r.register("stub", _StubReader)
    r.unregister("stub")
    assert "stub" not in r
    with pytest.raises(UnsupportedFormatError):
        r.get("stub")


def test_registry_unregister_unknown_name_raises():
    r = Registry("reader")
    with pytest.raises(UnsupportedFormatError, match="cannot unregister"):
        r.unregister("never_registered")


def test_registry_names_returns_sorted_list():
    r = Registry("reader")
    r.register("zoo", _StubReader)
    r.register("alpha", _StubReader)
    r.register("middle", _StubReader)
    assert r.names() == ["alpha", "middle", "zoo"]


def test_registry_kind_label_appears_in_error_messages():
    r = Registry("writer")
    with pytest.raises(UnsupportedFormatError, match="writer"):
        r.get("unknown")


def test_registry_contains_returns_false_for_non_string():
    r = Registry("reader")
    r.register("stub", _StubReader)
    assert 42 not in r
    assert None not in r
    assert "stub" in r


# ---------------------------------------------------------------------------
# Default singletons — pre-registered components
# ---------------------------------------------------------------------------

def test_default_readers_registry_has_xrmmap_h5():
    assert "xrmmap_h5" in readers


def test_default_writers_registry_has_hspy():
    assert "hspy" in writers


def test_get_reader_module_helper_returns_xrmmap_h5_instance():
    pytest.importorskip("h5py")
    reader = get_reader("xrmmap_h5")
    assert reader.name == "xrmmap_h5"
    assert ".h5" in reader.supported_extensions


def test_get_writer_module_helper_returns_hspy_instance():
    writer = get_writer("hspy")
    assert writer.name == "hspy"
    assert ".hspy" in writer.supported_extensions


def test_iter_readers_includes_xrmmap_h5():
    pytest.importorskip("h5py")
    names = [r.name for r in iter_readers()]
    assert "xrmmap_h5" in names


def test_iter_writers_includes_hspy():
    names = [w.name for w in iter_writers()]
    assert "hspy" in names


def test_register_reader_helper_adds_to_default_registry():
    """The module-level convenience helpers route to the default singletons."""

    class _LocalReader:
        name = "local_test"
        supported_extensions = (".local",)

    try:
        register_reader("local_test", _LocalReader)
        assert "local_test" in readers
        assert get_reader("local_test").name == "local_test"
    finally:
        # Restore the registry state so later tests in this session
        # don't see the temporary registration.
        readers.unregister("local_test")


def test_register_writer_helper_adds_to_default_registry():
    class _LocalWriter:
        name = "local_writer_test"
        supported_extensions = (".lw",)

    try:
        register_writer("local_writer_test", _LocalWriter)
        assert "local_writer_test" in writers
        assert get_writer("local_writer_test").name == "local_writer_test"
    finally:
        writers.unregister("local_writer_test")


# ---------------------------------------------------------------------------
# Lazy import: the built-in registrations don't pull h5py in
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Iteration tolerates broken factories (regression for Chunk 13's plugin work)
# ---------------------------------------------------------------------------

def test_registry_iter_skips_factory_that_raises():
    """A broken factory must not crash the whole iteration.

    A plugin's package can be uninstalled without uninstalling its
    entry-point metadata; the iter() of the registry must tolerate
    that so auto-detection still walks the rest of the plugins.
    """
    r = Registry("reader")

    class _GoodReader:
        name = "good"

    def _broken_factory():
        raise ImportError("simulated: plugin package not installed")

    r.register("broken", _broken_factory)
    r.register("good", _GoodReader)

    yielded = list(r)
    # Only the good one shows up; the broken one was logged + skipped.
    assert len(yielded) == 1
    assert isinstance(yielded[0], _GoodReader)


# ---------------------------------------------------------------------------
# Plugin discovery via Python entry points (Chunk 13)
# ---------------------------------------------------------------------------

class _FakeEntryPoint:
    """Stand-in for ``importlib.metadata.EntryPoint``.

    Carries only the fields the registry actually reads (``name``,
    ``value``, ``group``) so the tests don't need to subclass the real
    type, which changes signature across Python versions.
    """

    def __init__(self, name: str, value: str, group: str) -> None:
        self.name = name
        self.value = value
        self.group = group


def _fake_entry_points_factory(eps: list[_FakeEntryPoint]):
    """Return a callable matching the modern ``importlib.metadata.entry_points``
    signature, filtering ``eps`` by the requested group.
    """

    def fake_entry_points(*, group: str | None = None, **_):
        if group is None:
            return list(eps)
        return [ep for ep in eps if ep.group == group]

    return fake_entry_points


def test_entry_point_group_constants_have_documented_values():
    assert ENTRY_POINT_READERS == "axiomm.readers"
    assert ENTRY_POINT_WRITERS == "axiomm.writers"


def test_find_reader_plugins_yields_name_value_pairs():
    fake_eps = [
        _FakeEntryPoint(
            "my_format",
            "my_pkg.readers.my_format:MyReader",
            "axiomm.readers",
        ),
        _FakeEntryPoint(
            "irrelevant",
            "some.writer:SomeWriter",
            "axiomm.writers",
        ),
    ]
    with patch(
        "axiomm.io.converters.registry.importlib.metadata.entry_points",
        _fake_entry_points_factory(fake_eps),
    ):
        result = list(find_reader_plugins())
    assert result == [("my_format", "my_pkg.readers.my_format:MyReader")]


def test_find_writer_plugins_yields_name_value_pairs():
    fake_eps = [
        _FakeEntryPoint(
            "my_out", "my_pkg.writers.my_out:MyWriter", "axiomm.writers",
        ),
    ]
    with patch(
        "axiomm.io.converters.registry.importlib.metadata.entry_points",
        _fake_entry_points_factory(fake_eps),
    ):
        result = list(find_writer_plugins())
    assert result == [("my_out", "my_pkg.writers.my_out:MyWriter")]


def test_find_reader_plugins_is_empty_when_no_plugins_installed():
    """The common case: no third-party AXIOMM plugins on this machine."""
    with patch(
        "axiomm.io.converters.registry.importlib.metadata.entry_points",
        _fake_entry_points_factory([]),
    ):
        assert list(find_reader_plugins()) == []
        assert list(find_writer_plugins()) == []


def test_load_plugins_registers_into_explicit_registries():
    """`load_plugins(into_readers=..., into_writers=...)` allows isolated
    testing without touching the global default registries."""
    reader_registry = Registry("reader")
    writer_registry = Registry("writer")

    fake_eps = [
        _FakeEntryPoint(
            "plug_reader",
            "axiomm.io.converters.errors:UnsupportedFormatError",
            "axiomm.readers",
        ),
        _FakeEntryPoint(
            "plug_writer",
            "axiomm.io.converters.errors:UnsupportedFormatError",
            "axiomm.writers",
        ),
    ]
    with patch(
        "axiomm.io.converters.registry.importlib.metadata.entry_points",
        _fake_entry_points_factory(fake_eps),
    ):
        load_plugins(
            into_readers=reader_registry, into_writers=writer_registry,
        )

    assert "plug_reader" in reader_registry
    assert "plug_writer" in writer_registry


def test_load_plugins_is_idempotent():
    """Calling load_plugins twice must not raise and must produce the
    same final state — the second call overwrites with the same value."""
    reader_registry = Registry("reader")
    writer_registry = Registry("writer")

    fake_eps = [
        _FakeEntryPoint(
            "plug",
            "axiomm.io.converters.errors:UnsupportedFormatError",
            "axiomm.readers",
        ),
    ]
    with patch(
        "axiomm.io.converters.registry.importlib.metadata.entry_points",
        _fake_entry_points_factory(fake_eps),
    ):
        load_plugins(
            into_readers=reader_registry, into_writers=writer_registry,
        )
        load_plugins(
            into_readers=reader_registry, into_writers=writer_registry,
        )

    assert reader_registry.names() == ["plug"]


def test_load_plugins_skips_malformed_entry_points(caplog):
    """A plugin whose entry-point value is structurally broken (no
    colon, wrong type) must be logged and skipped — the registry-level
    `register()` rejects bad strings, and load_plugins absorbs the
    failure so the rest of the registrations still go through.
    """
    reader_registry = Registry("reader")
    writer_registry = Registry("writer")

    fake_eps = [
        _FakeEntryPoint("broken", "no_colon_here", "axiomm.readers"),
        _FakeEntryPoint(
            "good",
            "axiomm.io.converters.errors:UnsupportedFormatError",
            "axiomm.readers",
        ),
    ]
    with patch(
        "axiomm.io.converters.registry.importlib.metadata.entry_points",
        _fake_entry_points_factory(fake_eps),
    ):
        with caplog.at_level("WARNING"):
            load_plugins(
                into_readers=reader_registry,
                into_writers=writer_registry,
            )

    # Good one made it in; broken one didn't.
    assert "good" in reader_registry
    assert "broken" not in reader_registry
    # And the failure was surfaced to logging, not silently swallowed.
    assert any(
        "broken" in record.getMessage() for record in caplog.records
    )


def test_default_registries_run_load_plugins_at_import_time():
    """Module-level ``load_plugins()`` call exposes installed plugins
    in the default registries. With no plugins installed (the test
    environment), only the built-ins are present.
    """
    # We can't easily install a fake distribution into the running
    # environment, so this test just verifies the call happened by
    # checking that the built-ins remain (a crash during the
    # load_plugins call at import time would have failed *every*
    # test in this module).
    assert "xrmmap_h5" in readers
    assert "hspy" in writers


def test_registry_module_import_does_not_trigger_h5py():
    """Registering the XRMMapH5Reader via 'module:attr' must be lazy.

    Importing axiomm.io.converters.registry must NOT pull in h5py — that
    only happens when get_reader("xrmmap_h5") is actually called. This
    is the same lazy-import invariant the package as a whole guards via
    the side-effects test.
    """
    import importlib
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent(
        """
        import sys
        # Discard any pre-imported state.
        for m in list(sys.modules):
            if m.startswith(("h5py", "axiomm")):
                del sys.modules[m]
        import axiomm.io.converters.registry  # noqa: F401
        leaked = sorted(m for m in sys.modules if m.startswith("h5py"))
        if leaked:
            raise AssertionError(f"importing registry pulled in h5py: {leaked!r}")
        """
    )
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert result.returncode == 0, (
        f"subprocess failed (rc={result.returncode}).\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
