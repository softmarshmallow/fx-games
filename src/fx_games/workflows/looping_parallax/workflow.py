"""What the looping-parallax workflow states about itself, read from its workflow file."""

from __future__ import annotations

from fx_games.workflows._fx import fx_workflow

CODE = fx_workflow(
    "fx_games.workflows.looping_parallax",
    make_inputs="inputs/supplied_layers/make_inputs.py",
    no_importer="no example is pinned yet; one would be imported from an FX run",
)
