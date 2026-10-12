# Components

A component is an independently testable package under `src/fx_games/components/`: the
contracts, processing, admission and review a capability needs, callable without an engine. It
never runs alone and never imports a workflow. Workflows call components from their node types;
Grida FX plans, runs, caches and inspects those compositions. A component can serve several
node types, and it does not need a game package or a particular runtime.

## Components

| Component | Public surface | Output or responsibility |
|---|---|---|
| Repeating images | `image_repeat.validate_image_repeat`, `image_repeat.build_three_repeat_preview` | Deterministic single-axis seam validation and the three-repeat preview |
| Layered scenery | `sideview_layers.models.LayerRequest`, `sideview_layers.publish` | Repeat construction, the painted layer's gate, trimming and placement |
| Supplied-layer parallax | `sideview_layers.parallax`, `workflows.looping_parallax` | Repeating PNGs, portable composition metadata, and a scrolling preview |
| Fixed portrait motion | `portrait_motion` | Local eye/mouth patches, registration, review, and diagnostic playback |
| Rigged characters | `character_3d` | Profiles, partitions, quality bars, studios and the Blender worker |
| Sound effects | `sound_effect.SoundEffectRequest` | One effect asset or pinned take; gameplay response is separate |
| Speech | `speech.SpeechRequest` | One line and admission budget with a caller-owned voice binding |
| Video inspection | `video_clip` | Caller-specified size, codec, duration, and optional aspect constraints |

The kits only the games use (actors, terrain, UI, effects, screens, music, voices, world
generation, map design, character profiles) live in
[`demo_game_tools.kits`](../../../godot/games/_shared/python/src/demo_game_tools/kits/README.md),
beside the games that own them; the asset product never imports them.

Existing fixed geometry remains useful as named presets. The local eye/mouth portrait pipeline does not claim to represent every Live2D workflow. Authors can compose different components or write their own node types on Grida FX.

Runnable inputs live beside workflows. Start with [`../workflows/looping_parallax/inputs/supplied_layers/`](../workflows/looping_parallax/inputs/supplied_layers/): its small Python input generator draws original geometric layers without a provider and writes an `inputs.yaml` for `uv run python -m grida.fx run looping-parallax --inputs <dir>/inputs.yaml`. Inspecting or scrolling the result requires no game definition.

## Contract

An FX Games component is an independently testable application package under
`src/fx_games/components/`, such as repeat validation, portrait motion or the character-3d
studios. Components call no provider themselves: image, structured, video, mesh, music, sound
and speech generation are calls a node type makes through Grida FX, which owns their
specifications, retries and provider adapters.

Shared, workflow-neutral media inspection and transforms live under
`src/fx_games/media/`; component-specific processing stays with its component,
and workflow-specific canonicalization stays with its workflow. A workflow composes
components into a graph; a runtime or preview consumes its artifacts.

### Required properties

Artifact-producing components must:

1. accept typed or schema-validated input;
2. write only below the caller-provided output directory, or return the bytes for the
   node to store;
3. return what they made explicitly (bytes, a manifest or facts) rather than relying on
   implicit filenames;
4. validate media before reporting success;
5. call no provider and add no retry loop: a node calls a capability through Grida FX,
   whose engine is the one retry owner, with at most six sends of a request;
6. refuse with a reason, rather than repair, an answer that fails a deterministic check,
   so a judge can report it and its step draws again (`on_reject: regenerate`), a new
   take and never a provider retry;
7. return the measurements and digests a reviewer or consumer needs; FX's run record says
   which call made each file;
8. make deterministic post-processing explicit and independently testable;
9. leave nothing that looks finished when stopped part-way: FX keeps a step's outputs
   only when the step ends; and
10. expose enough information for a headless benchmark.

### Structure

The properties above say what a component does; this says what one looks like, so
that a reader who has seen one has seen them all. A component is a package under
`src/fx_games/components/` whose `__init__.py` exports its surface in `__all__`,
holding:

- `models.py` — the authored contract: the pydantic models and the vocabulary they
  close over, with their persisted `kind` and version literals;
- the pure work, each callable without an engine: `processing.py`, `admission.py`,
  `review.py` (prompts, response schemas and their validators), and the like;
- private helpers as `_<name>.py`; the package-level `components/_secure_fs.py` and
  `components/_game_input.py` hold what several packages share, rather than copies.

A component declares no node types. A workflow's node modules
(`src/fx_games/workflows/<id>/nodes/*.py`) declare its FX node types with `@node` from
`grida.fx` and call components from their bodies. The games' shared step families live in
`demo_game_tools.steps`: each module holds a family's node types and an `add_*_steps` helper
that writes the family's steps into a game's builder, over the pure parts of a kit.

A component imports `fx_games.media`, `fx_games.canonical`, other components and, where
it hands an agent a tool (character-3d's studios), `grida.fx`'s public names; never a
workflow, a game or a provider. `tests/contract/test_import_boundaries.py` refuses a
component that imports a workflow, and `tests/contract/test_component_structure.py` one
without an exported surface.

### Independence rule

The reusable contract does not assume a genre, camera, engine, coordinate
system, movement model, combat model, or gameplay loop. Those may be explicit
inputs to a specialized workflow, but they are never ambient global state.

For example, a sprite-sheet component may accept `{ rows, columns, anchors }`.
It must not silently assume that row 2 is a jump animation. A depth-layer
component may accept a requested projection and loop axis. It must not assume a
horizontal follow camera because one preview happens to use one.

The provider-neutral recovery, crop, and packing boundary is specified by the
[sprite-sheet slicing and instance-recovery contract](../../../docs/spec/sprite-sheet-processing.md).
The Python core implements its minimal alpha-component repacker; generic grid detection and
semantic ownership recovery remain planned. The contract does not reserve workflow or consumer
behavior inside reusable components.

Components must not import `web/`. The site consumes exported manifests and examples; it
never reaches into a component.

## Failure contract

Failures distinguish provider/transport errors, response-contract failures,
input validation errors, and deterministic post-processing failures. Error
messages may name environment variables but must never include credential
values or full authorization headers.

Partial outputs may remain for debugging only when clearly marked incomplete.
They must not satisfy skip-if-exists or cache checks.
