# Game Concept Studio

Game Concept Studio is the inexpensive pre-production side of Stage Gen. Start with a short game
idea, talk it through with an agent, and leave with a readable concept plus cover art before
deciding whether to build anything.

A concept is never an asset-pipeline input: a concept folder never contains game configuration,
maps, manifests, runtime assets, or implementation code.

This directory keeps the tracked [2D game style dictionary](style-dictionary/README.md) and the
publication-only [gallery](gallery/README.md). Local drafts live under the ignored `workspaces/`.

## Make a concept

Concept work is the installable agent skill
[game-concept-studio](../skills/game-concept-studio/SKILL.md). It runs in any folder and draws its
images with [Grida FX](https://github.com/gridaco/fx) on the user's own provider key, under a
`--max-usd` ceiling, after the user explicitly authorizes each live run.

Install it globally:

```sh
npx skills add softmarshmallow/stage-gen --skill game-concept-studio -g
```

Inside this checkout, a project install would land in the repository's own `.agents/skills`
(`.claude/skills` is a symlink to it), so install with `-g`, or point an agent at the skill's
`SKILL.md`. Then ask for it with a short game description, for example:

```text
Use game-concept-studio to imagine a 2D adventure about a rooftop courier in a flooded city.
```

In this checkout, put a concept folder at `workspaces/<concept_id>/`. The whole tree is ignored, so
its `fx.yaml`, `workflows/`, `inputs/`, `runs/`, `.fx/` and any `.env` stay out of git. The stable
handoff is:

```text
workspaces/<concept_id>/concept.md
workspaces/<concept_id>/images/cover.png
```

The FX run folder of the selected candidate is the cover's record.

## Style dictionary

[`style-dictionary/README.md`](style-dictionary/README.md) is the canonical tracked guide to
illustration vocabulary, reviewed model-pair prompts, exact verdicts, and concept-to-asset research.
The skill carries its neutral visual facets with it. Durable concept handoffs must not depend on
ignored `out/` artifacts or send its game-anchor names across the provider boundary.

## Gallery

`gallery/` contains only explicitly promoted, independently reviewed, provenance-complete concept
packages. A successful local image is not automatically gallery-ready.

The existing cover was published under the `game_concept_cover_v1` lineage of
[generated-media publication](../docs/generated-media-publication.md). A cover the skill makes
carries an FX run record, which that lineage does not read yet, so promoting one needs a new
lineage contract first.
