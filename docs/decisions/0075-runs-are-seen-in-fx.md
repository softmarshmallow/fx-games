# 0075 — Runs are seen in FX

*Ruled 2026-10-11 by the owner. It retires the viewer that
[0071](0071-workflows-are-the-product-unit-and-the-web-splits-into-site-and-viewer.md) split out of
the web; the site is unchanged.*

## Fact

Grida FX 0.2 ships its own viewer: `python -m grida.fx start` serves a project's plans and
runs, each drawn on a canvas with its steps' files, live while a run is in flight. Stage Gen still
kept the one 0071 and [0074](0074-stage-gen-runs-on-grida-fx.md) left it: the Next app in
`web/viewer` (55 files, 6,639 lines), its launcher (`stage_gen.viewer`, `scripts/view.py`), the
view contexts and view cache in `stage_gen.runview`, three generic view templates, three workflow
view templates, and the run-view, view-context and artifact-preview contracts in `web/ui`.

On 2026-10-11 both viewers were opened on this checkout's `out/runs`. Both listed the same eight
runs, the provider smoke runs of 2026-10-07, and drew the same graph for each. Neither listed a
run of the five workflows: the folders from 2026-10-03 are not FX runs, and both readers skip
them. What only Stage Gen's viewer showed was record detail (the view kind, the graph digest,
the projection's gaps), a card per workflow with its plan and commands, which the site and the
command line already give, and three workflow views: a parallax scroll, a universe gallery and
a sprite loop.

## Challenge

**Keep the three workflow views.** They show what a generic card does not: the parallax layers
scrolling together, the loop playing. But each template reads `stage-gen-view-context-v1`, a
document only Stage Gen's viewer wrote, so keeping them keeps the viewer. FX records a step's
`view:` for views it may render later and renders none today. What the views showed is still
there: looping-parallax delivers its `preview.png`, movie-sprite its loop, and universe's
pictures are files of the run; the site's players play the parallax and sprite examples.

## Ruling

Stage Gen keeps no run viewer. Runs are seen in FX's viewer, which
`uv run python -m grida.fx start --open` opens.

- Deleted: `web/viewer`, `stage_gen.viewer`, `scripts/view.py`, `stage_gen.runview`'s view
  contexts, view cache and file facts with their templates, the run view's archetype (its
  schema version is now 4), the three workflow view templates, the `web/ui` run-view,
  view-context and artifact-preview contracts, the viewer's settings in `.env.example` and
  `docs/viewer.md`. The five workflow files declare no `view:`.
- `scripts/view.py` is a retired command line: the documented-commands test refuses it.
- `stage_gen.runview` stays as the projection the examples store reads (`project_run`). FX's
  public run documents (`load_run`, `fx-viewer-run-v1`) do not carry the per-step provider,
  model, attempts and cost an example shows.
- `web/` is the site alone: `web/site` is the one Bun package, and the players and contracts
  `web/ui` held live in its `lib/`. The docs gate's no-spawn rule now covers every web source,
  not only the viewer's shell.

## Evidence

About 11,550 lines go, 6,639 of them the Next app and 1,324 the launcher and the view half of
`stage_gen.runview`. The product gate (`uv run python scripts/check.py`) and the web and docs
scopes pass without them.

## Falsifier

A workflow whose result cannot be judged from its files on FX's canvas, where FX gives no way to
show it. The answer then is a view in FX, not a second viewer here. If FX's public run document
grows the per-step facts an example shows, `stage_gen.runview` goes too.
