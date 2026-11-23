"""Example B — the same workflow as a reusable, importable module.

Importing this module runs **no** analysis and writes **no** files: the work lives
in a function a caller invokes. The caller gets the result back for inspection.

    from examples.api.example_b_analysis_module import analyse
    result = analyse("A21_066_map1_002.h5", "A21_066_report.html")
    print(result.summary())
"""
from __future__ import annotations

from axiomm import Pipeline


def analyse(source, report_path):
    """Run the standard analysis on ``source``, write its report to ``report_path``,
    and return the :class:`PipelineResult` for further inspection."""
    result = Pipeline(
        beam_energy_kev=13.55,
        reference="minerals_default_v2",
        groups=7,
        exclude_elements={"Ba"},
        normalize=True,
        classification="family_aware",
    ).run(source)
    result.report_html(report_path, overwrite=True)
    return result


# No module-level analysis, no writes at import time — importing is free of side effects.
