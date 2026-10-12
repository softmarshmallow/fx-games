# 0076 — Stage Gen is FX Games

*Ruled 2026-10-12 by the owner. It renames the repository and its product; no boundary
moves.*

## Fact

Since [0074](0074-stage-gen-runs-on-grida-fx.md) and [0075](0075-runs-are-seen-in-fx.md), Grida
FX owns the engine, the store, the run record and the viewer. What this repository keeps is
game-asset workflows written on FX, the examples they made, the site that shows them and the
Godot example project that consumes them. The name Stage Gen still described the pipeline
generator 0074 moved out.

## Ruling

The repository, its product and its packages are named FX Games:

- the repository `softmarshmallow/fx-games`, the distribution `fx-games` and the package
  `fx_games` (`src/fx_games/`), which every workflow's and game's `fx.yaml` lists in `sources:`;
- the contract kinds `fx-games-workflow-v1`, `fx-games-catalog-v1` and `fx-games-run-view-v1`,
  with no alias for the old kinds;
- the site at `softmarshmallow.github.io/fx-games`, and `@fx-games/site`;
- the Godot-owned authoring distribution `scenario-authoring`, after its import name, so it
  carries no product name.

Each `fx.lock` is re-pinned with `--same`: only the import lines in each node's closure
changed, and no node type's version moves. Grida FX is unchanged, and so is the direction of
every dependency.

Strings written into runs, caches, digests or committed media keep the old name, as the
[glossary](../glossary.md#frozen-persisted-strings) lists: the `@stage-gen/<name>` provenance
names, the `stage-gen` tool identity, the `stage-gen-headless` source of media sidecars,
The Grain's `stage-gen/dialogue-scene/...` digest domains and the bytes of committed game
inputs, comments included, which their package digests pin. Decisions, plans, research and the
Godot history keep the words of their time, and the retired `stage-gen` command line stays
refused.

## Evidence

Offline plans of the four games' builds, The Grain's rooms and scene, universe and
character-3d, made before and after the rename against the same store, give every step the
same identity and state. A first cut renamed a path in a comment of Ember Hollow's
`shell.toml`; that re-keyed its `world` step and broke the package's pinned source digest,
so committed inputs keep their bytes.

## Falsifier

A stored result that an offline plan no longer reuses after the rename, or a consumer that
reads a persisted string this record left unchanged and expects the new name.
