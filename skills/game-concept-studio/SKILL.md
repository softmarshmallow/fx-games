---
name: game-concept-studio
description: Develop an early game idea through conversation into a concise concept document and exploratory cover art drawn with Grida FX on the user's own provider key. Use for pre-production concept work in any folder before anyone builds the game; do not write game configuration, runtime assets, implementation plans or playable code.
---

# Game Concept Studio

The outcome is a game concept a person can read and look at before paying to build anything: one
`concept.md` and one cover image. It is not an input to any generator, and it promises nothing
about an implementation.

## 1. Make the concept folder

- Ask for a folder, or choose one: by default `./<concept-id>/` in the user's working directory,
  where `<concept-id>` is lowercase hyphen-case (`lantern-ferry`). One concept per folder; every
  candidate image lives in it.
- Never draft inside a game's source, build, asset or publication folders.
- Create:
  - `concept.md`, from the starter below;
  - the folders `images/` and `inputs/`;
  - `fx.yaml` and `workflows/concept-image.yaml`, verbatim from §4;
  - `.gitignore`, with the two lines `.env` and `.fx/`.
- Read [references/concept-folder.md](references/concept-folder.md): the layout, the parts of
  `concept.md`, and what each file records.

```markdown
# <Title>

> Status: exploratory game concept only; not a game package or implementation plan.

<One-sentence pitch.>
```

## 2. Shape the idea

- Grow the user's brief in conversation, not with a questionnaire.
- Write useful assumptions into `concept.md` as assumptions. Focus on the player fantasy and the
  visual identity, and leave consequential choices as open questions.
- Never write game configuration, maps, manifests, schemas, implementation plans, source code,
  production asset trees, or engine and runtime decisions. Mechanics may be discussed in prose,
  never encoded.

## 3. Direct the art

- Read [references/style-library.md](references/style-library.md) before writing any image
  prompt. It is vocabulary and evidence, not an allowlist: combine or depart from it in concrete,
  observable terms.
- Decide these separately: rendering style, subject, camera and composition, production role, and
  content presentation.
- No game, franchise, character, artist or studio name ever reaches the model. Turn a name the
  user gives into the visible traits they mean by it.
- Ask for original, brand-neutral imagery: no protected characters, logos, signatures, watermarks
  or pseudo-branding. Anyone depicted is unambiguously adult.
- Don't impose sprite, sheet, transparency or camera conventions on concept art.

## 4. Draw candidates with Grida FX

[Grida FX](https://github.com/gridaco/fx) plans each image call offline with a price, runs it only
with `--live` under a dollar ceiling, owns the retries, and keeps a record of every run.

**Get FX.** It runs on macOS, and on Linux with glibc 2.28 or later; on Windows, use WSL 2.

- `npm install -g @grida/fx` gives the `grida-fx` command.
- Or `pip install grida`; then `python -m grida.fx` takes the same arguments.

**Keys.** The user sets `OPENROUTER_API_KEY`, `OPENAI_API_KEY` or `FAL_KEY` themselves, in the
environment or in the concept folder's `.env`. Never open, print, write or copy a `.env`.
`grida-fx doctor`, run from the concept folder, says which keys are present and which routes a
live run could serve, never the values.

**Project files.** Write both verbatim. Keep the route pair whose key the user holds
([references/model-routing.md](references/model-routing.md) compares them).

```yaml
# fx.yaml
fx: project/v1
budget:
  max_usd: 1                  # one run's ceiling; --max-usd overrides it
routes:                       # one model on three providers: keep the pair whose key you hold
  image.generate: openai/gpt-image-2.5-sunburst@openrouter    # OPENROUTER_API_KEY
  image.edit: openai/gpt-image-2.5-sunburst@openrouter
  # image.generate: gpt-image-2.5-sunburst@openai             # OPENAI_API_KEY
  # image.edit: gpt-image-2.5-sunburst@openai
  # image.generate: openai/gpt-image-2.5/sunburst@fal         # FAL_KEY
  # image.edit: openai/gpt-image-2.5/sunburst@fal
```

```yaml
# workflows/concept-image.yaml
fx: workflow/v1
id: concept-image
title: One concept image
description: Draw one exploratory concept image from a written prompt, at an exact size.

inputs:
  prompt:
    type: string
    min_length: 1
    description: "The whole image prompt, sent to the model verbatim"
  size:
    type: string
    default: "2560x1440"
    enum: ["2560x1440", "2064x1008", "2560x1712", "1024x1024", "1712x2560", "1152x2496", "2496x1152"]
    description: "An exact size every built-in image route serves"

steps:
  draw:
    uses: fx/image.generate@1
    requires: [text_to_image, exact_size, opaque_background, authored_prompt_passthrough]
    with:
      prompt: ${{ inputs.prompt }}
      size: ${{ inputs.size }}
      background: opaque

outputs:
  image: ${{ steps.draw.outputs.image }}
```

**One candidate is one inputs file.** Write the prompt as a block scalar (`|`). FX sends an input
value as written, never rendering it as a template, and a value that holds a newline is never
mistaken for a `./path`.

```yaml
# inputs/candidate-01.yaml
size: "2560x1440"
prompt: |
  <the whole prompt, built with references/style-library.md>
```

**Commands**, from the concept folder:

1. Plan, which is free, and show the user the estimate:
   `grida-fx plan workflows/concept-image.yaml --inputs inputs/candidate-01.yaml --max-usd 1`
2. Only after the user explicitly authorizes this candidate count and ceiling, run:

   ```bash
   grida-fx run workflows/concept-image.yaml --inputs inputs/candidate-01.yaml \
     --live --max-usd 1 --run runs/candidate-01 --deliver image=images/candidate-01.png
   ```

3. Verify the record: `grida-fx inspect runs/candidate-01 --verify`

**Rules:**

- Read [references/model-routing.md](references/model-routing.md) before choosing a route or a
  size. Record the route (`model@provider`) and a one-line reason in `concept.md`.
- Live calls are billable. Authorizing one concept or one candidate count does not authorize more
  variants.
- Each candidate is one generation: its own inputs file, its own run folder, one image.
- FX is the only retry owner, with at most 6 attempts, each held against the ceiling. Never wrap a
  run in a retry loop of your own.
- A valid but disappointing image calls for a new candidate with a changed prompt, never a retry.
- Never switch routes silently.
- FX replays an identical request from its cache for free, so while the takes file is unchanged,
  running an unchanged prompt again never redraws it. To redraw one, follow "Redraw an unchanged prompt" in
  [references/model-routing.md](references/model-routing.md).

## 5. Review and select

- Open and look at every candidate yourself. Check it against `concept.md` for:
  - subject, player fantasy and world cues;
  - composition and style;
  - stray text, letters or marks;
  - visible protected material.
- Keep rejected candidates and their run folders. Give each candidate a line in `concept.md`'s
  Images list.
- Select by byte copy, with no transform: `cp images/candidate-NN.png images/cover.png`.
- Fill `concept.md`'s Cover section: the candidate, its run folder, the route, the size, the
  SHA-256 of `images/cover.png` (`shasum -a 256` on macOS, `sha256sum` on Linux), and why it was
  chosen.

## 6. Check

All must hold:

1. `concept.md` has a title and pitch, visual direction, an Images list, a Cover section, and
   assumptions or open questions. It holds no game configuration.
2. `cmp images/cover.png runs/<selected>/outputs/image.png` succeeds.
3. `grida-fx inspect runs/<selected> --verify` exits 0 and reports the run ok.
4. No key, `.env` value, absolute path or private path appears in `concept.md` or the inputs
   files.
5. Nothing outside the concept folder changed. Installing FX, with the user's agreement, is setup
   and not part of this check.

## 7. Hand off

- Return the folder's path, `concept.md` and `images/cover.png`.
- The FX run folder is the cover's record: its inputs, route, cost, digests and attempts. Never
  hand-write a provenance file beside it.
- Label the result exploratory and unapproved.
- Publishing the cover, or using it as an input anywhere, is the user's explicit decision, held to
  the destination's own review.
- Don't claim that anything imports the concept or builds a game from it.
