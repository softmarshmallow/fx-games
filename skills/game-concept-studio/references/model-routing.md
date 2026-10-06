# Image routes, sizes and cost

Grida FX serves concept images through its built-in route table. Routes and prices change with FX
releases: `grida-fx nodes image.generate` lists the current routes, and `grida-fx doctor` says
which of them the user's keys can serve. Re-check both after updating FX.

## What FX serves

- **`image.generate`:** a picture from a `prompt`, with an optional `size` and `background`
  (`auto`, `opaque` or `transparent`). It also takes `references`, but no built-in route accepts
  them.
- **`image.edit`:** a picture from input pictures: `image` first, then up to 15 `references`, so at
  most 16 in all. It also takes a prompt, a size, a background, and an optional `mask`: a PNG the
  size of `image` whose fully transparent pixels mark where the picture may change. A mask is a
  strong hint, not a guarantee.
- **Every answer** must be a PNG of exactly the requested size. FX checks that, and checks that an
  opaque answer has no transparent pixels and a transparent one has an alpha channel. An answer
  that fails is a failed attempt, still billed, and FX may try again within the limit below.

## Built-in routes

All three serve the same model. Each sends one image per call at the model's highest quality,
sends the prompt verbatim (`authored_prompt_passthrough`), and gets one PNG back.

| Route | Key | Notes |
|---|---|---|
| `openai/gpt-image-2.5-sunburst@openrouter` | `OPENROUTER_API_KEY` | opaque or auto only; no mask; `auto` or the seven sizes below; with the user's own provider key on OpenRouter, the upstream cost counts too |
| `gpt-image-2.5-sunburst@openai` | `OPENAI_API_KEY` | transparency; mask; any size in the envelope |
| `openai/gpt-image-2.5/sunburst@fal` | `FAL_KEY` | transparency; mask; any size in the envelope; prompt at most 32,000 characters |

- Choose by the key the user holds. A cover is opaque, so any route serves it. Transparency or a
  mask needs the OpenAI or fal route.
- Set the route in `fx.yaml` under `routes:`, or on one step with `route:`. Change it only with the
  user, and record the change in `concept.md`.
- A step's `requires:` names the features it needs. The plan refuses a route that lacks one,
  offline, before anything is spent.

### Prices

Prices are planning allowances in US dollars per call, not quotes, in tiers by exact size. A low is
the image output, measured or derived from a measured bill; a high leaves room for a long prompt
and, on an edit, 16 input pictures. What a call costs is settled from what the provider reports,
else at the high of its size's row below. OpenAI reports no cost, so FX books each OpenAI call at
that high. OpenRouter reports a cost, but has billed twice the measured output, so its highs cover
twice the output.

| Size | Low | OpenAI, fal high: generate / edit | OpenRouter high: generate / edit |
|---|---|---|---|
| `2064x1008` | 0.13 | 0.21 / 0.35 | 0.34 / 0.48 |
| `2496x1152`, `1152x2496` | 0.14 | 0.22 / 0.36 | 0.37 / 0.51 |
| `1024x1024` | 0.21 | 0.29 / 0.43 | 0.50 / 0.64 |
| `2560x1440` | 0.22 | 0.30 / 0.44 | 0.52 / 0.66 |
| `2560x1712`, `1712x2560` | 0.28 | 0.36 / 0.50 | 0.65 / 0.79 |
| any other size, `auto`, or none | 0.09 (OpenRouter 0.13) | 0.70 / 0.85 | 0.70 / 0.85 |

The OpenAI and fal routes also have tiers for sizes in the envelope below:

| Size | Low | High: generate / edit |
|---|---|---|
| `2880x960` | 0.10 | 0.18 / 0.32 |
| `1024x1536`, `1536x1024` | 0.16 | 0.24 / 0.38 |
| `1152x1024` | 0.19 | 0.27 / 0.41 |
| `1536x1536` | 0.30 | 0.38 / 0.52 |
| `2464x3328` | 0.52 | 0.60 / 0.74 |

## Sizes

Every route serves these:

| Size | Shape |
|---|---|
| `2560x1440` | 16:9 landscape |
| `2064x1008` | about 2:1 landscape |
| `2560x1712` | about 3:2 landscape |
| `2496x1152` | wide landscape |
| `1024x1024` | square |
| `1712x2560` | about 2:3 portrait |
| `1152x2496` | tall portrait |

The OpenAI and fal routes also serve any size in this envelope:

- both edges are multiples of 16;
- the long edge is at most 3840;
- the aspect ratio is at most 3:1;
- 655,360 to 8,294,400 pixels.

To use such a size, add it to the workflow's `size` enum, and keep a route that serves it.

## Drawing from the user's pictures

A picture the user supplies needs `image.edit`, and each one needs a rights basis: the user's own
work, or a licence that allows it. Plan first, and leave `references` out of the inputs file when
there are none.

```yaml
# workflows/concept-image-from.yaml
fx: workflow/v1
id: concept-image-from
title: One concept image from references
description: Draw one exploratory concept image from a written prompt and the user's own reference pictures.

inputs:
  prompt:
    type: string
    min_length: 1
    description: "The whole image prompt, sent to the model verbatim"
  image:
    type: file
    kind: image
    description: "The first reference picture"
  references:
    type: list
    optional: true
    max_items: 15
    items: { type: file, kind: image }
    description: "More reference pictures, after image"
  size:
    type: string
    default: "2560x1440"
    enum: ["2560x1440", "2064x1008", "2560x1712", "1024x1024", "1712x2560", "1152x2496", "2496x1152"]
    description: "An exact size every built-in image route serves"

steps:
  draw:
    uses: fx/image.edit@1
    requires: [image_input, exact_size, opaque_background, authored_prompt_passthrough]
    with:
      prompt: ${{ inputs.prompt }}
      image: ${{ inputs.image }}
      references: ${{ inputs.references }}
      size: ${{ inputs.size }}
      background: opaque

outputs:
  image: ${{ steps.draw.outputs.image }}
```

```yaml
# inputs/candidate-03.yaml: picture paths are relative to this file
size: "2560x1712"
image: refs/harbor-sketch.png
references: [refs/palette-study.png]
prompt: |
  <the whole prompt; say what to take from each picture, in order>
```

## Cost and the ceiling

- `grida-fx plan` prints the estimate and never spends.
- A live run needs `--live` and a ceiling: `--max-usd`, else the workflow's `budget:`, else
  `fx.yaml`'s.
- Every attempt holds its worst case against the ceiling before it is sent, so a tight ceiling can
  refuse a retry. A call refused before it is sent costs nothing.

## Retries, the cache and takes

- FX is the only retry owner. A call gets at most 6 attempts, each held against the ceiling and
  recorded. Never retry a run yourself.
- FX keeps every answer in `.fx/cache` and replays an identical request for free, so while the
  takes file is unchanged, running a candidate again never redraws it.
- A semantic miss, a valid image that is wrong for the concept, is a new candidate with a changed
  prompt.
- A change of prompt, size, route or reference picture is a new candidate.
- Provider moderation still applies.

### Redraw an unchanged prompt

To draw the same prompt again, as a new candidate:

1. Copy its inputs file: `cp inputs/candidate-01.yaml inputs/candidate-02.yaml`.
2. `grida-fx reroll runs/candidate-01 draw`. It writes "`draw` uses take 2" into
   `workflows/concept-image.takes.yaml`. Reroll from the newest run of that prompt.
3. Plan and run `candidate-02` as usual, into `runs/candidate-02`, once the user authorizes it.

The takes file is keyed by step (`draw`), not by candidate, so every later run of the workflow uses
that take. For a new prompt this changes nothing: it is a fresh draw either way. FX refuses to run
into a run folder made before the change, so make a new one. Don't use `grida-fx pick` in a
concept folder: it pins one result to `draw`, and every other candidate's run would then fail.
Select by copying instead.

After a reroll, every earlier candidate would draw anew at the new take, and be billed for it. To
get an earlier candidate's image back, copy it from `runs/<candidate>/outputs/image.png`; never
run it again.
