# AGENTS.md

Repository-specific guardrails. [README.md](README.md) owns setup, [ARCHITECTURE.md](ARCHITECTURE.md) boundaries,
[CONTRIBUTING.md](CONTRIBUTING.md) contribution policy, and [VERIFICATION.md](VERIFICATION.md) gates. Focused procedures
live in [providers](docs/models/providers.md), [publication](docs/generated-media-publication.md), [storage](docs/repository-storage.md),
and [IP](docs/oss-ip.md). This file controls applicability; focused docs control procedure and must be reconciled on conflict.

## Architecture

- Keep identifiers, comments, logs, tests, and user-facing source strings in English.
- This repository has two separately owned products: the main FX Games asset product and the maintained Godot
  example project. [The Godot charter](godot/CHARTER.md) owns the latter's purpose and internal evolution.
  Further runtime, shared game-system or visual-novel refactors belong within Godot; reuse by multiple games
  does not by itself justify moving them into the asset product.
- Python is the headless implementation. Grida FX (`third_party/fx`) is the engine; `src/fx_games/` is the
  application. FX owns the workflow file, planning and prices, the store, the run record, the spending ceiling,
  retries, the built-in node types (`fx/<type>@1`) and the provider adapters. FX Games owns components,
  workflows, the catalog and the run view (`fx_games.runview`) the examples store reads, and adds no engine
  or viewer of its own: runs are seen in FX's viewer.
  FX Games and the game code import FX only as `from grida.fx import X`, with `X` in `grida.fx.__all__`:
  never a private module and never `grida.fx.std`. FX knows no FX Games package, workflow, game or brand;
  provenance identities come from the application. FX Games' utilities (`contracts`, `fs`, `provenance`,
  `canonical`, `media`) import no engine, and the retired modules, the old engine's included, stay gone;
  `tests/contract/test_import_boundaries.py` enforces all of it. Shared workflow-neutral media inspection
  and transforms belong in `media`; capability-specific processing stays with its component, and
  workflow-specific canonicalization with its workflow.
- The product owns asset-pipeline authoring, execution, artifacts and inspection. Components own bounded capabilities;
  workflows compose useful asset outcomes. Their inputs never require a complete game, selected demo or gameplay schema.
  Consumer adapters own runtime camera, scene, engine and gameplay assumptions. `web/site` consumes
  public catalog and example contracts and is not a second generator. Bounded animation, terrain and spatial asset contracts
  may remain optional. Scenario authoring and execution belong to the Godot package; they are not asset-product components.
- Scenario is the Godot-owned VN-oriented invocation framework. Games own and invoke their sequences,
  grant installed capabilities and retain simulation, input, objects, cameras and saves. Keep narrative
  direction in data and mechanism implementations in declared bindings; do not dispatch by story/beat ID.
  `game_presentation` remains a lower dependency and imports no Scenario or game code.
- Complete game builders, gameplay schemas and their existing inputs/readers belong to their Godot game under
  `godot/games/`. Each game owns its project, preparation and bindings. Private reuse by multiple games belongs
  under `godot/games/_shared/`; independently usable runtime packages belong under `godot/packages/`.
  Shared support and packages never import a named game. Preserve supported reader/input pairs
  without requiring a TOML rewrite. Game code may import the public asset product; the product never imports games.
- Each workflow owns its declaration, page, contract and examples. Changes to its stages,
  asset dependencies, consumed inputs, operation counts or cache/scheduling semantics update that evidence together.
  Whole-game graph specifications apply only to their owning game consumers, not every future asset pipeline.

## Grida FX submodule

- `third_party/fx` is [gridaco/fx](https://github.com/gridaco/fx), a separate public product, pinned as a
  submodule. FX Games uses it only through `grida.fx` imports and `uv run python -m grida.fx`, as a path
  dependency on `third_party/fx/python`; its Rust engine is built from the pin with
  `uv run python third_party/fx/tools/build_engine.py` (cargo). Changes to FX follow its own `AGENTS.md` and
  gates, make sense without FX Games, are committed in the submodule, and reach gridaco/fx before FX Games'
  pointer moves (`push.recurseSubmodules=check` refuses a push that would pin an unpushed FX commit). Stage
  Gen's own linters skip `third_party/`.

## Skills

- `skills/<name>/` holds skills users install (`npx skills add`). Each stands alone in any folder: no path into this
  repository and no FX Games command. A skill that calls a provider itself does so through the public Grida FX
  command. `.agents/skills/` (`.claude/skills` links to it) holds only the skills for working on this repository.

## Schema naming

- Schema definitions and persisted/public contract fields use `lower_snake_case`; do not add camelCase aliases for
  convenience. Translate to language-native runtime shapes only at explicit adapters or boundaries. Preserve mandatory
  external-standard vocabulary exactly, including JSON Schema `$ref`, `$defs`, and `additionalProperties`.

## Provider and artifact safety

- A route is `model@provider`, an entry of FX's built-in route table with its price and the features it supports.
  A project's `fx.yaml` picks one per capability (`routes:`) and may add route tables of its own (`route_tables:`).
  A step's `requires:` names what it needs (`alpha`, `image_input`, `mask`), and a route without it is refused
  while planning, offline, before any spend. Do not name a model inside a node's logic.
- FX's engine is the one retry owner of every paid call, with at most six attempts, each reserved against the
  ceiling, recorded and settled. Transport, decoding and the answer's checks (file kind, size, alpha, schema)
  belong to that call. Never retry a call in a node body, an adapter or a loop around it.
- Mark artifacts successful only after validation and atomic persistence. FX places a step's files and records it
  before the step finishes, and reuses a stored result only under its exact identity with every file present;
  FX Games' own writers (`fx_games.fs`) write an artifact and any sidecar rollback-safe. Cache reuse must
  validate content and lineage, not merely path existence.
- Provider keys are read only by FX's allowlisted loader (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `FAL_KEY`,
  `TRIPO_API_KEY`, `ELEVENLABS_API_KEY` and the base URLs `.env.example` names), from the environment or the
  planning project's `.env`. FX Games reads no key's value; its launchers strip the keys from a child's
  environment. Treat `.env` as optional and local; never assume it is populated, overwrite, print, or commit it,
  or copy provider secrets into the site (`web/site`). `.env.example` owns non-secret defaults.
- Offline operation is the default. Planning never spends; a provider call needs `--live`, a ceiling
  (`--max-usd`), explicit task intent and documented opt-in. Tests answer paid calls with FX stand-ins
  (`grida.fx.run(..., stand_in=...)`), never a provider. Re-check current provider contracts before changing a
  route or a model identifier.
- Pipeline run artifacts require canonical portable provenance, because the manifest, cache, and consumers read it;
  an FX run's record holds a run's inputs, routes, costs, digests and attempts.
  A figure or capture authored for the docs is not a pipeline artifact and gets none. Never persist credentials,
  authorization headers, signed URLs, embedded references, private absolute or temporary paths. Confine writes and
  reject traversal or symlink escapes.

## Media and rights

- Use canonical fixtures in place. Copy only across a real package, build, deployment, or public-consumer ownership
  boundary; preserve provenance and rights, do not symlink across it, and never promote unreviewed output into fixtures.
- Prompts, examples, fixtures, and committed media must be original and brand-neutral. Referenced inputs need a
  documented rights basis; source licensing does not grant media redistribution.
- Accepted generated visuals require semantic review by someone other than their producer. Reference inspection and
  exploration do not; label exploration unreviewed. Audio quality claims need a separate listening verdict.
  Semantic regeneration runs are not provider retries.
- Generated media published as art is unapproved by default. Follow publication and storage gates before commit or
  publication; public binding, activation, or publication requires explicit authorization. The gate covers the declared
  publication roots only; `docs/media` and `docs/diagrams` are documentation and carry no sidecar or inventory entry.

## Verification

- Run focused checks for each changed boundary. For Python handoff run credential-free `uv run python scripts/check.py`,
  which builds FX's engine from the pinned submodule first (cargo) and runs FX without keys, `.env` or network;
  follow `VERIFICATION.md` for docs and web gates. Offline gates remain provider-free; live and semantic gates stay
  scoped. A change inside `third_party/fx` also passes FX's own gates.
