"""What the portrait-motion workflow states about itself, read from its workflow file."""

from __future__ import annotations

from stage_gen.workflows._fx import fx_workflow

from .example import import_example

CODE = fx_workflow(
    "stage_gen.workflows.portrait_motion",
    make_inputs="inputs/make_inputs.py",
    import_example=import_example,
)
