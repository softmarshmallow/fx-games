# 0073 — Concept Studio is a skill, not an application

*Ruled 2026-10-06 by the owner. It overturns M8f of
[0072](0072-gnode-is-one-engine-behind-text-contracts.md), which kept Concept Studio as it was.*

## Fact

0072 dropped its milestone M8f: concept studio stayed as it was, because it never ran a graph.
What stayed was an optional distribution, `stage-gen-concept`, under `apps/concept_studio/`:
1,388 lines of source and 957 lines of tests around one image call. They wrapped that call in
Stage Gen's configuration and image routing, the allowlisted `.env` loader, a JPEG-to-PNG
normalization and `.meta.json` provenance sidecars, with a workspace dependency group, a gate
scope and a CI matrix entry of their own. The skill told an agent to install that distribution and
to draft inside this checkout's `concept-studio/workspaces/`, so nobody without the checkout could
use it.

Grida FX ([gridaco/fx](https://github.com/gridaco/fx), pinned at `third_party/fx`) now serves
`image.generate` and `image.edit` as built-in steps: a free plan with a price, `--live` behind a
dollar ceiling, one retry owner with at most six attempts, a content-addressed cache, and a run
folder that records the inputs, route, cost, digests and attempts and that
`grida-fx inspect --verify` re-checks.

## Challenge

**Keep `stage-gen-concept` as a thin FX wrapper.** Its `init`, `image`, `select` and `check` are
familiar, and a wrapper could hide FX's files. But it would still need this repository installed,
still be a distribution with a gate scope, and still stand a second command in front of the FX run
record, which is what a cover's provenance now is. `init`, `select` and `check` are three short
procedures (make a folder, copy bytes, compare bytes) that an agent can follow from prose in any
folder.

**Keep the Grok route.** It was the inexpensive exploration route. FX serves no Grok route, and
that model can answer in JPEG, which every FX image route refuses: an answer must be a PNG of the
exact size asked for. Carrying it would mean an adapter FX does not have.

## Ruling

- `apps/concept_studio/` and `tests/unit/concept_studio/` are deleted, with the `apps` dependency
  group, the workspace member, the `apps` gate scope, its CI matrix entry and the
  `stage-gen-concept models` step of the aggregate gate.
- Concept work is the skill [game-concept-studio](../../skills/game-concept-studio/SKILL.md),
  which users install (`npx skills add softmarshmallow/stage-gen --skill game-concept-studio`).
  It stands alone in any folder: it names no path in this repository and no Stage Gen command.
  `init`, `select` and `check` become written procedures in the user's concept folder. Every
  image comes from a one-step Grida FX workflow the skill writes there, run with `--live` and a
  ceiling on the user's own key. The FX run folder replaces the provenance sidecar.
- `skills/` holds skills for users. `.agents/skills/`, and `.claude/skills`, a symlink to it, hold
  only skills for working on this repository. `movie-poster`, already standalone, moves to
  `skills/` too.
- `concept-studio/` keeps the committed gallery, the style dictionary and its ignored
  `workspaces/` for local drafts. The gallery's cover stays published under
  `game_concept_cover_v1`. That lineage does not read an FX run record, so a cover the skill makes
  needs a new lineage contract before it can be promoted.
- The Grok route is not carried. The skill covers FX's built-in GPT Image 2.5 Sunburst routes on
  OpenRouter, OpenAI and fal.
- `scripts/check_docs.py` link-checks `skills/` and refuses a skill line that names a repository
  path, a Stage Gen package or command, or gnode.

## Evidence

- Deleted: 1,427 lines under `apps/concept_studio/`, 1,388 of them source, and 957 lines of tests.
- The skill's two workflow files, exactly as its Markdown prints them, validate against FX's
  `fx-project-v1` and `fx-workflow-v1` schemas and plan on each of the three built-in image
  routes: $0.14–0.30 a call on OpenRouter, $0.18–0.25 on OpenAI, $0.16–0.50 on fal.
- `grida-fx expand` shows a block-scalar prompt reaching the step verbatim, a line that starts
  with `./` included, and an input that holds `${{ … }}` is not rendered as a template.
- No live call was made: the change cost nothing.

## Falsifier

- A user cannot go from an empty folder to a checked concept, the skill's §6, without a path into
  this repository or a Stage Gen command.
- The FX run record lacks something a publication of the cover needs, which writing the lineage
  contract for it would show.
