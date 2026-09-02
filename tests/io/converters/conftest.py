"""Shared fixtures for AXIOMM converter tests.

Two builders live here, each one focused on a single job:

* :func:`_build_xrmmap_h5` (exposed as the ``synthetic_xrmmap_h5``
  fixture) — minimal-but-valid XRM-map HDF5 with switches for
  omitting each dataset group; used by per-feature unit tests
  (missing-metadata branches, override paths, etc.). Spec §20.1.
* :func:`_build_realistic_xrmmap_h5` (exposed as the
  ``realistic_xrmmap_h5`` fixture) — XRM-map file that reproduces
  the *structural* gotchas real instrument files exhibit:
  ``(n_rois, n_variants, 2)`` ROI-limits layout, a populated
  environ table with the keys real XRM-Map/Larch software writes,
  and a non-trivial counts shape. Used for the end-to-end
  regression in :mod:`test_realistic_xrmmap_regression`.

The two are deliberately separate: the synthetic one stays the
smallest thing the reader will accept (so unit tests are clear about
what they're varying), and the realistic one stays focused on
matching real-world structural shapes.
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


# Realistic XRM-map structural defaults — used by the
# realistic_xrmmap_h5 fixture below. Names sampled from a real Larch /
# XRM-Map file; values are synthetic but plausible. The keys here exist
# so any real-file change in the wider AXIOMM toolchain that depends on
# these has a regression to point at.
_REALISTIC_SHAPE: tuple[int, int, int] = (8, 6, 1024)
_REALISTIC_N_ROI_VARIANTS: int = 7

_REALISTIC_ENVIRON: dict[str, str] = {
    "Experiment.User_Name": "AXIOMM Test User",
    "Experiment.Proposal_Number": "00000",
    "Experiment.Beam_Size__Nominal": "2um",
    "Experiment.Monochromator_Crystal": "Si(111)",
    "Experiment.Double_H_Mirror_Stripes": "silicon",
    "Experiment.Bpm_Foil": "Cr",
    "Experiment.Ssa_Horiz_Width__Mm": "0.025",
    "Experiment.Ssa_Vert_Width__Mm": "0.025",
    "Experiment.Kb_Mirror_Stripes": "silicon",
    "Experiment.Detector_Type": "Vortex ME-4",
    "Experiment.Detector_Element_Count": "4",
    "Experiment.Beam_Energy_Ev": "12000",
    "Experiment.Dwell_Time_Sec": "0.5",
    "Experiment.Date": "2024-01-15",
    "Experiment.Beamline": "AXIOMM-Test",
    "Scan.Start_Energy_Ev": "12000",
    "Scan.End_Energy_Ev": "12000",
    "Scan.Step_Count": "1",
    "Map.Width_Um": "16",
    "Map.Height_Um": "12",
    "Map.X_Step_Um": "2",
    "Map.Y_Step_Um": "2",
    "Sample.Description": "AXIOMM test sample",
    "Sample.Holder": "Kapton tape",
    "Mca.Channels": "1024",
    "Mca.Bin_Width_Ev": "10",
    "Mca.Live_Time_Sec": "0.5",
    "Mca.Real_Time_Sec": "0.51",
    "Mca.Dead_Time_Frac": "0.02",
    "Mca.Energy_Calibration_Slope": "0.01",
    "Mca.Energy_Calibration_Intercept": "0.0",
}

_REALISTIC_ROI_NAMES: list[str] = [
    "OutputCounts",
    "Si Ka", "Zr L", "P Ka", "S Ka", "Cl Ka",
    "K Ka", "Ca Ka", "Ti Ka", "V Ka", "Cr Ka",
    "Mn Ka", "Fe Ka", "Co Ka", "Ni Ka",
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


def _build_realistic_xrmmap_h5(
    path: Path,
    *,
    shape: tuple[int, int, int] = _REALISTIC_SHAPE,
    n_roi_variants: int = _REALISTIC_N_ROI_VARIANTS,
    seed: int = 42,
) -> Path:
    """Write a real-shape XRM-map HDF5 file at ``path`` and return the path.

    Captures the structural patterns the synthetic fixture omits:

    * ROI limits dataset of shape ``(n_rois, n_roi_variants, 2)`` —
      the layout real Larch / XRM-Map files use, not the 2-D one the
      legacy prototype assumed.
    * Environ table populated with the ~30 keys real instrument files
      ship, including ``Experiment.Beam_Size__Nominal`` so the
      reader's beam-size-driven navigation scale is exercised.
    * Counts dataset shape distinct from the 4×3×16 unit-test default.

    The function is also exported as the ``realistic_xrmmap_h5``
    fixture below; both forms exist on purpose so the helper is
    independently importable for ad-hoc use, not only via pytest's
    fixture mechanism.
    """
    import h5py

    rng = np.random.default_rng(seed)

    # Counts dataset.
    counts = rng.integers(0, 1000, size=shape, dtype=np.int32)
    n_channels = shape[2]

    # Environ table: real-instrument-shaped key/value strings.
    env_names = np.array(list(_REALISTIC_ENVIRON.keys()), dtype="S128")
    env_values = np.array(list(_REALISTIC_ENVIRON.values()), dtype="S128")

    # ROI limits: variant 0 carries the canonical (centi-keV) values,
    # other variants get a sentinel so a reader that picked the wrong
    # variant index would visibly fail downstream.
    n_rois = len(_REALISTIC_ROI_NAMES)
    roi_limits = np.full((n_rois, n_roi_variants, 2), 9999, dtype=np.int32)
    canonical_starts = rng.integers(
        100, max(n_channels - 50, 200), size=n_rois,
    )
    roi_limits[:, 0, 0] = canonical_starts
    roi_limits[:, 0, 1] = canonical_starts + 30

    roi_names = np.array(_REALISTIC_ROI_NAMES, dtype="S64")

    with h5py.File(path, "w") as f:
        f.create_dataset("/xrmmap/mcasum/counts", data=counts)
        f.create_dataset("/xrmmap/config/environ/name", data=env_names)
        f.create_dataset("/xrmmap/config/environ/value", data=env_values)
        f.create_dataset("/xrmmap/config/rois/name", data=roi_names)
        f.create_dataset("/xrmmap/config/rois/limits", data=roi_limits)

    return path


@pytest.fixture
def realistic_xrmmap_h5(tmp_path: Path):
    """Factory fixture: build a real-shape XRM-map HDF5 file in ``tmp_path``.

    Usage::

        def test_round_trip(realistic_xrmmap_h5):
            path = realistic_xrmmap_h5("realistic.h5")
            ...

    Accepts every keyword argument of :func:`_build_realistic_xrmmap_h5`.
    """

    def _make(name: str = "realistic.h5", **kwargs) -> Path:
        return _build_realistic_xrmmap_h5(tmp_path / name, **kwargs)

    return _make
