"""What the universe workflow states about itself, read from its workflow file."""

from __future__ import annotations

from fx_games.workflows._fx import fx_workflow

CODE = fx_workflow(
    "fx_games.workflows.universe",
    sample_inputs="inputs/lantern_ferry/inputs.yaml",
    no_importer="no example is pinned yet; one would be imported from an FX run",
)
