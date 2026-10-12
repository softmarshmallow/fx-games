# Architecture

FX Games provides asset-pipeline authoring, execution and inspection. Consumers own what
those assets mean in a complete application. Dependencies point from consumers to workflows
and components, then to Grida FX, the engine; the product never imports its example games.

## Two products in one repository

FX Games is the main asset-generation product. The Godot example project is a separately
owned consumer product, demonstrating asset use in complete games and developing its own
runtime packages, templates and tools. Its continuing purpose and internal review criteria
are defined in the [Godot project charter](godot/CHARTER.md).

The Godot directory serves as engine-specific examples for FX Games. Internally, it can
evolve as its own project: sharing game systems, extracting packages or reviewing
visual-novel implementations does not expand the main product's scope. The asset product
remains useful without Godot. It runs on Grida FX, a separate public product
pinned as a submodule at `third_party/fx`; that boundary is distinct from the two-product
ownership boundary. Co-location does not require common game formats or synchronized releases.

## Layers

Each layer imports only the layers above it in this list, with one named exception: the glue
reads the registry's declarations in `_registry.py` (`_fx.py` does, and `fx_games.runview`
lazily, to find an installed workflow's file again). The import rules below are what the
tests enforce; this ordering is not tested.

1. **Grida FX** (`third_party/fx`, imported as `grida.fx`) is the engine, a separate product
   pinned as a submodule. It owns the workflow file with its expander, planner, node host,
   store, runner and spending ceiling, the run record, the `python -m grida.fx` command, its
   built-in node types (`fx/<type>@1`), its route table, the provider adapters with their
   retries, and the key loader. FX imports no FX Games package, workflow, game or brand, and
   FX Games imports only its public names.
2. **Glue** (`src/fx_games/workflows/_fx.py`, `src/fx_games/runview/`): FX Games reads FX
   plans for its catalog and checks and writes the scratch projects its code plans in, and
   projects FX run folders to run views (`fx-games-run-view-v1`) for the examples store. It adds
   no graph engine of its own: every workflow, game build and user project is an FX workflow
   file or Python builder.
3. **Components** (`src/fx_games/components/`): bounded building blocks, such as contracts,
   prompts, validators and deterministic processing, that a workflow's node types call. A
   component never runs alone and never imports a workflow. Shared workflow-neutral media
   inspection and transforms belong in `src/fx_games/media/`. See the
   [component contract](src/fx_games/components/README.md).
4. **Examples.** An example is a frozen export of real runs (`workflow-example-v1`), pinned
   by sha256 in its owner's manifest and kept in the local, gitignored store
   `out/examples/<owner>/<id>/`; `fx_games.examples` is its public contract, which reads FX
   runs through `fx_games.runview`, imports no workflow, and which workflow importers and
   games use. `scripts/examples.py promote` refuses a stand-in run. `library/` holds
   committed, approved character-3d examples that the catalog builds from tracked files.
5. **Workflows** (`src/fx_games/workflows/<id>/`): the product unit. A workflow composes
   components into one named deliverable and owns its layout, generation and validation
   assumptions. Its folder holds `workflow.yaml` beside its own `fx.yaml` and `fx.lock`,
   `workflow.py` (the code facts read from the workflow file: typed steps over the real node
   types, persisted identity, an offline sample plan and which runs it owns),
   `workflow.toml` (what code cannot know: title, promise, summary, tools, output notes,
   try-it commands and pinned examples), `page.mdx`, `contract.md`, `example.py`
   where it has an importer, `inputs/` where it has sample inputs, and its implementation.
   `_registry.py`, `_catalog.py` and `_checks.py` read them. The catalog's drift check
   (`scripts/catalog.py --check`) fails when a step and the node types disagree, an
   output note names neither a port of the sample plan nor a path of the cover example, a
   `[try]` command does not parse, `page.mdx` restates the manifest's summary or an output
   note, the README workflow table differs from the manifests, or a stated identity differs
   from the identity golden.
6. **Runs.** A run is one FX run folder under `out/runs/<workflow id>/`: its plan
   (`plan.json`, `fx-graph-v1`), its record (`events.jsonl`) and its steps' files. Results live
   in the store (`out/fx-cache`), so deleting a run folder loses nothing.
   `python -m grida.fx inspect` reads a run back, FX's viewer draws it, and `fx_games.runview`
   projects it for the examples store.
7. **Surfaces.** `python -m grida.fx` plans, runs and inspects every workflow by its id: the
   root `fx.yaml` finds them (`workflows: [src/fx_games/workflows]`), and
   `python -m grida.fx start` serves FX's viewer over their runs. The [site](docs/site.md)
   (`web/site`) is built from the catalog export and the example store. It is the one Bun
   package and the only Node boundary, and keeps its players and data contracts in
   `web/site/lib`.
8. **Consumers.** The Godot example project.

Provider configuration, credentials and concrete services belong to Grida FX: each project's
`fx.yaml` names the routes its calls take, and FX reads the keys and owns the adapters that
serve them. No workflow acquires those responsibilities.

## Import rules

`tests/contract/test_import_boundaries.py` enforces these, and every scan asserts that it
matched at least one file:

- FX is imported only as `from grida.fx import X`, with `X` one of its public names, by the
  product, its tests and scripts, and the games' pipelines and tools.
- FX Games' utilities (`contracts`, `fs`, `provenance`, `canonical`, `media`) import no
  engine, and no Python source in the product names an image model: routes live in `fx.yaml`.
- The retired modules (the old engine's packages, `fx_games.orchestration`, the route-policy
  modules and the rest the test lists) are gone, and nothing imports them.
- Workflows never import each other. A workflow may import its own package,
  `fx_games.workflows._registry` and `fx_games.workflows._fx`.
- Components import no workflow; the registry, catalog, checks, `_fx.py`
  and `fx_games.examples` import no workflow either.
- The product imports no game, and no optional consumer.

## Identity is frozen where it is persisted

Moving or renaming code must not move a cache key or a persisted identity, and
`tests/contract/test_workflow_identity.py` pins them in one machine-independent golden
(`scripts/write_workflow_identity.py` writes it):

- the node-type inventory: every leaf step of each workflow file, with the type identity FX
  resolves its `uses:` to (`fx/mesh.generate@1.1` for a built-in,
  `nodes/assembly.py#assemble@1` for a versioned type of the workflow's own);
- the identities FX gives the instances of offline plans and free runs made only from
  committed or constant bytes, and the keys of the paid calls such a run made through a
  stand-in.

FX derives an unversioned node type's identity from its module, the project modules it
imports and the resources it declares, and `fx.lock` pins a versioned one's source. Neither
globs a folder, so adding `workflow.py`, `example.py` or prose beside an implementation never
changes an identity. The persisted strings that keep an older word (the `recipe` field of
some game documents, the `*-execution-*` kinds) are listed in the [glossary](docs/glossary.md)
so nobody renames them.

Character-3d qualification binds a declared closure rather than every installed byte: its
node types as `fx.lock` pins their source, the workflow file, the core contract versions,
each route with its contract, each paid step's price, the Blender build and the settings the
cohort ran with (`workflows/character_3d/support.py`).

## Bounded contracts and flexible composition

Public components include independent sound effects, speech, repeating images, layers,
movie sprites, video clips, portrait motion and the 3D character's studios. The kits only the
games use (UI, screen and effects artwork, terrain, music, voice profiles, world generation)
live in `demo_game_tools.kits` beside them. Spatial generation and sprite locomotion retain
their precise constraints; host combat and physics stay out. Scenario authoring and execution
belong to the Godot project, independently of asset generation.

The looping-parallax workflow, the first written as a workflow file, owns layer images,
repeat axes, offsets and relative scroll factors. It does not own a player, level or camera controller. Portrait motion owns its
judged chain from one sprite to independent eye and mouth patches; the consuming
presentation decides when that animation plays. These contracts are not combined into a universal gameplay language.

A workflow file states a graph over proven node types, and a workflow's inputs are a YAML
file or flags. Ordinary Python, an FX builder, composes a graph a file cannot state. TOML
remains suitable for a game's asset requests. GDScript and scenes compose Godot games. Do not
require users to describe general-purpose computation or gameplay as YAML or TOML.

## Consumers and optional tools

Runs are seen in FX's viewer (`python -m grida.fx start`); FX Games keeps no viewer of its own
([decision 0075](docs/decisions/0075-runs-are-seen-in-fx.md)). The site never starts a run or
implements a game's logic.

`godot/packages/` contains independently bounded reusable runtime packages. `godot/games/`
contains playable consumers. `godot/templates/` contains starting projects whose preparation
scripts import assets explicitly. A game's configuration is local to that game. No runtime
package has to depend on all other packages.

[Scenario](godot/packages/scenario_runtime/README.md) is the Godot-owned VN-oriented
invocation framework. Its independent Python compiler and native Session executor share one
data contract. A game owns and invokes a sequence, grants installed capabilities, and
retains its world, camera, input, resource bindings and saves. Presentation mechanisms
remain in the lower `game_presentation` package. This framework imposes no game contract or
dependency on FX Games.

Each named game in `godot/games/` owns its authored inputs, optional Python preparation
package, Godot project, gameplay and asset bindings. Existing TOML readers remain supported
game formats; GDScript and resources can replace them when that game's needs warrant it. No
repository-wide selected game exists. A game publishes what it made as examples through
`fx_games.examples` (`demo-games example export <game>`); output only a game can make is an
example made by that game, not a workflow, until it has product-owned inputs, a standalone
product graph and a real product run.

`godot/games/_shared/` holds private implementation with multiple game consumers: bounded
simulation and IO support, input readers and media binding helpers. Shared code imports no
named game. Cross-game CLI dispatch and fixture maintenance live under `godot/tools/`; the
optional `games` installation group supplies that tooling and the individual game
preparation packages. The public product imports none of these packages. Game formats are
documented with their owning game or shared reader, independently of the asset SDK's
authoring contract.

The current division between game-local code, private shared support and runtime packages
may change through review within the Godot project. Reuse between games alone does not make
a mechanism an asset SDK capability. Moving functionality to FX Games requires a separate,
game-independent asset-pipeline responsibility.

`skills/` holds agent skills users install into their own folders (`npx skills add`). Each
stands alone and names no path in this repository; one that calls a provider itself does so
through Grida FX.

## Enforcing the boundary

Import tests enforce FX's public surface, the absence of the retired engine and the absence
of product-to-game dependencies. Package tests verify installed use outside the checkout.
Product verification runs without optional consumers; the aggregate gate additionally
verifies game readers, Godot and the site. Each workflow's graph contract lives in
its `contract.md`, and each game's in that game's docs. There is no repository-wide canonical
game graph.

Cache identity, route preflight, retry ownership, atomic persistence, provenance, path
confinement and media review rules hold through every move. See
[verification](VERIFICATION.md), decisions
[0071](docs/decisions/0071-workflows-are-the-product-unit-and-the-web-splits-into-site-and-viewer.md)
[0074](docs/decisions/0074-stage-gen-runs-on-grida-fx.md) and
[0075](docs/decisions/0075-runs-are-seen-in-fx.md), and the
[directory preview](docs/repository-layout.md).
