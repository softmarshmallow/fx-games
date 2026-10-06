# Provider operations

Grida FX makes every provider call Stage Gen's workflows and games make. FX owns the adapters,
the built-in route table, where keys are read, retries, billing, long jobs and downloads. They
are specified in FX's [providers spec](https://github.com/gridaco/fx/blob/main/spec/providers.md)
and [capabilities spec](https://github.com/gridaco/fx/blob/main/spec/capabilities.md); the
copy this repository runs is the one pinned at `third_party/fx`. This page keeps what Stage Gen
decides: which route each workflow and game picks and why, what this repository has measured
about those routes, and what happens to their output afterwards.

FX's adapters have not yet made a live call from this repository; one budgeted smoke run per
provider is still to come. The live evidence below was gathered through the predecessor
adapters on the same provider surfaces, and each finding is dated. Hosted capabilities drift:
re-check a provider's current contract before widening a route, and repeat a scoped live check
after.

Image-route capabilities and their verification histories are kept in the
[GPT Image 2.5](gpt-image-2.5.md) and [GPT Image 2](gpt-image-2.md) model records. All model
records are indexed in [Models](index.md). GPT Image 2.5 Sunburst is the image model every
route uses; GPT Image 2 is kept only as historical evidence.

## Keys and tools

```dotenv
OPENAI_API_KEY=
OPENROUTER_API_KEY=
FAL_KEY=
ELEVENLABS_API_KEY=
TRIPO_API_KEY=
```

These five keys, and the four base URLs [`.env.example`](../../.env.example) lists, are the only
names FX reads: from the environment, else from the `.env` file of the project a command runs
from. The file is optional and local. `GRIDA_FX_DISABLE_DOTENV=1` turns it off, which the
credential-free gates do. Without `--live` no key is used and nothing is sent; a missing key
refuses only the calls that need it, before anything is sent and for nothing.

Credentials are server-side only. Do not expose them to `web/`, persist them in provenance,
print them, or commit a populated env file. FX never prints a key's value:
`uv run python -m grida.fx doctor <workflow>` says which keys are present and where each came
from, and which routes, tools and node types the workflow needs. A base URL must be HTTPS unless it names a
loopback host, and one that holds a key's value is refused (FX providers §3).

A step that runs a local program declares it as a tool; `GRIDA_FX_TOOL_<NAME>` points at a
particular binary, else the tool is found on `PATH`. Character-3d declares Blender
(`GRIDA_FX_TOOL_BLENDER`), and Ember Hollow's opening clips an ffmpeg built with libtheora
(`GRIDA_FX_TOOL_FFMPEG_THEORA`).

## The routes Stage Gen picks

Routes and their prices come from FX's built-in table, then the tables a project's `fx.yaml`
lists under `route_tables`. Each Stage Gen project names, under `routes:` in its `fx.yaml`, the
one route each capability uses:

| Project | Routes | Why |
| --- | --- | --- |
| [looping-parallax](../../src/stage_gen/workflows/looping_parallax/fx.yaml) | `image.edit`: `gpt-image-2.5-sunburst@openai` | The seam repaint requires `mask` and `alpha`. |
| [portrait-motion](../../src/stage_gen/workflows/portrait_motion/fx.yaml) | `structured.generate`: `openai/gpt-6-astra@openrouter`; `image.edit`: `gpt-image-2.5-sunburst@openai` | The face locator and the judges need a vision model that sees each picture as it is; the new states are drawn at the portrait's own exact size, which OpenRouter's fixed sizes do not serve. |
| [universe](../../src/stage_gen/workflows/universe/fx.yaml) | `structured.generate`: `openai/gpt-5.6-sol@openrouter`; `image.generate`: `openai/gpt-image-2.5-sunburst@openrouter` | Concept images are opaque, at canvases verified live on that route. |
| [movie-sprite](../../src/stage_gen/workflows/movie_sprite/fx.yaml) | `video.generate`: `google/gemini-omni-flash/v1.1/image-to-video@fal` | The take needs `first_last_frame`. |
| [character-3d](../../src/stage_gen/workflows/character_3d/fx.yaml) | `agent.turn`: `openai/gpt-6-astra@openrouter`; `image.generate` and `image.edit`: `openai/gpt-image-2.5-sunburst@openrouter`; `mesh.generate`: `P2-20260801@tripo`; `mesh.rig`: `v1.0-20240301@tripo` | Agents design, review and lay out parts; reference views are opaque; Tripo builds and rigs the meshes. |
| [Bellweather](../../godot/games/bellweather/fx.yaml), [The Grain](../../godot/games/the_grain/fx.yaml) | `image.generate` and `image.edit`: `gpt-image-2.5-sunburst@openai`; `structured.generate`: `openai/gpt-5.6-sol@openrouter`; `music.generate`: `google/lyria-3-pro-preview@openrouter` | Cut-out art needs native alpha, and Bellweather's seam repaints need a mask. |
| [Ember Hollow](../../godot/games/ember_hollow/fx.yaml) | as Bellweather, plus `agent.turn`: `openai/gpt-5.6-sol@openrouter`, `sound.generate`: `eleven_text_to_sound_v2@elevenlabs` and `video.generate`: `google/gemini-omni-flash/v1.1/image-to-video@fal` | The prop-anchor agent, sound effects and the opening clips. |
| [Iron Petal Unit](../../godot/games/iron_petal_unit/fx.yaml) | as Bellweather, plus `agent.turn`: `openai/gpt-5.6-sol@openrouter`, `sound.generate`: `eleven_text_to_sound_v2@elevenlabs` and `speech.generate`: `eleven_v3@elevenlabs` | The cut-in placement agent, sound effects and spoken lines. |
| [Afterlight voice preparation](../../godot/games/afterlight/fx.yaml) | `speech.generate`: `eleven_v3@elevenlabs`, priced per thousand characters by its own route table | One spoken line per call. |

The rules that make a route choice safe:
- **A step names the features it needs** in `requires:` (`alpha`, `mask`, `image_input`,
  `first_last_frame`, `exact_duration`, and so on), and a route without one is refused while
  planning, before any spend.
- **No route is a fallback for another.** A project names one route per capability. Changing it
  is an edit to its `fx.yaml`, or a `routes:` entry in the `fx.yaml` a command runs from; keys
  and failures never switch a route. The repository's root `fx.yaml` names no routes, so a
  workflow planned there by id keeps its home's.
- **Prices are planning allowances**, FX's built-in table's unless a project's route table
  restates them. What a call costs is settled from what the provider reports, else the whole
  amount held for it.

`uv run python -m grida.fx nodes` lists every built-in node type, `nodes <type>` one type's
ports, settings and the routes that serve it, and `uv run python -m grida.fx doctor <workflow>`
names the keys, tools and routes one workflow needs. All are offline and read only local files.

The move onto FX carried no cache. Runs made through the predecessor engine stay under `out/`,
but their paid calls are not reused: a game's next build draws its art again.

## GPT Image 2.5 Sunburst

Every image route is the Sunburst variant at `quality: max`. Flare, the bare `gpt-image-2.5`
name and dated aliases are not routes. OpenAI is used only through its Images endpoints; the
Responses image tool is not a route, because it rewrites prompts and changes the response.

| Route | Background | Size | Inputs |
| --- | --- | --- | --- |
| `gpt-image-2.5-sunburst@openai` | `auto`, `opaque` or `transparent` (`alpha`) | any exact size in the envelope below, or flexible | up to 16 pictures; a mask (`mask`) |
| `openai/gpt-image-2.5/sunburst@fal` | `auto`, `opaque` or `transparent` (`alpha`) | as OpenAI | up to 16 pictures; a mask (`mask`) |
| `openai/gpt-image-2.5-sunburst@openrouter` | `auto` or `opaque` | seven verified exact sizes, or flexible | `image.edit` only: up to 16 pictures, no mask |

The OpenAI and fal envelope is FX's: edges multiples of 16, the longer edge at most 3,840 pixels,
an aspect ratio at most 3:1, and 655,360 to 8,294,400 pixels. A workflow's target geometry is
its own: it asks for one valid provider size, inspects the answer, then normalizes it with
premultiplied-alpha, aspect-preserving resampling to its exact sheet or layer dimensions.

**OpenAI.** Native alpha at maximum quality is the default for every cut-out. Transparency is
proved from decoded bytes, never from a PNG container or an RGBA mode: FX refuses a transparent
answer without an alpha channel, and each game's gates check that the exterior is clear.
Measured transparent output tops out at alpha 254, never 255, so the gates that judge an opaque
body accept 254. An edit sends no `input_fidelity`: a live run on 2026-09-09 returned HTTP 400
`invalid_input_fidelity_model` for it on every reference-conditioned request, and the same edit
succeeded without it. FX paces each OpenAI and OpenRouter image route at 150 requests a minute,
which matched this repository's OpenAI project; a project whose account allows another rate
restates the route in a route table.

**fal.** The same model and envelope as OpenAI, with separate text-to-image and edit endpoints.
No Stage Gen project picks it today. A paid masked edit on 2026-09-09 landed the editable band
and kept native alpha, but also changed material pixels outside the mask: a mask is a strong
hint, not a protected region, so a workflow that needs untouched pixels restores them itself.

**OpenRouter.** Opaque and `auto` only. A paid transparent request returned HTTP 400, and FX
refuses one before sending. The seven exact sizes are the canvases verified live in September
2026: `1024x1024`, `1152x2496`, `1712x2560`, `2064x1008`, `2496x1152`, `2560x1440` and
`2560x1712`. Reference-conditioned maximum-quality calls cost USD 0.138393 to 0.294423 across
them. Every request turns OpenRouter's upstream fallbacks off.

The route-by-route live verdicts, including the shared seam-repaint admission failure of
2026-09-10, are in the [GPT Image 2.5 record](gpt-image-2.5.md).

## Structured output and agents through OpenRouter

`openai/gpt-5.6-sol@openrouter` is the default model for structured output and agent turns. It
was exercised live for structured output on 2026-08-20. OpenRouter lists image input and
structured outputs for it; keep a live check before relying on a new use.

`openai/gpt-6-astra@openrouter` is the vision judge portrait motion names, and the agent model
of character-3d. Its route contract, which FX ships, carries its request settings (high
reasoning effort, high image detail, OpenAI as the only upstream, fallbacks off) and, for
structured output, shows every picture exactly as its file is. The default model instead fits
each picture into 1600 by 1600 pixels, flattened onto the step's matte. Both settings are part
of the route's fingerprint, so a call's cache key changes with them. Its worst case is USD 1.50 a
call or a turn; the portrait runs' structured calls cost USD 0.07 to 0.39.

An agent step runs FX's agent loop: each turn is one `agent.turn` call, with the transcript, the
step's tools and, for a structured answer, a required tool choice. Tools are sent strict, and
OpenRouter is told to require every parameter, so an upstream that cannot honour them is not
used rather than silently degraded. Pictures a tool returns follow the tool results as one user
message. Each turn is call-cached by its transcript, so a resumed agent replays the turns it
already paid for. The cut-in placement agent
([Iron Petal Unit's screen effects](../../godot/games/iron_petal_unit/docs/fx.md)) is bounded
at six turns a portrait.

## Music through OpenRouter

- Model slug: `google/lyria-3-pro-preview`.
- Canonical version observed in metadata: `google/lyria-3-pro-preview-20260330`.
- Input modalities: text and image.
- Output modalities: text and audio.

OpenRouter advertises `max_tokens`, `temperature`, `top_p`, `seed`, and `response_format`. It
does not advertise a duration parameter or supported voices. Express musical structure and
requested duration in the prompt. Do not send a speech/TTS voice. FX's adapter sends the prompt
alone, reads the streamed or buffered answer, and refuses anything but MP3 (FX providers §9.2).
OpenRouter's generic audio guide is speech-oriented and does not guarantee Lyria's envelope, and
provider documentation disagrees on a fixed sample rate, so nothing is assumed about the audio
beyond the bytes: a game's soundtrack steps judge each draw as a playable MP3, then measure it
and refuse one too short to loop.

Provider documentation indicates that Lyria output is expected to carry SynthID. This
repository has not independently verified that watermark on the preview loop. The expectation
is provenance metadata only: it does not prove ownership, originality, clearance, or permission
to redistribute an artifact. Repository publication still requires the independent
[generated-media approval gate](../generated-media-publication.md).

A draw outside any build is a one-step workflow over `fx/music.generate@1`, beside an `fx.yaml`
whose `routes:` names `music.generate`, with `takes:` to hear several. A game's own soundtrack
steps draw, admit and pick takes the same way.

Primary sources:

- [OpenRouter model page](https://openrouter.ai/google/lyria-3-pro-preview)
- [OpenRouter audio output](https://openrouter.ai/docs/guides/overview/multimodal/audio)
- [Provider-native music guide](https://ai.google.dev/gemini-api/docs/music-generation?hl=en)

## Video through fal

The one video route is `google/gemini-omni-flash/v1.1/image-to-video@fal`, which the
[movie sprite workflow](../../src/stage_gen/workflows/movie_sprite/page.mdx) and Ember Hollow's
opening use. Its
[official API schema](https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video/api)
was checked on 2026-09-15: `prompt` (at most 20,000 characters), `image_url`, optional
`end_image_url`, integer `duration` from 3 through 10, `resolution` in `360p`, `720p`, `1080p`
or `4k`, and `aspect_ratio` in `9:16` or `16:9`. Movie sprite passes the same prepared picture as
the first and the last frame.

Two lessons came from the reference form of the same model
(`google/gemini-omni-flash/v1.1/reference-to-video`, which no route serves today):

| Fact | How it was learned |
| --- | --- |
| At most 10 seconds | `duration: 18` answered HTTP 422 naming `le: 10`, free, before rendering. |
| Whole seconds only | 4.5 seconds was truncated to 4 by the predecessor adapter, the route answered four seconds correctly, and the caller's length gate refused the answer against the 4.5 nobody had asked for: six attempts at full price. |

FX's adapter refuses a duration that is not a whole number from 3 to 10 before sending, rather
than rounding one.

The [published rates](https://fal.ai/models/google/gemini-omni-flash/v1.1/image-to-video)
checked on 2026-09-15 are USD 0.03, 0.10, 0.15 and 0.30 per generated second at 360p, 720p,
1080p and 4k, with no minimum and no rounding: a longer clip always costs more. The route is
priced per second by resolution, and its worst case carries 25 percent more; FX holds that worst
case before each attempt and charges it whole when fal reports no cost. Local playback slowing
does not change what generation costs.

A take is a long job on fal's queue. FX records the job before submitting and once fal takes it,
so an interrupted run collects the clip instead of submitting again. A submission whose answer
never arrived stops for a person (`uv run python -m grida.fx jobs`); the key is sent only to
fal's hosts, never to the hosted download.

A 2026-09-15 live canary returned 360 by 640, 72 frames at 24 fps over three seconds, in one
attempt. The response reported no actual cost; its estimate was USD 0.09 and the held liability
USD 0.1125. It carried audio despite the silent prompt, which local sprite finishing removes.
This proves endpoint wiring and structural validation, not compliance with every artistic
motion instruction.

The answer is h264 in mp4. The pinned Godot host plays only Ogg Theora, so a clip is transcoded
before publication; see [the shell spec](../../godot/games/ember_hollow/docs/shell.md) for that
leg and the encoder it needs. The endpoint documentation does not establish training-data
license provenance; technical suitability is not a legal assurance.

### Audition this route before you plan a run on it

Video is among the most expensive routes this repository uses (a ten-second 720p clip is USD
1.00, about four to six maximum-quality images) and, like every other seedless route here, it answers
the same brief differently every time. A take kept only in the call cache is drawn anew, and
differently, whenever that cache goes cold.

So draw takes, look at the frames, and keep the winner as a file. A one-step workflow in a
folder of its own (under the ignored `out/`, say) is enough, beside an `fx.yaml` that names the
video route:

```yaml
# fx.yaml
fx: project/v1
routes:
  video.generate: google/gemini-omni-flash/v1.1/image-to-video@fal
```

```yaml
# clip-audition.yaml
fx: workflow/v1
id: clip-audition
title: Clip audition
steps:
  film:
    uses: fx/video.generate@1
    with:
      prompt: the brief, verbatim
      first_frame: ./references/style-plate.png
      duration: 10
      resolution: 720p
      aspect_ratio: "16:9"
    takes: 4
    view: true
outputs:
  clip: ${{ steps.film.outputs.video }}
```

From that folder, `uv run python -m grida.fx plan clip-audition.yaml` prices the four takes at
USD 4.00 to 5.00, and

```sh
uv run python -m grida.fx run clip-audition.yaml --live --max-usd 5
```

draws them into its `runs/` folder. From the repository root,
`uv run python scripts/view.py out/<audition>/runs` shows each take. Back in the folder,
`uv run python -m grida.fx pick runs/<run> film 3` makes the third take the one the workflow
outputs, and `uv run python -m grida.fx run clip-audition.yaml --deliver clip=the_cold.mp4`
copies it out from the cache without drawing anything again. A game that films a shot in its own build gates and reviews each take there
instead; see [the shell spec](../../godot/games/ember_hollow/docs/shell.md) for Ember Hollow's,
and for its `take` contract, which names the kept file instead of the brief. Adopting a kept
file costs nothing and is not held to the route's ten-second limit, because nothing is asked
of the route. Drawing in the run stays fully supported for any shot that does not declare a
take.

## Sound and speech through ElevenLabs

`eleven_text_to_sound_v2@elevenlabs` makes sound effects, with the `exact_duration` feature,
which Iron Petal Unit's generated clips require; the request surface was verified against the
published reference on 2026-09-02. A runner package whose effects are all oscillators needs
nothing from this provider. The measured model boundary is
[model-eleven-text-to-sound-v2.md](../spec/model-eleven-text-to-sound-v2.md); the authoring
contract that consumes it is [Iron Petal Unit's audio](../../godot/games/iron_petal_unit/docs/audio.md).

`eleven_v3@elevenlabs` speaks lines, with the `audio_tags` and `stability` features, verified
against the account's model listing on 2026-09-03 (`requires_alpha_access` false;
`can_use_style` and `can_use_speaker_boost` false, so only `stability` is sent). The voice is
the provider's own voice id, cast in the game's `voices.toml` and never authored beside
gameplay; Iron Petal Unit's build refuses a voice cast on a provider other than its speech
route's. A seed is never sent: measured, it pins the length of a read and not its waveform. The
measured model boundary is [model-eleven-v3.md](../spec/model-eleven-v3.md); the authoring
contract is [Iron Petal Unit's voices](../../godot/games/iron_petal_unit/docs/voices.md).

ElevenLabs reports characters, not dollars, so FX charges each call the whole amount held for
it. Afterlight's route table prices the speech route per thousand characters: the published USD
0.10, held at twice that.

## 3D through Tripo

Character-3d names two Tripo routes, both long jobs:
- `mesh.generate` on `P2-20260801@tripo`: a multiview task from a part's front and back, and
  its left and right when given; USD 1.20 to 2.50 a mesh.
- `mesh.rig` on `v1.0-20240301@tripo`: USD 0.25 to 0.50 a rig. Tripo's free riggability check
  runs first; a doubted model is refused unless the step allows it, and the check's answer is
  recorded either way.

A task is posted once, polled, and after a crash collected instead of posted again; an answer the
post cannot confirm is never posted twice. Models are downloaded only from Tripo's own hosts.
Tripo reports credits, which FX converts at USD 0.01 a credit (FX providers §9.4).

## Background removal

FX has a `background.remove` adapter on fal (`fal-ai/birefnet/v2`, General Use (Light), at a
1024 by 1024 operating resolution), but its built-in table has no route for it until fal's
price is recorded, and no Stage Gen project declares one. So nothing removes a background
today: an `ai` transparency strategy, which would generate on a neutral field and remove it, is
refused while planning, and `chroma` keys an exact `#FF00FF` field locally (see the
[prompt contract](../spec/agent-prompts.md)). A removal would never silently replace failed
native generation.

## Game builds

The games build with Grida FX from their own folders, and planning is provider-free:

```sh
(cd godot/games/bellweather && uv run python -m grida.fx plan pipeline/workflow.py:build --arg package=inputs/default)
```

Each game's `fx.yaml` names its routes. A painting that needs alpha requires `alpha` and a seam
repaint requires `mask`, so a route that cannot serve one is refused while planning. OpenRouter
serves the structured reviews, rebase readings and music.

## Retries and billing

FX's engine is the one retry owner for every paid call: at most six sends of one request, a
request sent again only when it provably was not received or the provider's failure allows a new
attempt, and a deterministic refusal ending the call. Every attempt is held against the run's
ceiling and settled from the provider's reported cost, else charged whole (FX protocol §6.1;
providers §4–6). Stage Gen adds no retry loop around a call. A judge that refuses an answer and
draws again (`on_reject: regenerate`) makes a new, billed take; that is a semantic regeneration,
never a provider retry.

A migration tool once re-seeded an accepted run's provider bytes after its validators tightened,
because a tightening inside a paid step could only be expressed as "redraw everything". It was
retired in the engineering pass: acceptance lives in the free judges downstream of a paid step,
a paid step's identity moves only when its request does, and `uv run python -m grida.fx plan`
says what a run would bill before it runs. What the tool preserved, historical bytes under a
current request identity, is what the call cache does by construction when the request has not
changed.
