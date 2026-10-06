# Image style anchor

The style anchor fixes the *rendering medium* of generated images so it cannot
drift between calls. A free-text instruction like "make it anime" is re-read by
the model on every request, and long runs slide toward semi-realistic output.
The anchor replaces that instruction with a tracked, versioned clause.

## What it does

An edge LLM may return exactly one field — the chosen `style_mode`. It cannot
write prose, invent a medium keyword, name an artist, or reference a brand.
Local code expands that single token into the clause appended to the prompt:

```text
A weary cartographer resting at a roadside shrine at dusk.

Canonical style anchor — medium: clean 2D Japanese anime illustration.
Observable traits: crisp inked linework; flat cel-shaded color regions;
  discrete hard-edged shadow shapes; restrained gradients.
Asset treatment: visual novel character sprite with a readable silhouette
  and expression.
Exclude: photorealistic rendering; semi-realistic rendering; live-action
  imagery; 3D rendering; painterly realism; skin-pore detail; subsurface
  scattering; photographic depth of field; lens bokeh.
```

Everything after the author's first line comes from
`stage_gen/resources/prompting/image_style_vocabulary_v1.json`, not from the
model. Only the `Asset treatment` line varies across the eight asset kinds;
medium, traits, and exclusions stay byte-identical across a whole run.

## Vocabulary

Four modes ship in v1: `cel_shaded_anime_2d`, `photorealistic_natural`,
`gouache_illustration_2d`, and `flat_graphic_2d`. Each defines one medium
keyword, four observable traits, per-asset treatments for the eight
`ImageAssetKind` values, and an exclusion list. The selection skill is
`stage_gen/resources/skills/anchor-image-style/SKILL.md`.

Adding a mode is additive for validation — a persisted anchor naming an older
mode still validates — but it rewrites `vocabulary_sha256` and the vocabulary
the selection is asked with, so the next build asks (and pays) for its
selection again, and every image whose clause text changes is drawn again.
Modes are therefore added when art direction demands one, not for convenience.

## Where it is used

The Grain's room and scene builds
([`pipeline/workflow.py`](../godot/games/the_grain/pipeline/workflow.py)) pick
one style for the whole room or scene, in three steps:

1. a `structured.generate` step asks the selection question
   (`stage_gen.image_prompting.image_style_question`): the skill and the
   vocabulary as the system prompt, the asset kinds and the creative brief as
   the prompt;
2. a judge refuses a selection that names no approved mode or lacks a
   treatment for an asset kind the build draws, and the selection is asked
   again;
3. a step materializes the accepted mode into the canonical anchor
   (`style-anchor.json`) and the clause each asset kind's prompts end with.

No other workflow or game uses the anchor today.

## Binding

The Grain's build appends each kind's clause once, after the authored prompt.
`append_style_anchor_once` is the library form of that rule: it appends the
clause idempotently and refuses a prompt that already carries a different
anchor. The clause is part of every image request, so it is part of every image
call's key. The anchor carries `vocabulary_sha256`, and the dialogue-scene
bundle records `style_anchor_sha256`, so two images can be proven to share a
style contract, and editing the vocabulary correctly invalidates cached work.
