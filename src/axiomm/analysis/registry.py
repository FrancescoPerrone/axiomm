"""Protocol-agnostic backend registry for the analysis suite.

Generalises :mod:`axiomm.io.converters.registry`. A :class:`Registry`
maps a stable string name to a lazy factory (a no-argument callable, or
a ``"module.path:AttributeName"`` string resolved on first use). One
instance per swappable kind — a ``decomposers`` registry in
:mod:`axiomm.analysis.decomposition`, a ``clusterers`` registry in
:mod:`axiomm.analysis.clustering`, a ``references`` registry in
:mod:`axiomm.analysis.reference` — all reuse this class.

Entry-point discovery is parameterised by group name so each kind
declares its own group (``axiomm.decomposers``, ``axiomm.clusterers``,
...).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from collections.abc import Iterator
from typing import Any, Callable, Union

from axiomm.analysis.errors import BackendNotFoundError

logger = logging.getLogger(__name__)

#: A factory is a callable returning an instance, or a ``"module:attr"``
#: string resolved lazily to such a callable.
Factory = Union[Callable[[], Any], str]


class Registry:
    """Stable-string-name registry for a single kind of analysis backend.

    ``kind_label`` is used in error messages (``"decomposer"`` vs.
    ``"clusterer"``) so lookups fail with the right vocabulary.
    """

    def __init__(self, kind_label: str) -> None:
        self._kind = kind_label
        self._factories: dict[str, Callable[[], Any]] = {}

    def register(self, name: str, factory: Factory) -> None:
        """Register ``factory`` under ``name`` (replacing any existing entry)."""
        self._factories[name] = _normalise_factory(factory)

    def unregister(self, name: str) -> None:
        """Drop ``name``; raise :class:`BackendNotFoundError` if absent."""
        if name not in self._factories:
            raise BackendNotFoundError(
                f"No {self._kind} registered under {name!r}; cannot unregister."
            )
        del self._factories[name]

    def get(self, name: str) -> Any:
        """Return a fresh instance for ``name`` (factory invoked once per call)."""
        if name not in self._factories:
            raise BackendNotFoundError(
                f"Unknown {self._kind} name {name!r}. "
                f"Known {self._kind}s: {sorted(self._factories)}."
            )
        return self._factories[name]()

    def names(self) -> list[str]:
        """Sorted list of registered names — useful for help text."""
        return sorted(self._factories)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._factories

    def __len__(self) -> int:
        return len(self._factories)


def _normalise_factory(factory: Factory) -> Callable[[], Any]:
    """Convert a ``Factory`` into a no-argument callable returning an instance."""
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
    """Return a callable that imports ``spec`` (``"module:attr"``) on first use."""
    module_path, attribute = spec.split(":", 1)

    def _resolve() -> Any:
        module = importlib.import_module(module_path)
        klass = getattr(module, attribute)
        return klass()

    _resolve.__name__ = f"resolve_{module_path.replace('.', '_')}_{attribute}"
    return _resolve


def discover_entry_points(group: str) -> Iterator[tuple[str, str]]:
    """Yield ``(name, "module:attr")`` for each entry point in ``group``.

    Empty when no plugins are installed for that group.
    """
    for ep in importlib.metadata.entry_points(group=group):
        yield ep.name, ep.value


def load_into(registry: Registry, group: str) -> None:
    """Discover entry points in ``group`` and register them into ``registry``.

    Idempotent. A plugin whose ``value`` cannot be registered (malformed
    spec) is logged at WARNING and skipped; the rest still register.
    """
    for name, spec in discover_entry_points(group):
        try:
            registry.register(name, spec)
        except Exception as exc:  # noqa: BLE001 — plugin-loading boundary
            logger.warning(
                "axiomm.analysis: skipping %s plugin %r=%r: %s",
                group, name, spec, exc,
            )


__all__ = [
    "Factory",
    "Registry",
    "discover_entry_points",
    "load_into",
]
