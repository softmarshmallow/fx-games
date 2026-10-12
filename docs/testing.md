# Testing FX Games

All verification is credential-free, and no test calls a provider. A test that runs a
workflow or a game build runs it whole on Grida FX with a stand-in
(`grida.fx.run(..., stand_in=...)`): a function that answers each paid call offline, for
nothing, through the same answer checks a provider's answer gets. The helpers in
`tests/unit/_fx.py` write the scratch projects such runs use, so their runs and store stay
in the test's own folder.

## Focused matrix

| Surface | Command |
|---|---|
| Reusable components | `uv run pytest tests/unit/components -q` |
| Verified single-axis image repeats | `uv run pytest tests/unit/components/image_repeat -q` |
| Deterministic media | `uv run pytest tests/unit/media -q` |
| Workflows | `uv run pytest tests/unit/workflows -q` |
| Game-owned graphs | `uv run pytest tests/unit/games -q` |
| CLI boundary | `uv run pytest tests/integration -q` |
| Wheel-packaged resources | `uv run pytest tests/contract/test_packaged_resources.py -q` |
| Import architecture | `uv run pytest tests/contract/test_import_boundaries.py -q` |
| Persisted identities | `uv run pytest tests/contract/test_workflow_identity.py -q` |
| Run views | `uv run pytest tests/unit/test_runview.py -q` |
| Godot owners | `uv run --group games python godot/tools/check.py` |
| Scenario compiler/runtime/embedding | `uv run --group games python godot/tools/check.py --owner scenario_runtime` |
| Formatting and lint | `uv run ruff format --check . && uv run ruff check .` |
| Strict typing | `uv run mypy --strict src tests scripts` |

The Godot coordinator accounts for all maintained packages, games and templates.
Its native-game adapter uses authored temporary fixtures, including Ember Hollow
fixtures from `godot/games/ember_hollow/tools/make_fixture_run.py`. A fresh clone has
no `out/` media. Naming a real run with `--run` adds assertions pinned to that run;
prepared-media and rendered suites have explicit scopes and prerequisites. An
offline state check does not prove a picture or listening quality. See [Godot host](../godot/games/ember_hollow/docs/runtime.md) and
[decision 0068](decisions/0068-the-suite-reads-a-world-the-repository-can-write.md).

Tests that plan or run need FX's engine: build it once with
`uv run python third_party/fx/tools/build_engine.py` (cargo), and again after a pull that
moves the submodule's pin, or point `GRIDA_FX_BIN` at a built one.

The product gate is `uv run python scripts/check.py`. It builds the engine first and needs no
Bun or Godot.
Use the owning optional scope or `--scope all` for the complete repository gate,
after `uv sync --all-groups --frozen`. See [VERIFICATION.md](../VERIFICATION.md).
The retained game tests require the optional `games` workspace group; use it when
selecting old test directories directly.

The pre-push hook checks each pushed commit in a temporary worktree, preserving the
working checkout. It installs all groups, then runs the format and lint checks, the web tests
and the contract tests, after building FX's engine for the pinned FX commit (needs cargo).

## Live runs

There are no live tests. A provider is reached only by a live run, `--live` with a ceiling
(`--max-usd`), made with explicit task intent and the owner's go, never as part of CI or an
offline check. Its FX run record keeps the route, cost, digests and attempts without
credentials. Visual output accepted as evidence still requires semantic review by a
non-producer; audio quality review is separate from deterministic media validation.

## Site

The site (`web/site`) uses Bun for Next.js tooling. It consumes published contracts
and starts nothing:

```sh
cd web/site
bun install --frozen-lockfile
bun run check
bun test
```

Site tests cover the catalog and example parsers, the players' cleanup, page binding,
doc links and Python-faithful number formatting. A build must not require provider
credentials or execute a live generation request.

## Documentation and publication policy

For documentation or publication-policy changes, run these Python utilities. The
docs scope runs `check_docs.py`, the product gate runs `test_media_rights.py`, and
`test_docs_check.py` imports a game package, so it runs in the games scope
(`uv run --group games python scripts/check.py --scope games`):

```sh
uv run python scripts/check_docs.py
uv run --group games pytest tests/unit/test_media_rights.py tests/contract/test_docs_check.py -q
```

Two of the checker's rules bind prose to the tree. A backticked source path
must exist. And every specification under `docs/spec/` opens with a
`> **Checked by:** ...` line naming the test modules that read it, or `none.`
when nothing does; a named test must exist and must itself name the spec, so a
document cannot claim a checker it never had, and `none.` is an honest fact a
reader can act on rather than a pointer that rotted.

## System tools and packaged resources

`ffmpeg` and `ffprobe` must be on `PATH` for audio inspection (probing, level and
duration measurement). Component tests inject process runners where possible, but a
real music pipeline should fail clearly when those tools are unavailable.

The core wheel includes immutable layout templates under `fx_games.resources`.
Game-only music and its provenance belong to the optional game tooling distribution. The contract test builds a
wheel in isolation, inspects its entries, extracts it away from the checkout,
and resolves every required resource through the installed helper API. Do not
restore checkout-relative resource lookup or symlink fixtures into a build.
