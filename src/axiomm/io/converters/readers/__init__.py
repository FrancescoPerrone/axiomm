"""Format-specific readers for the AXIOMM converter.

Each concrete reader implements the :class:`~axiomm.io.converters.readers.base.Reader`
protocol and is registered with the converter registry (added in a later chunk).
Importing this subpackage must not import any optional dependency
(``h5py``, instrument SDKs, etc.) — those imports belong inside concrete
reader modules so the package remains usable without them.
"""

from __future__ import annotations

from axiomm.io.converters.readers.base import Reader

__all__ = ["Reader"]
