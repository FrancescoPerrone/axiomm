"""Example A — one analysis, the way a non-coding scientist (Isra) would run it.

This is the acceptance target for the "reads like a sentence" review, in the
**current** API. Configure one analysis (the scientific choices together), run it,
keep the result, and write its report — each with its own line.

Run this file to exercise it on a tiny synthetic map (no real data needed):

    python examples/api/example_a_one_analysis.py
"""
from __future__ import annotations

from axiomm import Pipeline


def analyse_one(source, report_path):
    """Configure, run, and report a single analysis; return the result."""
    # The scientific choices, in one place.
    pipeline = Pipeline(
        beam_energy_kev=13.55,                 # the acquisition energy
        reference="minerals_default_v2",       # the mineral library to match against
        groups=7,                              # how many clusters to look for
        exclude_elements={"Ba"},               # drop Ba (its line overlaps Ti here)
        normalize=True,                        # per-incident-photon footing (I0)
        classification="family_aware",         # species when clear, else family, else unresolved
    )

    result = pipeline.run(source)              # read + run the whole analysis
    result.report_html(report_path, overwrite=True)   # write the interactive report
    return result


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    from examples.api._fixture import synthetic_payload

    out = Path(tempfile.mkdtemp()) / "example_a_report.html"
    result = analyse_one(synthetic_payload(), out)
    print(result.summary())
    print("report written:", out, "exists:", out.exists())
