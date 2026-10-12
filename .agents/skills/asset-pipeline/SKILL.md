---
name: asset-pipeline
description: Author or extend an asset workflow on Grida FX (a workflow file or a Python builder, node types, built-in steps) with FX Games' components. Use for asset inputs, generation, judges, cache and takes; keep complete gameplay inside its consuming application.
---

# Asset Pipeline Authoring

Read [AGENTS.md](../../../AGENTS.md), [architecture](../../../ARCHITECTURE.md), and
[the FX guide](https://github.com/gridaco/fx/blob/main/docs/guide/README.md). Begin with explicit inputs, output
artifacts and the judges that admit them. A node type performs one capability; a workflow
composes a bounded asset result. A game is a consumer with its own code and rules.

Write the workflow as an FX workflow file (`workflow.yaml`, `fx: workflow/v1`, beside its own
`fx.yaml`), or as a Python builder when a file cannot state the graph. The home's `fx.yaml`
picks a route per capability (`routes:`) and keeps runs and the store under `out/`; a step's
`requires:` names the features its route must have (`alpha`, `image_input`, `mask`). Use FX's
built-in steps (`fx/<type>@1`, listed by `uv run python -m grida.fx nodes`) where one fits, and
your own `@node` types from `grida.fx` where none does; declare every paid call (`calls=`),
every program (`tools=`, found by `GRIDA_FX_TOOL_<NAME>` or `PATH`) and every file a node reads
(`resources=`). Import only `grida.fx`'s public names. Do not create a scheduler, cache, retry
loop or instruction parser: FX plans, prices, caches by request, retries each paid call (at
most six attempts) and records the run. Version a node type once it is stable, and pin it with
`uv run python -m grida.fx lock`. TOML is optional asset configuration owned by that workflow
or game. It never needs to describe combat, quests, camera controllers or complete gameplay.

Study [looping-parallax](../../../src/fx_games/workflows/looping_parallax/page.mdx) for a
provider-free end-to-end workflow, and the guide's
[example projects](https://github.com/gridaco/fx/blob/main/docs/guide/README.md#example-projects) for the patterns. Keep
runnable samples beside their owner. Plan before any spend
(`uv run python -m grida.fx plan <id> --check`); a live run needs `--live`, a ceiling
(`--max-usd`) and the owner's go. Test a workflow whole with a stand-in
(`grida.fx.run(..., stand_in=...)`) that answers its paid calls offline. Choose takes with
`reroll` and `pick`, which write `<workflow id>.takes.yaml`, and copy results out with
`--deliver`.

Inspect runs in FX's viewer (`uv run python -m grida.fx start --open`), which shows each step's
files on the workflow's canvas. A workflow declares no views of its own.

A Godot game builds its assets with its own FX builder (`pipeline/workflow.py`, beside its
`fx.yaml`) and imports them through its own code. Use
[the consumer template](../../../godot/templates/asset_consumer/README.md) as a starting point.
The product and new asset workflows must not import game pipeline packages,
`demo_game_tools` or `demo_game_collection`.

Verify the public boundary with credential-free `uv run python scripts/check.py`. Run the
web, Godot or games scope when changing those consumers. Follow
[VERIFICATION.md](../../../VERIFICATION.md) for the aggregate gate and live checks. Never
claim generation, visual acceptance or gameplay proof from planning or a stand-in run alone.
