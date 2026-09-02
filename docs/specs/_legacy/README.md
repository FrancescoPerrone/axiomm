# Legacy reference material

The files in this directory are **reference-only**. They are preserved so
that future contributors (human or AI) can trace the evolution of AXIOMM
without depending on the original `melt_data_explorer` directory.

* `converter_prototype.py` — the original, single-file converter that the
  package replaces. It mixes input discovery, Tkinter file dialogs,
  `input()` prompts, HDF5 reading, HyperSpy signal construction, and
  saving. The AXIOMM converter splits these into the four core components
  described in `../converter_tool_spec.md`.

## Important caveats

* **Do not import anything from this directory.** It is not part of the
  AXIOMM package. The presence of these files must never affect the
  behaviour of `import axiomm.io.converters`.
* The prototype's licence header claims **MIT** but also contains a
  special-clause acknowledgement for Joshua Franz Einsle. The AXIOMM
  package is licensed under **PolyForm Noncommercial 1.0.0** (see
  `LICENSE` at the repo root). The prototype's licence inconsistency is
  the release blocker described in spec §18; if any portion of the
  prototype is ported into the package, its header must not be carried
  over.
* The prototype is what we are *moving away from*. New contributions
  should target the spec, not the prototype.
