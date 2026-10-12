# Concept Studio guardrails

This subtree is an agent-facing pre-production project. Its only authored deliverables are text and
images that help a person decide what game they want before full generation.

- Use the game-concept-studio skill ([`SKILL.md`](../skills/game-concept-studio/SKILL.md)) for
  concept requests.
- Keep drafts under `workspaces/<concept_id>/`; this directory is gitignored. The skill's FX
  project files (`fx.yaml`, `workflows/`, `inputs/`, `runs/`, `.fx/`) stay inside that draft.
- Do not create or modify `game.toml`, maps, runtime manifests, FX Games workflows, source code,
  fixtures, library packages, web files, or engine assets as part of concept work.
- Draw images only through the skill's Grida FX workflow (`grida-fx`, or `python -m grida.fx`). A
  live run needs explicit user intent and a `--max-usd` ceiling. Never read, print, copy or write
  any `.env`.
- Keep provider prompts original and brand-neutral. Research game names never cross the provider
  boundary.
- `style-dictionary/` is the canonical tracked vocabulary, reviewed-prompt, and research reference.
  Its Markdown consumes individual previews directly; do not add a grid, contact sheet, or document
  render. Keep prompts brand-neutral and keep its manifest, shared exact-image review, and rights
  notice synchronized with the tracked preview set.
- `gallery/` is a publication surface. Promotion requires explicit authorization plus provenance,
  independent review, rights, inventory, and storage gates. An FX run record is not yet a
  publication lineage: the gate covers only the existing `the-sky-remembers` cover.
- Keep repository identifiers, logs, prompts intended for persistence, and authored files in
  English.
