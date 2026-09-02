"""Output writers for the AXIOMM converter.

Each concrete writer implements the :class:`~axiomm.io.converters.writers.base.Writer`
protocol and is registered with the converter registry (added in a later chunk).
Importing this subpackage must not import any optional dependency; those
imports belong inside concrete writer modules.
"""

from __future__ import annotations

from axiomm.io.converters.writers.base import Writer

__all__ = ["Writer"]


# HSpyWriter is lazily importable via the converters package __getattr__
# so the writers package itself doesn't need to import it eagerly.
