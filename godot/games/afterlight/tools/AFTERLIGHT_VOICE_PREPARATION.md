# Manual Afterlight voice preparation

Current narrative ownership: the episode is authored in Scenario and its compiled
program supplies the read-only review/voice inventory. This tool owns explicit
recording preparation only; playing, compiling narrative, restoring a checkpoint
or activating content does not request new speech. See the [game guide](../README.md).

[voice.yaml](voice.yaml), with its nodes in [voice_nodes.py](voice_nodes.py), is a local
preparation workflow for the P95/P96 voice pass. Godot never imports it or requests speech
generation. Later wording or casting changes require an explicit manual refresh;
launching, playing, changing language, and inspecting voice status spend nothing.
This is not a new generation package, provider adapter, or background sync service.

Afterlight owns the source: its story and paired text, `voice/voices.json` policy
and separate speech scripts, and `voice/cast.json` provider casting. Its
`voice/export_inventory.gd` exports the resolved inputs. Each language/line has a
stable `line_id`, actual `speaker_id`, `display_text`, `speech_text`, explicit
`voice_policy`, selected `voice_profile`, and `source_revision`. Alternative
replies retain their actual speakers. Intentional `none` skips generation even
if a clip exists. The protagonist is unvoiced for this pass. Choice-button labels
are excluded by the host exporter.

Its plan-time step, `voiced_lines`, preserves the host's revision and adds a
digest of immutable source and generation fields. Status, path, and missing-asset
diagnostics do not enter that digest. A different display, speech script, language,
speaker, provider, model, selected voice, setting, or source revision gets a different
preparation identity. Existing recordings remain unchanged. Host status distinguishes current
authored freshness; a saved export only describes the source at its export time.

## Commands

Run from the repository root. Export the current authored source:

```sh
Godot --headless --path godot/games/afterlight --script res://voice/export_inventory.gd -- --output /tmp/afterlight-voice-inventory.json
```

The game's folder is an FX project: `fx.yaml` finds `afterlight-voice` in `tools/`, binds
`speech.generate` to `eleven_v3@elevenlabs`, and prices it from
[voice-routes.yaml](voice-routes.yaml); `fx.lock` pins the node types. Inspect preparation
and cost offline, without credentials or network access:

```sh
(cd godot/games/afterlight && uv run python -m grida.fx plan afterlight-voice --inventory /tmp/afterlight-voice-inventory.json --prepared voice/manifest.json --installed 'voice/clips/*/*.mp3')
```

Paid dispatch is a separate explicit action. It needs `ELEVENLABS_API_KEY`, read by
FX's key loader, and requires `--live` with a ceiling:

```sh
(cd godot/games/afterlight && uv run python -m grida.fx run afterlight-voice --inventory /tmp/afterlight-voice-inventory.json --prepared voice/manifest.json --installed 'voice/clips/*/*.mp3' --live --max-usd 10 --deliver 'files={key}')
```

The run's record lands in `out/runs/afterlight-voice/` and its answers in the store,
`out/fx-cache/`. `--deliver 'files={key}'` copies each new clip to its game path,
`voice/clips/<language>/<line_id>-<revision>.mp3`, and writes the candidate manifest to
`art/voiceovers-p95/manifest.json`; nothing is written when the run fails. The candidate
manifest's `res://` paths name the delivered clips, so it can be tried locally before it
replaces `voice/manifest.json`.

## Budget and attempts

[voice-routes.yaml](voice-routes.yaml) restates FX's built-in ElevenLabs v3 speech
route with its price per character sent: $0.10 per 1,000 characters, the published
rate, reserved at $0.20, at most 5,000 characters a call. The plan prices the worst
case, every take of every line, and the workflow's budget, like the documented
ceiling, is $10. These are rate conversions, not an assertion of a separate invoice
charge when the account consumes included subscription credits.

FX's engine is the only retry owner. It sends a call at most six times, with capped
backoff, and reserves, records and settles each attempt against the ceiling. A request
that provably never reached the provider is sent again under the same attempt. Any other failure, including a timeout or reset after the
request left, is settled as billed and becomes a new attempt, so a line whose outcome
was uncertain is sent again rather than blocking the pass. ElevenLabs reports no
cost FX reads, so every answered attempt is settled at its full reservation, and the
`character-cost` credits header is not recorded. Independently of attempts, the
`admit` judge refuses a read that is not a playable, unclipped MP3 and asks for
another, at most three takes, then the line fails and nothing is laid out. No
artistic retakes, auditions, voice creation or post-processing are part of this
workflow.

An interrupted run is resumed by running the same command again: finished steps come
from the store, and calls already answered are replayed from it without another
provider call.

## Artifact admission and reuse

The speech route is sent the verbatim text, the selected voice, language and v3
stability, and answers in `mp3_44100_192`, the one output format the inventory may
name. The judge decodes each read and
checks its level; `layout` decodes it again for its duration and hash. There are no
`.meta.json` sidecars: the run's record is the provenance of every clip (its request,
route, attempts and settled cost), and `uv run python -m grida.fx inspect` summarises a
run from its folder.

`--prepared` is checked against `--installed` (the installed clips): a ready record at
the line's revisions is kept only when its clip sits at the record's path, hashes to
its `audio_sha256` and decodes again as a playable, unclipped read. A missing clip (a
fresh clone, where the manifest is tracked and the clips are not) is spoken again. A
clip that is present but disagrees fails the plan, naming the line for
reconciliation; it is never spoken again automatically. `--prepared` without
`--installed` is refused.

Ready manifest records contain the host source revision, preparation revision,
audio hash, game path, decoded duration, actual speaker, and provider profile. They
record `listening_verdict: not_reviewed`: decoding and level checks do not establish
acting quality, pronunciation, character fit, user approval, or publication rights.
Generated media rights stay unreviewed.

## The P95 pass

P95 was made with this workflow's predecessor, a Python command with its own quote,
journal and ledger. It produced 80 recordings in 81 returned attempts, including one
technical retry: 7,174 submitted characters, a $0.7174 published-rate estimate, and
3,946 reported subscription credits. The final conservative budget accounting is
$1.4348, also not an invoice. Account subscription counters independently confirm
3,946 credits consumed within existing quota. The initial ledger that incorrectly
treated credit units as text units is preserved as `ledger.initial-accounting.json`;
the corrected ledger retains its original receipt values and initial estimate for
audit. These are distinct measures. There were 36 intentional localized skips and no
final generation failures. A listening verdict was not performed. Its records stay
under the ignored `art/voiceovers-p95/`; see the [generation report](../voice/GENERATION_REPORT.md).

The focused provider-free check runs the workflow with an FX stand-in in place of the
provider:

```sh
uv run pytest -q godot/games/afterlight/tests/python/test_afterlight_voice_preparation.py
```

The local ignore rules explicitly allow this focused Python test source to be
tracked alongside the Godot QA scripts; generated pass output remains ignored.
