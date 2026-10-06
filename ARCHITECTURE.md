# Architecture

Stage Gen provides asset-pipeline authoring, execution and inspection. Consumers own what
those assets mean in a complete application. Dependencies point from consumers to workflows
and components, then to GNode; the product never imports its example games.

## Two products in one repository

Stage Gen is the main asset-generation product. The Godot example project is a separately
owned consumer product, demonstrating asset use in complete games and developing its own
runtime packages, templates and tools. Its continuing purpose and internal review criteria
are defined in the [Godot project charter](godot/CHARTER.md).

The Godot directory serves as engine-specific examples for Stage Gen. Internally, it can
evolve as its own project: sharing game systems, extracting packages or reviewing
visual-novel implementations does not expand the main product's scope. The asset product
remains useful without Godot. GNode and the Stage Gen application are layers of that main
product; this is distinct from the two-product ownership boundary. Co-location does not
require common game formats or synchronized releases.

## Layers

Each layer imports only the layers above it in this list, with two named exceptions: the
character-3d run reader in `workflow.py` imports `stage_gen.runs` for the run-view file, and `_checks.py` imports the CLI parser lazily to parse `[try]` commands. The
import rules below are what the tests enforce; this ordering is not tested.

1. **Grida FX** (`third_party/fx`, imported as `grida.fx`) is the engine, a separate product
   pinned as a submodule. It owns the workflow file with its expander, planner, node host,
   call cache, runner and spending ceiling, the run record, the `python -m grida.fx` command,
   its built-in node types (`fx/…`), and the provider adapters with their retries. FX imports
   no Stage Gen package, workflow, game or brand, and Stage Gen imports only its public names.
2. **Glue** (`src/stage_gen/workflows/_fx.py`, `src/stage_gen/runview/`, `src/stage_gen/viewer.py`):
   Stage Gen reads FX plans for its catalog and checks, projects FX run folders to run views,
   and starts the viewer. It adds no graph engine of its own: every workflow, game build and
   user project is an FX workflow file or Python builder.
3. **Components** (`src/stage_gen/components/`): bounded building blocks with their node types,
   graph fragments, contracts and services. A component never runs alone and never imports
   a workflow. Shared workflow-neutral media inspection and transforms belong in
   `src/stage_gen/media/`. See the [component contract](src/stage_gen/components/README.md).
4. **Examples.** An example is a frozen export of real runs (`workflow-example-v1`), pinned
   by sha256 in its owner's manifest and kept in the local, gitignored store
   `out/examples/<owner>/<id>/`; `stage_gen.examples` is its public contract, which imports
   only GNode and which workflow importers and games use. `library/` holds committed,
   approved character-3d examples that the catalog builds from tracked files.
5. **Workflows** (`src/stage_gen/workflows/<id>/`): the product unit. A workflow composes
   components into one named deliverable and owns its layout, generation and validation
   assumptions. Its folder holds `workflow.yaml` beside its own `gnode.yaml`, `workflow.py`
   (the code facts read from the workflow file: typed steps over the real node types,
   persisted identity, an offline sample plan and which runs it owns),
   `workflow.toml` (what code cannot know: title, promise, summary, tools, output notes,
   try-it commands and pinned examples), `page.mdx`, `contract.md`, `example.py`
   where it has an importer, `inputs/` where it has sample inputs, and its implementation.
   `_registry.py`, `_catalog.py` and `_checks.py` read them. The catalog's drift check
   (`scripts/catalog.py --check`) fails when a step and the node types disagree, an
   output note names neither a port of the sample plan nor a path of the cover example, a
   `[try]` command does not parse, `page.mdx` restates the manifest's summary or an output
   note, the README workflow table differs from the manifests, or a stated identity differs
   from the identity golden.
6. **Runs.** A run is one gnode run folder: its plan, its record (`events.jsonl`) and its
   steps' files. `gnode inspect` reads it back, and `gnode view` keeps its run view.
7. **Surfaces.** The `gnode` command line plans, runs and inspects every workflow by its id.
   The [viewer](docs/viewer.md) (`web/viewer`, the dashboard `gnode view` starts, installed
   by `stage_gen.viewer`) reads run folders. The [site](docs/site.md) (`web/site`) is built from the catalog
   export and the example store. `web/` is one Bun workspace and the only Node boundary;
   the viewer and the site share only `web/ui` and the versioned data contracts.
8. **Consumers.** The Godot example project.

Provider configuration, credentials and concrete services belong to Grida FX: each project's
`fx.yaml` names the routes its calls take, and FX reads the keys and owns the adapters that
serve them. No workflow acquires those responsibilities.

## Import rules

`tests/contract/test_import_boundaries.py` enforces these, and every scan asserts that it
matched at least one file:

- FX is imported only as `from grida.fx import X`, with `X` one of its public names.
- Workflows never import each other. A workflow may import its own package, its own frozen
  implementation root and `stage_gen.workflows._registry`.
- Components import no workflow; the registry, catalog, checks and `stage_gen.examples`
  import no workflow either.
- The product imports no game, and no optional consumer.

## Identity is frozen where it is persisted

Moving or renaming code must not move a cache key or a persisted identity, and
`tests/contract/test_workflow_identity.py` pins them in one machine-independent golden:

- every member of the character-3d implementation;
- graph-document literals and kinds, cache record kinds, the node-type inventory (a
  workflow file's steps with the locked versions of the node types they use), provenance
  names and the run-view schema version;
- the cache keys of plans and free runs made only from committed or constant bytes, and the
  call keys of paid calls such a run made through a stand-in.

No digest may glob a workflow folder. A digest names its files, so adding `workflow.py`,
`cli.py`, `example.py` or prose beside an implementation never changes an identity. The
persisted strings that keep an older word (the graph-document field `recipe`, the
`*-execution-*` kinds) are
listed in the [glossary](docs/glossary.md) so nobody renames them.

Character-3d qualification binds a declared closure rather than every installed byte: its
node types as `gnode.lock` pins their source, the workflow file, the core contract versions,
its routes and prices, and the Blender build (`workflows/character_3d/support.py`).

## Bounded contracts and flexible composition

Public components include independent sound effects, speech, music, voice profiles, UI
artwork, screen artwork, effects artwork, terrain, layers, sprites and portrait motion.
Spatial generation and sprite locomotion retain their precise constraints; host combat and
physics stay out. Scenario authoring and execution belong to the Godot project,
independently of asset generation.

The looping-parallax workflow, the first written as a gnode workflow file, owns layer images,
repeat axes, offsets and relative scroll factors. It does not own a player, level or camera controller. Portrait motion owns its
judged chain from one sprite to independent eye and mouth patches; the consuming
presentation decides when that animation plays. These contracts are not combined into a universal gameplay language.

TOML remains suitable for a workflow's asset requests. Ordinary Python is the composition
language for arbitrary graphs. GDScript and scenes compose Godot games. Do not require users
to describe general-purpose computation or gameplay as TOML.

## Consumers and optional tools

The viewer reads public graph, trace, manifest and view records, and derives a missing view
into a user cache, never into a run folder. It never starts a run or implements a game's
logic. Basic previews are generic; specialist inspectors are optional adapters over bounded
metadata. Unknown preview contracts retain readable metadata rather than disappearing.

`godot/packages/` contains independently bounded reusable runtime packages. `godot/games/`
contains playable consumers. `godot/templates/` contains starting projects whose preparation
scripts import assets explicitly. A game's configuration is local to that game. No runtime
package has to depend on all other packages.

[Scenario](godot/packages/scenario_runtime/README.md) is the Godot-owned VN-oriented
invocation framework. Its independent Python compiler and native Session executor share one
data contract. A game owns and invokes a sequence, grants installed capabilities, and
retains its world, camera, input, resource bindings and saves. Presentation mechanisms
remain in the lower `game_presentation` package. This framework imposes no game contract or
dependency on Stage Gen.

Each named game in `godot/games/` owns its authored inputs, optional Python preparation
package, Godot project, gameplay and asset bindings. Existing TOML readers remain supported
game formats; GDScript and resources can replace them when that game's needs warrant it. No
repository-wide selected game exists. A game publishes what it made as examples through
`stage_gen.examples` (`demo-games example export <game>`); output only a game can make is an
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
a mechanism an asset SDK capability. Moving functionality to Stage Gen requires a separate,
game-independent asset-pipeline responsibility.

`skills/` holds agent skills users install into their own folders (`npx skills add`). Each
stands alone and names no path in this repository; one that calls a provider itself does so
through Grida FX.

## Enforcing the boundary

Import tests enforce GNode rings and the absence of product-to-game dependencies. Package
tests verify installed use outside the checkout. Product verification runs without optional
consumers; the aggregate gate additionally verifies game readers, Godot and the web
workspace. Each workflow's graph contract lives in its `contract.md`, and each game's
in that game's docs. There is no repository-wide canonical game graph.

Cache identity, route preflight, retry ownership, atomic persistence, provenance, path
confinement and media review rules hold through every move. See
[verification](VERIFICATION.md), decision
[0071](docs/decisions/0071-workflows-are-the-product-unit-and-the-web-splits-into-site-and-viewer.md)
and the [directory preview](docs/repository-layout.md).
