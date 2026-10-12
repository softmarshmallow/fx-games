# Contributing

Contributions should preserve `fx-games` as a headless, general asset
pipeline with optional consumers.

The [Godot example project](godot/README.md) is a separately owned consumer product
within this repository. Read its [charter](godot/CHARTER.md) before changing its
organization or shared game systems. Such work stays in that project unless a
separate, game-independent asset capability belongs in FX Games.

## Boundaries

- Put reusable asset capabilities in `src/fx_games/components/`. Modality services
  and provider adapters belong to Grida FX (`third_party/fx`), not to FX Games.
- Put shared workflow-neutral media inspection and transforms in
  `src/fx_games/media/`. Keep capability-specific deterministic processing
  with its component contract and workflow-specific canonicalization with its
  workflow.
- Compose them into a workflow under `src/fx_games/workflows/`: an FX workflow file
  whose node types call them. Keep sample inputs in the workflow's `inputs/`.
- Complete games own their preparation packages, input formats, gameplay and
  bindings under `godot/games/<game>/`. Share implementations under
  `godot/games/_shared/` only when multiple games use them. The optional `games`
  installation group provides game tooling; the product imports none of it.
- Independently reusable Godot runtime capabilities and optional game frameworks
  belong in `godot/packages/`, with their own contracts and checks. Review package
  extraction within the Godot project's scope; no common engine is required of
  every example game.
- Keep generation-specific genre, composition, projection, framing, layout,
  artifact, and validation assumptions in workflows. Keep runtime camera, scene,
  engine, movement, combat, and gameplay assumptions in consumer adapters under
  `godot/`.
- Do not import `web/` from a reusable component.
- Keep source identifiers, comments, logs, tests, and user-facing strings in
  English.

## Adding a workflow

A workflow is one folder, `src/fx_games/workflows/<snake_id>/`, whose kebab-case id is the
id `python -m grida.fx` runs it by (the root `fx.yaml` finds it there), the site slug and the
docs path. The folder name is the id with `-` written as `_`, and a test holds them equal.

1. Write `workflow.yaml` (`fx: workflow/v1`) beside its own `fx.yaml`, the workflow's home:
   its `routes:`, `sources:` and the shared `out/runs` and `out/fx-cache`. Put its node types
   under `nodes/` with the prompts and schemas they read, and use a built-in (`fx/<type>@1`)
   wherever one fits. `uv run python -m grida.fx lock src/fx_games/workflows/<snake_id>` pins
   the versioned types in `fx.lock`. A node imports the components it needs and only the
   public names of `grida.fx`.
2. `workflow.py` exports `CODE`, from `fx_workflow` (`fx_games.workflows._fx`): the steps
   and node types are read from the workflow file (each leaf step is one type, under its
   top-level step), with `identity()`, an offline `sample_plan` over committed or drawn
   sample inputs (or a stated reason it has none), and `owns_run`.
3. `workflow.toml` holds only what code cannot know: title, promise, summary, related
   workflows, tools, output notes, a `[try]` table of real `python -m grida.fx` commands, and
   pinned examples.
4. `page.mdx` is the reader's page; `contract.md` is the exact contract, with a
   `> **Checked by:**` line. A workflow with a sample plan carries its graph-contract block,
   written by `uv run python scripts/write_workflow_contracts.py --write`.
5. `example.py` is its example importer, when it has one.
6. Add the workflow's row to the README table, and pin its persisted identities in the
   identity golden that `scripts/write_workflow_identity.py` writes; `CODE.identity()` must
   agree with it. Its tests run it whole on FX stand-ins (`grida.fx.run(..., stand_in=...)`),
   never on a provider. Then run
   `uv run python scripts/catalog.py --check --allow-missing-examples --out <scratch>`.

An example is promoted from real runs with `scripts/examples.py promote`; it is pinned by
digest and stays in the local store. Committing run media or deploying the site follows
[generated-media publication](docs/generated-media-publication.md).

### When a game's output becomes a workflow

Output only a game can make is an example made by that game: its prose, pins and importer
live with the game, and `demo-games example export <game>` writes it to the store through
`fx_games.examples`. It becomes a product workflow once it has product-owned inputs, a
standalone product graph and a real product run. The UI kit and parallax from a reference
are the first candidates.

## Provider work

Provider adapters, routes, prices and the key loader belong to
[Grida FX](https://github.com/gridaco/fx); a change to them is made in
`third_party/fx` under FX's own rules and gates, and reaches gridaco/fx before FX Games'
pointer moves. In FX Games, a project picks routes in its `fx.yaml`, and a step's
`requires:` names the features its route must have. Use documented env variable names and
never commit or print credentials. FX's engine is the one retry owner of every paid call,
with at most six attempts; never retry a call in a node body or a loop around it. Persist
non-secret provenance and validate media before marking a run successful.

## Prompts and media

Follow [docs/oss-ip.md](docs/oss-ip.md). Prompts and examples must request
original work using neutral properties, without named franchises, brands,
artists, studios, games, recordings, or recognizable creator-style imitation.

Do not add binary media without documented provenance and a clear rights
basis. Repository code licensing does not grant rights to generated or
third-party assets.

Generated media in publication roots must follow the
[artifact-specific publication policy](docs/generated-media-publication.md).
A technically valid provider response remains runtime-unreviewed until its
sidecar rights, inventory status, and any required human review are approved.

## Checks

Run the checks relevant to your change. At minimum for public documentation:

```sh
uv run python scripts/check_docs.py
uv run --group games pytest tests/unit/test_media_rights.py tests/contract/test_docs_check.py -q
uv run pytest tests/contract/test_documented_commands.py tests/contract/test_workflow_contract_docs.py -q
```

The docs gate also keeps the retired words of the [glossary](docs/glossary.md) out of the
front-page documents and every workflow's `page.mdx` and `contract.md`.

For product Python code, run its credential-free gate:

```sh
uv run python scripts/check.py
```

Use `--scope all` after installing all workspace groups for changes across owners.
See [VERIFICATION.md](VERIFICATION.md) for the separate consumer gates.

For the site (`web/site`), run:

```sh
cd web/site
bun install --frozen-lockfile
bun run check
bun test
cd ../..
uv run python scripts/site.py build --allow-missing-examples
```

See [docs/testing.md](docs/testing.md) for focused module commands. For code,
run the workspace's type, test, build, and headless smoke commands.
Tests make no provider calls: paid calls are answered by FX stand-ins. A live run is
opt-in, with `--live` and a ceiling; its FX run record keeps the route, cost, digests and
attempts without credentials.

Keep generated run output, populated env files, caches, local screenshots, and
OS metadata out of Git.
