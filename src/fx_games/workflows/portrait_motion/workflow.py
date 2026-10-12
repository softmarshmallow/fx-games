"""What the portrait-motion workflow states about itself, read from its workflow file."""

from __future__ import annotations

from fx_games.workflows._fx import fx_workflow

from .example import import_example

CODE = fx_workflow(
    "fx_games.workflows.portrait_motion",
    make_inputs="inputs/make_inputs.py",
    import_example=import_example,
)
