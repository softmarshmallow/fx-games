# 0074 — Stage Gen runs on Grida FX

*Ruled 2026-10-06 by the owner; landed 2026-10-07 in `f499c35d`. It supersedes the parts of
[0072](0072-gnode-is-one-engine-behind-text-contracts.md) that name the engine and keep it in
this repository: R9, R9b and its six `gnode-*` documents.*

## Fact

0072 built gnode inside this repository: `src/gnode` and `src/gnode_std`, about 23,000 lines,
one `gnode` command and three plugins (`std`, `stage_gen` and the viewer). Every workflow and
every game build planned and ran on it.

gnode then became Grida FX ([gridaco/fx](https://github.com/gridaco/fx)), a standalone public
product: a Rust engine, a Python SDK imported as `grida.fx`, its own specification, guide,
conformance suite and gates, and no brand. Its first milestone made it run from a clone, and
Stage Gen took it as a submodule at `third_party/fx` (`43fc6cfc`). Nothing here used it yet.

Leaving out gnode's own tests, Stage Gen imported 159 names from gnode, and `grida.fx` had 17
of them: 142 names, imported in 116 files, had no FX equivalent. They were plain utilities (contract models, atomic writes, media checks,
provenance sidecars), about 60 names of provider services and retries, a route-policy layer
that re-checked a route a table had already chosen, the run view and its dashboard, the
injected services and recorded-call doubles the tests ran workflows on, and the catalog's
planning internals. FX's overview planned to replay gnode's paid cache into FX.

## Challenge

**Replay the cache.** Copying each paid result under its FX key would keep it at $0. But
gnode's call records keep no request, so a replay needed gnode running beside FX, and gnode
could go only after it. What a replay could keep was small: about $20–30 of game image calls,
101 of them Bellweather's, which a rebuild bills again and draws as new art anyway. The
largest block, $108 of character-3d spike calls, begins with agent turns whose keys change
shape, so it could not move at all.

**Keep a compatibility package.** A `gnode` shim over FX would let code move a little at a
time. It would also keep two identities and two command lines, which
[0072](0072-gnode-is-one-engine-behind-text-contracts.md)'s R13 rules out.

**Keep the run view in FX.** The viewer draws a run, so the projection could live with the run
record. But the view contract, the viewer and its catalog are Stage Gen's, and FX must make
sense without Stage Gen; FX reserves `views/` in a run folder and draws no views yet.

**Wait for a published wheel.** It would need no Rust toolchain here. But FX is not published
until trusted publishing exists, and Stage Gen changed FX in the same milestone. A submodule
pins exactly the commit the gates ran, and `push.recurseSubmodules=check` keeps an unpushed FX
commit from being pinned.

## Ruling

- Stage Gen consumes Grida FX as a submodule at `third_party/fx`, with `grida` as an editable
  path dependency. It runs FX as `uv run python -m grida.fx`, never a bare `grida-fx`, and
  imports only `grida.fx`'s public names (`tests/contract/test_import_boundaries.py`). Every
  gate builds the engine from the submodule first (`third_party/fx/tools/build_engine.py`), and
  the pre-push hook builds the FX commit each pushed commit pins.
- gnode is deleted in the same step, with no compatibility path: `src/gnode`, `src/gnode_std`,
  the `gnode` command and its plugins, the gnode schemas, `docs/spec/gnode-rings.md`,
  `tests/conformance` (FX keeps its own suite), `tests/live`, and the route-policy layer with
  its model policy snapshot and `STAGE_GEN_*_MODEL` overrides. FX's built-in route table and
  each project's `routes:` choose a route, and the planner refuses one that lacks a feature a
  step `requires:`.
- **No cache replay** (the owner, 2026-10-06). FX starts with an empty cache. gnode's runs stay
  in `out/`, and the viewer does not list them.
- Project files are `fx.yaml` and `fx.lock`. The root `fx.yaml` finds the first-party workflows
  by id (`workflows: [src/stage_gen/workflows]`), and every project keeps its runs in
  `out/runs` and its store in `out/fx-cache`. Built-ins are `fx/<type>@1`, features are FX's
  (`alpha`, `image_input`, `mask`), takes files are `<workflow id>.takes.yaml`, and
  `GRIDA_FX_TOOL_<NAME>` picks a tool's binary.
- FX gained what Stage Gen needed, each part of FX's own contract: stand-in answers
  (`grida.fx.run(..., stand_in=...)`, `--stand-in`), the `workflows:` search folders and
  `RunResult.failures`. Tests run whole workflows and game builds on stand-ins in place of
  injected services.
- The run view moves into Stage Gen: `stage_gen.runview` projects an FX run folder to
  `stage-gen-run-view-v1` and keeps views in the user cache, and `scripts/view.py` replaces
  `gnode view`.
- Concept Studio is already a skill that draws through FX
  ([0073](0073-concept-studio-is-a-skill-not-an-application.md)).
- 0072's rulings on the engine's behaviour (identity, calls, takes, judges, phases,
  expressions, ceilings, retries) are FX's to keep now, in its specification. Its views (R11)
  are Stage Gen's run view until FX draws views, and its R12–R14 stay Stage Gen's.

**What follows.** Prices do not move: every workflow and game plans on FX at exactly gnode's
prices. Identities and cache keys are new, and every paid result is drawn again when it is
next needed. The guide that lived in `docs/guide` is FX's guide now, in gridaco/fx. Building
anything here needs cargo.

## Evidence

- Deleted: `src/gnode` (22,319 lines), `src/gnode_std` (740), `docs/guide` (2,730),
  `tests/conformance` (3,105), `tests/live` (531) and the route-policy and orchestration
  modules (about 4,800). The switch removed 51,935 lines and added 7,449, about 1,500 of them
  `stage_gen.runview`.
- Every workflow plans on FX by id, and every game builder from its own folder, at gnode's
  prices; only digests moved. The workflow identity golden was re-pinned on FX.
- The tests run every workflow and game build whole on stand-ins, offline.
- No live call was made: the change cost nothing. The first live runs on FX are one budgeted
  smoke run per provider, each with the owner's go and a cap.

## Falsifier

- A Stage Gen need that FX can meet only by learning a Stage Gen name: a workflow, a game, a
  brand or the viewer's contract.
- A test that can be written only against an injected service, not a stand-in.
- A rebuild of a game or workflow that costs well past the estimate above because a result
  could not move.
