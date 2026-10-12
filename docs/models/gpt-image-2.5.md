# GPT Image 2.5 provider contract

> **Checked by:** none.

OpenAI released GPT Image 2.5 on 2026-09-08 as two distinct models:
`gpt-image-2.5-sunburst` and `gpt-image-2.5-flare`. There is no documented bare
`gpt-image-2.5` model ID. External provider research and historical live probes
are date-scoped below; repository integration status is current through
2026-09-10. This record keeps provider documentation, live artifact evidence,
and repository integration status separate. Grida FX's route table and each
project's `fx.yaml` remain the runtime authority.

## Provider history through 2026-09-09

| Provider | External route | Generation and editing | Transparent background | Evidence through 2026-09-09 |
| --- | --- | --- | --- | --- |
| OpenAI | `gpt-image-2.5-sunburst` | Both; explicit repository generation and edit routes | Documented for generation and edit | A live generation returned HTTP 200 through the then-current pre-refactor repository adapter; generation/edit and mask contracts are covered offline |
| OpenAI | `gpt-image-2.5-flare` | Both documented; not registered | Documented | Earlier live request was refused by the account gate; no later Flare canary |
| fal | `openai/gpt-image-2.5/sunburst/text-to-image` and `openai/gpt-image-2.5/sunburst/edit` | Separate explicit repository routes | Advertised by both schemas | High-quality text-to-image decoded with native alpha; a maximum-quality transparent masked edit also passed live, with outside-mask drift |
| fal | `openai/gpt-image-2.5/flare/text-to-image` and `openai/gpt-image-2.5/flare/edit` | Separate active routes; not registered | Advertised by both schemas | High-quality text-to-image output decoded with native alpha |
| OpenRouter | `openai/gpt-image-2.5-sunburst` | Generation plus up to 16 references; repository route has no native-alpha claim | `auto` or `opaque` only | `max` square and reference-conditioned wide generations passed live; transparent request returned HTTP 400 |
| OpenRouter | `openai/gpt-image-2.5-flare` | Listed, not selected | `auto` or `opaque` only | Catalog only; no repository canary |

## Live adapter verdict, 2026-09-10

On 2026-09-10, after provider-free checks passed for the then-new OpenAI Images
and fal adapters (the predecessors of FX's), the bounded live invocation
`sunburst-routing-20260910` dispatched the same ordered primary cases to each
provider, stopping that provider after its first deterministic admission
failure:

| Case | OpenAI Images | fal |
| --- | --- | --- |
| Transparent generation, 1536 by 1024 | Deterministic validation and independent semantic review passed | Deterministic validation and independent semantic review passed |
| Wayfarer idle edit | Deterministic validation passed; independent semantic review failed | Deterministic validation and independent semantic review passed |
| Sunpetal seam repaint edit | HTTP 200; deterministic admission failed, so OpenAI stopped | HTTP 200; deterministic admission failed, so fal stopped |
| Remaining terrain paint-over, ladder edit, and UI-panel edit cases | Not dispatched under the provider-stop policy | Not dispatched under the provider-stop policy |

No reruns were dispatched. The results validate native transparent
output and basic edit-route selection on both providers, but the shared
seam-repaint admission blocker means they do not establish full recipe
readiness.

Neither provider reported a complete actual dollar cost. All six attempts have
`cost_complete=false`, so the observed cost must not be described as zero. The
harness conservatively reserved $12 across the six attempts and ended with $34
of accounted exposure, including $22 of fixed, nondispatchable safety headroom.

## Direct OpenAI

Sunburst is OpenAI's most capable variant and is positioned for editing
precision. Flare is the faster variant for everyday generation. Both support:

- `POST /v1/images/generations` and multipart `POST /v1/images/edits`;
- dated snapshots `gpt-image-2.5-sunburst-2026-09-08` and
  `gpt-image-2.5-flare-2026-09-08`;
- the Responses API image-generation tool with the exact image model selected
  in the tool;
- `background`: `auto`, `opaque`, or `transparent`;
- `output_format`: `png`, `jpeg`, or `webp`;
- `quality`: `auto`, `low`, `medium`, `high`, `xhigh`, or `max`;
- `moderation`: `auto` or `low` for generation and edits;
- standard 1024-by-1024, 1536-by-1024, and 1024-by-1536 canvases, plus custom
  dimensions aligned to 16 pixels, within a 1:3 to 3:1 aspect ratio, no edge
  above 3840 pixels, and 655,360 to 8,294,400 total pixels; dimensions above
  2560 by 1440 remain experimental; and
- multiple edit inputs and an optional mask.

Transparent output requires PNG or WebP. A successful GPT Image response carries
base64 image data; the caller must decode and inspect the alpha channel rather
than infer transparency from the container.

An early high-quality transparent PNG request for each exact model returned HTTP
403 at an account verification gate. That was not the final Sunburst result. A
repository-owner check recorded at 2026-09-09 10:58:11 UTC sent
`POST /v1/images/generations` with `gpt-image-2.5-sunburst`, received HTTP 200
and a real image with 196 image-output tokens, and completed `stage-gen
generate-image` through the then-current pre-refactor repository adapter in one
attempt. The cause of the change is unknown: account verification and rollout
propagation were both plausible, while `/v1/models` still omitted or returned
404 for 2.5.
The successful check did not record background mode, canvas, or edit behavior,
so by itself it proves only that the Images generation route was reachable. The
2026-09-10 refactor canary above subsequently supplied direct native-alpha and
basic edit evidence for the OpenAI adapter of the time, subject to its recorded
semantic and deterministic failures.

OpenAI's current pricing table lists the same token rates for both variants:
$5 per million text-input tokens, $1.25 cached; $8 per million image-input
tokens, $2 cached; and $30 per million image-output tokens. Rate limits are
organization-specific.

Image output is most of an image's price, and it is fixed by size. OpenAI's
usage reports for this repository's earlier `quality="max"` Sunburst calls give
the same image-output tokens for every call at one size:

| Size | Image-output tokens | At $30 per million |
| --- | ---: | ---: |
| 2880 by 960 | 3,660 | $0.1098 |
| 1536 by 1024 or 1024 by 1536 | 5,488 | $0.16464 |
| 1152 by 1024 | 6,487 | $0.19461 |
| 1024 by 1024 | 7,024 | $0.21072 |
| 1536 by 1536 | 10,044 | $0.30132 |
| 2464 by 3328 | 17,382 | $0.52146 |

Grida FX's built-in image routes are priced per call in tiers by exact size.
A tier's low is the image output: measured for the sizes in this table and for
the two OpenRouter canaries below, and derived from a measured bill for the five
one-reference canaries after them. Its high leaves room for a long prompt and,
on an edit, 16 input pictures. Any other size, `auto`, or no size takes the
route's whole range. OpenAI reports no cost, so FX books each OpenAI image at
its tier's high, or at the route's whole-range high ($0.70 for a generate,
$0.85 for an edit) when no tier names its size. Each OpenAI high leaves room for one
image output, as measured or derived here; the October bill below leaves open
whether that still covers a call.

Primary sources:

- [OpenAI September 2026 changelog](https://developers.openai.com/api/docs/changelog#september-2026)
- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI Images API reference](https://developers.openai.com/api/reference/resources/images)
- [Sunburst model](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)
- [Flare model](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)
- [OpenAI image-generation pricing](https://developers.openai.com/api/docs/pricing#image-generation)

## fal

fal exposes four active public routes, one generation and one edit route for
each variant. Their public catalog IDs are canonical; the `fal-ai/...` names in
the expanded OpenAPI queue paths are implementation metadata, not route
identities. fal's catalog records for the four routes were created between
2026-09-08 19:38:25 UTC and 19:43:14 UTC.

The text-to-image schemas expose:

| Field | Contract |
| --- | --- |
| `prompt` | required, 1 to 32,000 characters |
| `image_size` | preset or custom dimensions; default `landscape_4_3` |
| `background` | `auto`, `transparent`, or `opaque`; default `auto` |
| `quality` | `auto`, `low`, `medium`, `high`, `xhigh`, or `max`; default `high` |
| `num_images` | 1 through 10; default 1 |
| `output_format` | `jpeg`, `png`, or `webp`; default `png` |
| `output_compression` | 0 through 100 for JPEG or WebP |
| `sync_mode` | boolean; default false |

The edit schemas add required `image_urls` with at most 16 inputs and optional
`mask_url`; their default `image_size` is `auto`. All four schemas advertise
the same background enum. Request PNG or WebP when alpha must be preserved.

Live text-to-image canaries requested `quality="high"`, a square-HD canvas,
`background="transparent"`, and PNG without mentioning transparency in the
prompt. Flare completed at 2026-09-09 05:44 KST; its 1024-by-1024 PNG decoded as
RGBA with alpha values from 0 through 254, 70.59% fully transparent pixels, and
four fully transparent corners. Sunburst completed at 05:58 KST with the same
dimensions, mode, alpha range, and transparent corners; 62.15% of its pixels
were fully transparent. Both responses omitted width and height, so byte-level
decoding remains mandatory. A separate paid Sunburst masked edit on 2026-09-09
returned an exact 1536-by-1024 transparent PNG at `quality="max"`; the intended
editable band landed and native alpha survived. Material pixels also changed
outside the mask, confirming that fal/OpenAI masks are guidance rather than a
protected-region guarantee. An earlier template-conditioned edit canary also
completed, but used obsolete 1600-by-900 geometry and is not evidence for the
current terrain contract.

fal currently publishes the same token rates and size/quality tables for Flare
and Sunburst. At `quality="max"`, both list $0.21072 for 1024 by 1024 and
$0.16464 for 1536 by 1024 or 1024 by 1536 before variable input/context use.
Those maximum-tier output prices match GPT Image 2 at its former highest
quality. Recheck the canonical billing surface before an integration or cost
estimate.

Primary sources:

- [fal Flare text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/flare/text-to-image/api)
- [fal Flare edit API](https://fal.ai/models/openai/gpt-image-2.5/flare/edit/api)
- [fal Sunburst text-to-image API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/text-to-image/api)
- [fal Sunburst edit API](https://fal.ai/models/openai/gpt-image-2.5/sunburst/edit/api)
- [fal live model catalog](https://api.fal.ai/v1/models?q=gpt-image-2.5&limit=50)

## OpenRouter

At 2026-09-09 05:42 KST, neither exact 2.5 model appeared in OpenRouter's
catalog and exact endpoint lookups returned HTTP 404. Both appeared later that
morning: OpenRouter records Flare at 10:12:30 KST and Sunburst at 10:12:48 KST.
This rollout history matters: absence immediately after an upstream release is
not evidence that a slug will remain unavailable.

The current Sunburst endpoint advertises `aspect_ratio`, all six quality
levels through `max`, `background`, `n`, `input_references`, and
`output_compression`, with provider-specific `moderation` passthrough. Its
`background` enum is `auto | opaque`; it does not advertise transparent output
or masked editing. A paid `background="transparent"` request returned HTTP 400
before generation, so FX's adapter refuses that request before sending rather than
silently accepting an opaque artifact.

Two paid Sunburst canaries passed at `quality="max"` on 2026-09-09: a
text-only square request returned an exact 1024-by-1024 RGB PNG, and a request
with one input reference returned an exact 2560-by-1440 RGB PNG. They consumed
7,024 and 7,370 image-output tokens and cost $0.210835 and $0.227414
respectively. Exact `size` is not listed in the endpoint's current capability
descriptor, so these canaries support the repository's bounded current route;
they do not justify projecting arbitrary size support onto other OpenRouter
models. Decode and inspect returned bytes in all cases.

Five additional one-reference canaries covered the remaining exact canvases of
the Universe workflow and of the since-removed Storefront workflow. All returned the requested PNG dimensions:
1152-by-2496 and 2496-by-1152 cost $0.154773 each, 2064-by-1008 cost $0.138393,
and 2560-by-1712 and 1712-by-2560 cost $0.294423 each. No canary image or
credential was persisted.

Those five bills give no token counts. FX's tiers for their sizes take the image
output as the bill less $0.006314, the input of the one-reference 2560-by-1440
canary (its bill less its 7,370 output tokens): about 4,949 tokens at 1152 by
2496 and 2496 by 1152, 4,403 at 2064 by 1008, and 9,604 at 2560 by 1712 and
1712 by 2560. The whole bill bounds each output from above; at that bound every
tier's high still leaves at least $0.06 for a generate's prompt.

On 2026-10-07, Grida FX's OpenRouter smoke run sent a text-only 1024-by-1024
generation at `quality="max"` and was billed $0.42164. That is exactly twice
the September canary's 7,024 image-output tokens at $30 per million
($0.42144), plus a few prompt tokens. OpenRouter's published Sunburst rates
were unchanged that day. One bill does not show whether OpenRouter now counts
the output twice or the model drew twice as much. FX's built-in OpenRouter
highs therefore leave room for twice the measured output. OpenRouter reports a
cost, so its high is only held; a call is settled at what it was billed.

The OpenAI and fal highs leave room for one output only, so they are not known
to be worst cases. OpenAI's usage reports still gave the measured output tokens
for all 313 of this repository's direct calls on 2026-09-29 (34 of them at 1024
by 1024, at 7,024 tokens each), eight days before that bill; they are the newest
calls with recorded usage. The image-output tokens of FX's 2026-10-07 OpenAI
smoke edit (1024 by 1024) are not recorded: FX keeps no usage in an answer, so
only OpenAI's usage report for that day can give them. 7,024 tokens would put
the doubling on OpenRouter. 14,048 would mean the model now draws twice as much:
every OpenAI call would then be booked at its high but cost up to one more
output (a 1024-by-1024 generate about $0.42, booked at $0.29), and the OpenAI
and fal highs would need the same room as OpenRouter's.

Primary sources:

- [OpenRouter image-model catalog](https://openrouter.ai/api/v1/images/models)
- [OpenRouter model catalog](https://openrouter.ai/api/v1/models)
- [Sunburst endpoint lookup](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-sunburst/endpoints)
- [Flare endpoint lookup](https://openrouter.ai/api/v1/images/models/openai/gpt-image-2.5-flare/endpoints)

## Repository boundary

FX Games' image routes are Sunburst only, at `quality: max`. Flare, bare
`gpt-image-2.5`, dated aliases, and arbitrary model overrides are not routes.
OpenAI is used only through the Images API; the Responses image tool is
intentionally not a route because it rewrites prompts and has a different
response and usage identity. It is not a fallback now that the Images route is
reachable.

The routes are Grida FX's built-in ones
([FX providers §10](https://github.com/gridaco/fx/blob/main/spec/providers.md)),
each serving both `image.generate` and `image.edit`:

| Route | Provider endpoints | Background | Exact size | Input pictures |
| --- | --- | --- | --- | --- |
| `gpt-image-2.5-sunburst@openai` | `/v1/images/generations` and `/v1/images/edits` | `auto`, `opaque`, or `transparent` | any size in the envelope below | `image.edit`: up to 16, and a mask |
| `openai/gpt-image-2.5/sunburst@fal` | fal `/text-to-image` and `/edit` | `auto`, `opaque`, or `transparent` | any size in the envelope below | `image.edit`: up to 16, and a mask |
| `openai/gpt-image-2.5-sunburst@openrouter` | OpenRouter `/images` | `auto` or `opaque`; no native-alpha claim | the seven verified sizes below | `image.edit`: up to 16; no mask |

A step names what it actually needs in `requires:` (`alpha`, `mask`,
`image_input`, `custom_exact_size`, and so on) instead of inheriting every
feature of a node type, and a route that lacks one is refused while planning.
Each project's `fx.yaml` names one route per capability: the games, the seam
repaint and portrait motion use OpenAI for native alpha, masks or custom exact
sizes; universe and character-3d use OpenRouter for opaque work at sizes its
route has verified; no project uses fal today. There is no provider switch and
no discovery. Changing a route is an edit to an `fx.yaml`, and neither a missing
key nor a failed call moves a call to another route. [Provider
operations](providers.md) lists each project's routes.

OpenAI Images and fal share one exact-size envelope: each edge must be a
multiple of 16, total area must be 655,360 through 8,294,400 pixels, the longest
edge must not exceed 3,840 pixels, and the aspect ratio must not exceed 3:1.
OpenRouter does not declare `custom_exact_size`; its exact sizes are limited to
the live-verified `1024x1024`, `1152x2496`, `1712x2560`, `2064x1008`,
`2496x1152`, `2560x1440`, and `2560x1712` canvases. All three also admit a
provider-selected flexible size. A size a route does not serve is refused
before anything is sent.

A route's contract (the adapter that serves it and that adapter's behaviour) is
part of its fingerprint, and so of every cache key the route serves; price,
pacing, and credentials are not. Changing which route a project names therefore
changes its image calls' keys, but leaves each workflow's step fan-out and
scheduling with the workflow. A future topology change must update the
[canonical generation pipeline](../../godot/games/bellweather/docs/generation-pipeline.md)
and its executable graph contract in the same implementation change.

What an image call costs is the provider's reported cost, else the whole amount
held for it: the high of its size's tier, or the route's whole-range high ($0.70
for a generate, $0.85 for an edit) when no tier names its size. OpenAI reports token
usage but no cost, so FX charges each OpenAI image attempt its whole hold;
OpenRouter reports a cost.

Keys, the routes each project names, and retries are in
[provider operations](providers.md).
