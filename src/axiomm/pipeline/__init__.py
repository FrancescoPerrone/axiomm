"""``axiomm.pipeline`` — AXIOMM's one-call front door (stage two, S5).

Composes the trusted stage-two tools (decomposition → clustering → cluster
spectra → peaks → quantification → reliability → mineral matching) into a single
object that reads like plain English:

    from axiomm import Pipeline

    result = Pipeline().run("map.bcf")          # clusters + spectra
    result = Pipeline(beam_energy_kev=20).run("map.bcf")   # + minerals
    result.clusters
    result.phase_map
    result.summary()
    result.save("out/")

It does as much as the data and settings support and skips honestly (with a
diagnostic) rather than forcing a result. Heavy backends load lazily inside
``run``; importing this package stays cheap.
"""

from __future__ import annotations

from axiomm.pipeline.config import PipelineConfig
from axiomm.pipeline.core import Pipeline, run
from axiomm.pipeline.result import PipelineResult, load_result

__all__ = ["Pipeline", "PipelineConfig", "PipelineResult", "load_result", "run"]
