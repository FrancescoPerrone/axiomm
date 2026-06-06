"""Signal builders for the AXIOMM converter.

A signal builder turns a neutral :class:`AxiommSignalPayload` into a
backend-specific signal object (HyperSpy ``BaseSignal``, xarray ``Dataset``,
plain numpy array — whatever a downstream analysis pipeline expects).

Importing this subpackage must not import HyperSpy or any other heavy
backend; those imports belong inside concrete builder modules so the package
is usable in environments where only a subset of backends is installed.
"""

from __future__ import annotations

from axiomm.io.converters.signals.base import SignalBuilder
from axiomm.io.converters.signals.validation import validate_axes

__all__ = ["SignalBuilder", "validate_axes"]
