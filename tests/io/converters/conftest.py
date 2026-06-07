"""Shared fixtures for AXIOMM converter tests.

Provides :func:`synthetic_xrmmap_h5`, a factory fixture that writes a
minimal-but-valid XRM-map style HDF5 file into the per-test ``tmp_path``,
with switches for omitting each top-level dataset group so the reader's
missing-metadata branches can be exercised. Spec §20.1.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


DEFAULT_SHAPE: tuple[int, int, int] = (4, 3, 16)

_DEFAULT_ENVIRON: dict[str, str] = {
    "Experiment.Beam_Size__Nominal": "1 um",
    "Experiment.Detector": "Synthetic",
}

_DEFAULT_ROIS: list[tuple[str, int, int]] = [
    ("Fe Ka", 640, 670),  # 6.40 – 6.70 keV at roi_limit_scale = 0.01
    ("Cu Ka", 800, 830),  # 8.00 – 8.30 keV
]


def _build_xrmmap_h5(
    path: Path,
    *,
    shape: tuple[int, int, int] = DEFAULT_SHAPE,
    environ: dict[str, str] | None = None,
    rois: list[tuple[str, int, int]] | None = None,
    roi_limits_override: np.ndarray | None = None,
    include_counts: bool = True,
    include_environ: bool = True,
    include_rois: bool = True,
    seed: int = 0,
) -> Path:
    """Write a synthetic XRM-map HDF5 file at ``path`` and return the path.

    Defaults match the spec §20.1 shape ``(4, 3, 16)``. Use the include
    flags to omit each dataset group and drive missing-metadata branches
    in the reader.

    Use ``roi_limits_override`` to write a custom ROI limits array (any
    shape) — useful for testing the real-file `(n_rois, n_variants, 2)`
    case the prototype didn't handle. When given, the integer values in
    ``rois`` are ignored; only the names matter.
    """
    import h5py  # imported here so the conftest itself does not require h5py at collection

    rng = np.random.default_rng(seed)
    environ_data = dict(_DEFAULT_ENVIRON) if environ is None else dict(environ)
    rois_data = list(_DEFAULT_ROIS) if rois is None else list(rois)

    with h5py.File(path, "w") as f:
        if include_counts:
            data = rng.integers(0, 100, size=shape, dtype=np.int32)
            f.create_dataset("/xrmmap/mcasum/counts", data=data)
        if include_environ:
            names = np.array(list(environ_data.keys()), dtype="S128")
            values = np.array(list(environ_data.values()), dtype="S128")
            f.create_dataset("/xrmmap/config/environ/name", data=names)
            f.create_dataset("/xrmmap/config/environ/value", data=values)
        if include_rois:
            roi_names = np.array([r[0] for r in rois_data], dtype="S64")
            if roi_limits_override is not None:
                roi_limits = np.asarray(roi_limits_override)
            else:
                roi_limits = np.array(
                    [[r[1], r[2]] for r in rois_data], dtype=np.int32
                )
            f.create_dataset("/xrmmap/config/rois/name", data=roi_names)
            f.create_dataset("/xrmmap/config/rois/limits", data=roi_limits)

    return path


@pytest.fixture
def synthetic_xrmmap_h5(tmp_path: Path):
    """Factory fixture: build a synthetic XRM-map HDF5 file in ``tmp_path``.

    Usage::

        def test_xxx(synthetic_xrmmap_h5):
            path = synthetic_xrmmap_h5("ok.h5", shape=(4, 3, 16))
            ...

    Accepts every keyword argument of :func:`_build_xrmmap_h5`.
    """

    def _make(name: str = "synth.h5", **kwargs) -> Path:
        return _build_xrmmap_h5(tmp_path / name, **kwargs)

    return _make
