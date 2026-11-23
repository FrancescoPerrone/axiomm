"""Chunk 1 — plain-English facade names, resolved additively to canonical config."""

from __future__ import annotations

import numpy as np
import pytest

from axiomm.analysis.errors import PayloadValidationError
from axiomm.io.converters.models import AxiommSignalPayload, AxisSpec
from axiomm.pipeline import Pipeline


def _tiny_payload(ny=8, nx=8, ne=600, seed=0):
    rng = np.random.default_rng(seed)
    e = np.arange(ne) * 0.02
    cube = np.full((ny, nx, ne), 3.0)
    cube[: ny // 2] += 200 * np.exp(-((e - 1.74) ** 2) / (2 * 0.06 ** 2))   # Si
    cube[ny // 2:] += 220 * np.exp(-((e - 6.40) ** 2) / (2 * 0.06 ** 2))    # Fe
    cube += rng.normal(0, 2.0, cube.shape).clip(min=-3)
    axes = (
        AxisSpec("y", "navigation", ny, units="µm", scale=1.0, offset=0.0, index_in_array=0),
        AxisSpec("x", "navigation", nx, units="µm", scale=1.0, offset=0.0, index_in_array=1),
        AxisSpec("Energy", "signal", ne, units="keV", scale=0.02, offset=0.0, index_in_array=2),
    )
    return AxiommSignalPayload(data=cube, axes=axes, signal_kind="signal1d")


# -- aliases resolve to the canonical config ---------------------------------

def test_facade_words_resolve_to_canonical_config():
    new = Pipeline(beam_energy="13.55 keV", clusters=7, library="minerals_default_v2",
                   naming_policy="family_aware", exclude_elements=["Ba"])
    old = Pipeline(beam_energy_kev=13.55, groups=7, reference="minerals_default_v2",
                   classification="family_aware", exclude_elements={"Ba"})
    # identical resolved config -> an identical (deterministic) run
    assert new._config_dict() == old._config_dict()
    assert new.config.exclude_elements == frozenset({"Ba"})
    assert new.config.beam_energy_kev == 13.55
    assert new.config.groups == 7


def test_facade_energy_string_parsed():
    assert Pipeline(beam_energy="2900 eV").config.beam_energy_kev == pytest.approx(2.9)
    assert Pipeline(beam_energy=13.55).config.beam_energy_kev == 13.55
    with pytest.raises(PayloadValidationError):
        Pipeline(beam_energy="13.55")       # a bare-number string has no unit


@pytest.mark.parametrize("kw", [
    {"beam_energy": "13.55 keV", "beam_energy_kev": 13.55},
    {"clusters": 7, "groups": 7},
    {"library": "a", "reference": "b"},
    {"naming_policy": "a", "classification": "b"},
])
def test_facade_rejects_word_and_alias_together(kw):
    with pytest.raises(PayloadValidationError):
        Pipeline(**kw)


def test_exclude_elements_accepts_list_rejects_bare_string():
    assert Pipeline(exclude_elements=["Ba", "Cs"]).config.exclude_elements == frozenset({"Ba", "Cs"})
    with pytest.raises(PayloadValidationError):
        Pipeline(exclude_elements="Ba")     # would iterate to 'B','a'


def test_unknown_keyword_still_detected():
    with pytest.raises(TypeError):
        Pipeline(not_a_real_setting=1)


# -- end-to-end: new words run and write_report writes -----------------------

def test_facade_run_and_write_report(tmp_path):
    result = Pipeline(beam_energy="13.55 keV", library="minerals_default_v2", clusters=4,
                      naming_policy="family_aware", exclude_elements=["Ba"]).run(_tiny_payload())
    assert len(result.clusters) >= 1
    out = result.write_report(tmp_path / "r.html")
    assert out.exists() and out.suffix == ".html"


def test_new_vs_old_words_scientifically_equivalent(tmp_path):
    payload = _tiny_payload()
    new = Pipeline(beam_energy="13.55 keV", library="minerals_default_v2", clusters=4,
                   naming_policy="family_aware", seed=1).run(payload)
    old = Pipeline(beam_energy_kev=13.55, reference="minerals_default_v2", groups=4,
                   classification="family_aware", seed=1).run(payload)
    # same cluster assignment and same per-cluster labels (deterministic, seed-locked)
    assert np.array_equal(np.asarray(new.label_map), np.asarray(old.label_map))
    assert [r["label"] for r in new.clusters] == [r["label"] for r in old.clusters]
    # and the same quantification + reliability where minerals ran
    if new.quantification and old.quantification:
        assert [dict(q.net_intensities) for q in new.quantification] == \
               [dict(q.net_intensities) for q in old.quantification]
    if new.reliability and old.reliability:
        assert ([r.cluster_status for r in new.reliability]
                == [r.cluster_status for r in old.reliability])
