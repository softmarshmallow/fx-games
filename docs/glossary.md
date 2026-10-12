# Glossary

The words FX Games uses for its parts, the words it retired, and the persisted strings that
keep an old word because changing them would change an identity.

## Terms

| Term | Meaning |
|---|---|
| Grida FX | The engine every workflow runs on ([gridaco/fx](https://github.com/gridaco/fx)), a submodule at `third_party/fx`: the workflow file, planning and prices, the store, the run record, retries, the built-in node types and the provider adapters. FX Games runs it as `uv run python -m grida.fx` and imports it as `grida.fx`. |
| node type | What a step uses: an FX built-in (`fx/<type>@1`) or a type of the workflow's own (`./nodes/<file>.py#<function>`, an `@node` body taking `Ctx`). The catalog lists each leaf step of a workflow file as one type, `<folder>/<step path>`, titled by the step's `title:` (a reader label, kept out of cache keys); the identity golden (`tests/contract/fixtures/workflow-identity.json`) pins the type identity FX resolves its `uses:` to. |
| node | One step instance in a plan, with its identity. |
| component | A package under `src/fx_games/components/`: contracts, prompts, validators and deterministic processing that a workflow's node types call. It never runs alone and never imports a workflow. |
| workflow | One folder under `src/fx_games/workflows/` that makes one kind of deliverable: its workflow file (`workflow.yaml`) beside its own `fx.yaml` and `fx.lock`, `workflow.py`, `workflow.toml`, `page.mdx`, `contract.md`, its node types and, where it has them, `example.py` (its example importer) and `inputs/`. The root `fx.yaml` finds it by its id, so `python -m grida.fx plan <id>` and `run <id>` plan and run it; its kebab-case id is that word, the site's slug and the docs path. |
| project | A folder with an `fx.yaml`: where its runs (`runs:`) and store (`cache:`) go, the routes its calls take (`routes:`) and, for the root project, where workflows are found by id (`workflows:`). Each workflow home is one, and so is each game folder that builds with FX. |
| step | A top-level step of a workflow file, with its `title:` and `description:`, as readers see it. Every leaf step under it is one node type, and every node type sits in exactly one step. |
| input | A folder a run reads. A workflow's committed sample inputs live in its `inputs/<name>/`. |
| run | One execution folder. A chain, such as a take and then its finish, is several runs. |
| example | A frozen export of real runs (`example.json`, `figures.json` and `media/`), pinned by sha256 in its owner's manifest and made by a workflow or a game. It is the only result the site shows. An example made with an earlier version of its workflow says so behind a disclosure. |
| take | One draw of a step's request. `takes:` draws several at once, `python -m grida.fx reroll` draws the next, and `pick` keeps one in the takes file, `<workflow id>.takes.yaml`: beside a builder (a game's `pipeline/<id>.takes.yaml`) or a workflow file whose home is the project you run from, else at the root of the project you run from (the installed workflows, found by id from the root `fx.yaml`, keep theirs at the checkout root, such as `universe.takes.yaml`). An audition is a take a person chose, which a run may adopt by digest as a file. |
| stand-in | A function that answers a run's paid calls in a test, offline and for nothing (`grida.fx.run(..., stand_in=...)`); its answers pass the checks a provider's do, and its records stay apart from real ones. |
| SDK | Grida FX's Python package, `grida.fx`: a builder (`Workflow`, `plan`, `run`), node types (`@node` over a body taking `Ctx`) and stand-ins. FX Games' workflows and every game build are written with it. |
| run view | `fx-games-run-view-v1`: `fx_games.runview`'s projection of an FX run folder, which the examples store reads. |
| catalog | The `fx-games-catalog-v1` JSON that `scripts/catalog.py` writes from the installed workflows and the example store. It is derived and never committed. |
| site | `web/site`, the static landing and documentation, built from the catalog and the example store. |
| viewer | FX's viewer, which `uv run python -m grida.fx start --open` opens: the local, read-only canvas over a project's plans and runs. FX Games keeps none of its own (decision 0075). |

## Retired terms

| Retired | Now |
|---|---|
| Stage Gen, the `stage-gen` repository and distribution, the `stage_gen` package, the `stage-gen-<contract>-v1` kinds | FX Games, `fx-games`, `fx_games` and `fx-games-<contract>-v1` (decision 0076). The persisted strings that keep the old name are listed below. |
| recipe | workflow. The persisted fields that keep the word are listed below. |
| `RecipeGraph`, `RecipeExecutor`, `RecipePlan`, `RecipeRun`, `GraphDocument`, `GraphExecutor`, `PlannedGraph`, `GraphRun`, `CachedNodeHandler` | an FX workflow file or Python builder, run by `python -m grida.fx run` |
| `stage_gen.pipeline` (`define`, `plan`, `run`, `inspect`, dry runs, the node cache) | Grida FX: `Workflow` with `plan` and `run`, stand-ins, and the store |
| gnode, `gnode_std`, the `gnode` command, `gnode.yaml`, `gnode.lock`, `gnode/<type>@1` | Grida FX (decision 0074): `python -m grida.fx`, `fx.yaml`, `fx.lock`, `fx/<type>@1` |
| `gnode view`, `gnode-run-view-v1` | `python -m grida.fx start`, `fx-games-run-view-v1` |
| injected services, `HostServices`, `WorkflowRun` and `CallRecord` test doubles, the live provider tests and their `live` marker | stand-ins (`grida.fx.run(..., stand_in=...)`) |
| the route-policy layer, the model policy snapshot, `STAGE_GEN_*_MODEL` overrides | FX's built-in route table and a project's `routes:` and `route_tables:` |
| feature names `transparent_background`, `reference_images` | `alpha`, `image_input` |
| `workflow.takes.yaml` | `<workflow id>.takes.yaml` |
| `GNODE_TOOL_<NAME>` | `GRIDA_FX_TOOL_<NAME>` |
| harness | SDK |
| showcase | site |
| showcase record, adapter | example, importer (`example.py`) |
| `node_labels`, `[[stages]]` | a step's `title:` and the workflow file's top-level steps |
| web viewer, run viewer | viewer |
| scripts/view.py, web/viewer, `stage_gen.viewer`, view contexts, step and workflow view templates, `STAGE_GEN_RUN_ROOTS`, `STAGE_GEN_VIEW_CACHE` | FX's viewer, `python -m grida.fx start` (decision 0075) |
| capability, meaning a package under `components/` | component |
| `stage-gen-py`, `stage-gen-character`, `stage-gen-portrait-motion`, `stage-gen-movie-sprite`, and the `stage-gen` command line | `python -m grida.fx`, with no aliases: `schema <id>` for `show`, `start` for `view`, `nodes` for `models routes` |
| `stage-gen catalog export`, `stage-gen example verify`, `stage-gen example promote` | `scripts/catalog.py`, `scripts/examples.py` |
| `stage-gen capability <call>` | a step's takes: a one-step workflow, or the build's own step, with `reroll` and `pick` |
| `body idle`, `face repaint`, `prepare`, `verify`, `generate`, `semantic` and `gallery` as verbs | `plan`, `run` and `inspect`, with flags such as `--inputs`, `--live` and `--verify` |
| movie-sprite's `--input-root`, `--output-root`, `--cache-root`; character-3d's experiment file and launcher flags | an inputs file (`python -m grida.fx plan movie-sprite --inputs take.yaml`) |
| `export-view`, `stage-gen inspect --write-view` | `python -m grida.fx start`, whose viewer draws every FX run; every game builds with FX, and a game's run is an FX run |
| `STAGE_GEN_OUT_DIR` | a project's runs go where its `fx.yaml` says (`out/runs`) |
| a workflow's `examples/` input bundles | its `inputs/` |
| `examples/pipelines`, `docs/sdk/pipelines/` (SDK samples), `docs/guide` | the FX guide and its example projects, in gridaco/fx |
| a workflow's `README.md` and its guide under `docs/` | its `page.mdx` and `contract.md` |

## Frozen persisted strings

These keep their old words because they are written into runs, caches or digests. Leave them
as they are:

- the `<word>-execution-{graph,event,summary,projection,view}` kinds and `pipeline-execution-*`;
- the `recipe` and `recipe_version` fields of the game documents that carry them, such as The
  Grain's dialogue scene (`dialogue-scene-v8`);
- the `@stage-gen/<name>` provenance names, the `stage-gen` tool identity and the
  `stage-gen-headless` source of committed media sidecars;
- the `stage-gen/dialogue-scene/...` digest domains of The Grain's dialogue scene;
- the bytes of committed game inputs, comments included, which their package digests pin.

The domain phrases "rig recipe" and "crafting recipe" are unrelated and stay.
