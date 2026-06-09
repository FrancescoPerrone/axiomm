"""Reader / writer registry for the AXIOMM converter (Chunk 12, spec §12).

A small, lazy, stable-string-name registry. Replaces the hand-rolled
``_BUILTIN_READERS`` / ``_BUILTIN_WRITERS`` dicts that previously lived in
:mod:`workflows`. One :class:`Registry` instance per component kind —
readers and writers — exported as the module-level singletons
:data:`readers` and :data:`writers`.

Lazy by design: each entry stores a callable that returns the instance,
not the instance itself, so registering ``XRMMapH5Reader`` does not pull
in ``h5py`` until the reader is actually resolved. The two convenient
shapes a ``factory`` can take are:

* A no-argument callable returning an instance (a class, a lambda,
  anything else with ``__call__``).
* A ``"module.path:AttributeName"`` string — resolved with
  :func:`importlib.import_module` on first use. This is the path
  third-party plugins will take when entry-point discovery lands
  (Chunk 13).

The Registry class is intentionally protocol-agnostic. It is used here
for readers and writers, but the same shape works for any future
component kind that wants stable string names without forcing eager
imports.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any, Callable, Union

from axiomm.io.converters.errors import UnsupportedFormatError

#: A factory either is a callable returning an instance, or a
#: ``"module:attr"`` string resolved lazily to such a callable.
Factory = Union[Callable[[], Any], str]


class Registry:
    """Stable-string-name registry for converter components.

    One instance per component kind. The ``kind_label`` is used in
    error messages so users get the right vocabulary back when a
    lookup fails (``"reader"`` vs. ``"writer"``).
    """

    def __init__(self, kind_label: str) -> None:
        self._kind = kind_label
        self._factories: dict[str, Callable[[], Any]] = {}

    # -- registration ------------------------------------------------------

    def register(self, name: str, factory: Factory) -> None:
        """Register ``factory`` under ``name``.

        Replaces any existing entry with the same name. Users who care
        about that being noisy should check :meth:`__contains__` first.
        """
        self._factories[name] = _normalise_factory(factory)

    def unregister(self, name: str) -> None:
        """Drop the registration for ``name``.

        Raises :class:`UnsupportedFormatError` if no such entry exists,
        so test isolation can be explicit about what it expected to find.
        """
        if name not in self._factories:
            raise UnsupportedFormatError(
                f"No {self._kind} registered under {name!r}; cannot unregister."
            )
        del self._factories[name]

    # -- lookup ------------------------------------------------------------

    def get(self, name: str) -> Any:
        """Return a fresh instance for ``name``.

        Each call invokes the registered factory once, so callers can
        rely on getting a clean instance per lookup (no shared mutable
        state across uses).
        """
        if name not in self._factories:
            raise UnsupportedFormatError(
                f"Unknown {self._kind} name {name!r}. "
                f"Known {self._kind}s: {sorted(self._factories)}."
            )
        return self._factories[name]()

    def names(self) -> list[str]:
        """Return the sorted list of registered names — useful for help text."""
        return sorted(self._factories)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._factories

    def __iter__(self) -> Iterator[Any]:
        """Iterate over fresh instances of every registered component.

        Order is the registration order; for deterministic iteration
        either pin registration order at module level or sort
        :meth:`names` and dispatch through :meth:`get`.
        """
        for factory in self._factories.values():
            yield factory()

    def __len__(self) -> int:
        return len(self._factories)


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------

def _normalise_factory(factory: Factory) -> Callable[[], Any]:
    """Convert a ``Factory`` (callable or ``"module:attr"`` string) into
    a no-argument callable that returns an instance."""
    if isinstance(factory, str):
        if ":" not in factory:
            raise ValueError(
                f"Factory string must be 'module.path:AttributeName'; got {factory!r}."
            )
        return _from_import_string(factory)
    if not callable(factory):
        raise TypeError(
            f"Factory must be a callable or 'module:attr' string, got "
            f"{type(factory).__name__}: {factory!r}."
        )
    return factory


def _from_import_string(spec: str) -> Callable[[], Any]:
    """Return a callable that imports ``spec`` (``"module:attr"``) on first use.

    The import happens at call time, not at registration time, so heavy
    optional dependencies (h5py, hyperspy, ...) only load when the
    component is actually resolved.
    """
    module_path, attribute = spec.split(":", 1)

    def _resolve() -> Any:
        module = importlib.import_module(module_path)
        klass = getattr(module, attribute)
        return klass()

    _resolve.__name__ = f"resolve_{module_path.replace('.', '_')}_{attribute}"
    return _resolve


# ---------------------------------------------------------------------------
# Module-level default registries + pre-registered built-ins
# ---------------------------------------------------------------------------

#: Default reader registry. Pre-populated with the built-in readers.
readers: Registry = Registry("reader")

#: Default writer registry. Pre-populated with the built-in writers.
writers: Registry = Registry("writer")


# Lazy-import specs for the built-in components: never trigger h5py or
# hyperspy imports unless somebody actually resolves the matching name.
readers.register(
    "xrmmap_h5",
    "axiomm.io.converters.readers.xrmmap_h5:XRMMapH5Reader",
)

writers.register(
    "hspy",
    "axiomm.io.converters.writers.hspy:HSpyWriter",
)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def register_reader(name: str, factory: Factory) -> None:
    """Register a reader factory in the default :data:`readers` registry."""
    readers.register(name, factory)


def register_writer(name: str, factory: Factory) -> None:
    """Register a writer factory in the default :data:`writers` registry."""
    writers.register(name, factory)


def get_reader(name: str) -> Any:
    """Return an instance of the reader registered under ``name``."""
    return readers.get(name)


def get_writer(name: str) -> Any:
    """Return an instance of the writer registered under ``name``."""
    return writers.get(name)


def iter_readers() -> Iterator[Any]:
    """Iterate over fresh instances of every registered reader."""
    return iter(readers)


def iter_writers() -> Iterator[Any]:
    """Iterate over fresh instances of every registered writer."""
    return iter(writers)


__all__ = [
    "Factory",
    "Registry",
    "get_reader",
    "get_writer",
    "iter_readers",
    "iter_writers",
    "readers",
    "register_reader",
    "register_writer",
    "writers",
]
