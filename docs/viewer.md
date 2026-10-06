# The viewer

The viewer is the local web client for Grida FX runs: `uv run python scripts/view.py` starts
it. It lists every run under the folders you give it, grouped by the workflow that made it,
draws each run's execution graph and artifacts, and shows each workflow's offline plan and the
commands that run it. It is read-only: it does not start runs, receives no provider
credentials, and implements no gameplay.
Playable projects and their asset wiring belong to their Godot owners. The [site](site.md) is a
separate surface: it documents workflows and shows their examples, and it never reads run folders.

## Start it

```sh
uv run python scripts/view.py out/runs
uv run python scripts/view.py out/runs path/to/more-runs --port 3100 --no-open
```

`scripts/view.py [runs]... [--port 3000] [--no-open]` shows the runs under each folder you
name, or the `runs` folder of the nearest `fx.yaml` (`out/runs` here) when you name none. FX
records runs and draws no views; Stage Gen projects each FX run folder to its run view
(`stage_gen.runview`) and starts this viewer
([`stage_gen/viewer.py`](../src/stage_gen/viewer.py)). The viewer is the Next app in
[`web/viewer`](../web/viewer), so it needs a source checkout and Bun: the launcher finds the
checkout by walking up from the installed package, then from the working directory, to the
`pyproject.toml` named `stage-gen` that has `web/viewer` beside it. From an installed wheel,
without Bun on `PATH`, or given a folder that does not exist, `scripts/view.py` exits 2 and
says why. Install the web workspace once with `cd web && bun install --frozen-lockfile`.

Before the server starts:

- a thread starts that writes each FX run's view into the view cache every three seconds when
  the run has changed (below).
- the launcher exports the catalog into `~/.cache/stage-gen/catalog/catalog.json`
  (`$XDG_CACHE_HOME` replaces `~/.cache` when it is an absolute path). The viewer groups runs
  by it and draws plans from it; it never plans anything itself.
- the launcher sets `STAGE_GEN_RUN_ROOTS` (the absolute run folders, joined by the platform's
  path separator), `STAGE_GEN_CATALOG`, `STAGE_GEN_VIEW_CACHE` (`~/.cache/stage-gen/views`) and
  `STAGE_GEN_REPO_ROOT` for the server. Provider keys are removed from the server's environment.

It then runs `bun run --cwd web/viewer dev --port PORT --hostname 127.0.0.1`, opens the browser
once the port answers unless `--no-open` is given. The server leads its own process group; when
`scripts/view.py` ends, by Ctrl-C, SIGTERM, a hangup or the server exiting, it stops that whole
group, so nothing it started outlives it. The server listens on the loopback interface only.

Run without `scripts/view.py` (`cd web/viewer && bun run dev`), the viewer reads `out/` of its
checkout and has neither a catalog nor a view cache: runs are listed ungrouped and only views a
run carries itself are drawn.

## Runs and their views

A run is a folder that holds `execution-view.json`, `manifest.json`, `bundle.json` or
`case.json`; or `plan.json` of kind `fx-graph-v1` beside `events.jsonl` (an FX run). A
`plan.json` and `events.jsonl` of another kind are a foreign run, such as one made before
[decision 0074](decisions/0074-stage-gen-runs-on-grida-fx.md): it is neither listed nor
searched. Runs are found up to four folders below each
root. A run's own folders are not searched again, hidden folders and `node_modules` are
skipped, symlinked folders are not followed out of the root, and the example store at the top
of a root (`out/examples`) is not a run ([`lib/shell/runs.ts`](../web/viewer/lib/shell/runs.ts)).
`scripts/view.py` finds the FX runs whose views it keeps by the same rules
([`stage_gen/runview/refresh.py`](../src/stage_gen/runview/refresh.py)).

The view a run page draws is the run's own `execution-view.json`, or the one kept in the view
cache, whichever is newer. Kept views are written only under
`~/.cache/stage-gen/views/<first 16 hex digits of sha256(real path)>/execution-view.json`;
neither the viewer nor `scripts/view.py` writes into a run folder. `scripts/view.py` writes an
FX run's view when its `plan.json` or `events.jsonl` is newer than its cached one, projected
from those two files, with each step's view context and, when its workflow has a view of its
own, the whole run's. A game's assets build with FX, so its run is an FX run like any other.
Any other run is drawn from the view it carries itself, or its row says none was exported.

The viewer reads any `*-execution-view-v1` envelope at `schema_version = 3`, and Stage Gen's
own `stage-gen-run-view-v1`, which an FX run's view carries. Header fields a producer
adds beside the envelope (`pipeline_id`, `title`, a graph document's `recipe` literal, a game's
ids, a view's `graph_kind`) are kept as the run's subject. Pipeline identities and node
type IDs need no registration. A user-authored pipeline uses the same graph, state, timing, cache,
artifact and provenance surfaces as an installed workflow, and node types without joined display
metadata use the generic node view. A document at another version is refused with a re-derive
message rather than migrated.

## Pages

- `/` lists every run under every root. Each installed workflow leads with its title and promise
  from the catalog and a link to its page; its runs follow, newest first, each with its state,
  node counts and when it last changed. Runs no workflow claims follow under "Game runs" (a run
  folder holding a game's `manifest.json`, `bundle.json` or `case.json`) and "Other runs". An FX
  run belongs to the workflow its plan names, when the catalog lists that workflow with the
  plan's graph kind; a run that carries only a view, to the workflow whose graph kinds include
  the one its view was derived from.
- `/workflows/<id>` shows a workflow's promise and summary, its commands with a copy button, the
  graph it plans offline from its committed sample inputs (drawn as on a run page, with every node
  pending; each lane is a step), its steps, and its runs.
- `/runs/<root>/<tag>` is one run. `<root>` is a root's folder name and a short digest of its real
  path; `<tag>` is the run's root-relative path with `/` written as `~`. A run whose workflow has a
  view of its own (universe's gallery) is shown in that view, with the graph one link away
  (`?view=graph`); any other run with a view fills the window with its graph and node inspector; a
  run with neither says how to get a view. `/runs/<root>/<tag>/artifacts`
  lists the declared outputs.

While a run on a page is live (its trace was written in the last fifteen minutes and it has not
finished), the page refreshes itself every two seconds; the graph keeps its camera and selection.

## Artifact previews

The application selects renderers for image, audio, video, text, and data artifacts. A display
hint the renderer has no view for falls back to an ordinary artifact link. The run view carries
renderer hints as JSON; it does not own a sprite or parallax contract.

The historical `motion` field still describes a uniform strip of 1 through 16 frames. Its
application-owned parser preserves that bound; a different atlas layout needs its own preview
kind. The existing motion player provides frame stepping and sample playback.

Unknown preview kinds retain the ordinary artifact fallback. Model files such as GLB retain their
media type and can be opened or downloaded; there is no dedicated spatial renderer yet.
[`artifact-preview.ts`](../web/ui/contracts/artifact-preview.ts) owns these adapters. Adding a
renderer is an application change, independent of adding a workflow.

## Step views

An FX run's steps can have views of their own. A view is an HTML template and a read-only
context ([`view-context.ts`](../web/ui/contracts/view-context.ts)). A step's `view: <file>`
names a template in its workflow's home, and `view: true` picks a generic image, video or JSON
view by the kind of its output files; a workflow's top-level `view:` names the whole run's
view. FX records neither template: `stage_gen.runview` reads the step's setting from the plan
and the workflow's from its file, found again in the planning project or the installed
workflow of that id. `scripts/view.py` keeps, in the run's view cache folder, each template
under `views/<sha256>.html`, every file a view shows under `views/files/<digest><suffix>`, and
the contexts in `view-contexts.json` (`stage-gen-view-contexts-v1`): each step's inputs,
outputs, facts and title, with each file's cache path and a small JSON file's value inline.
A copied run folder shows the same views wherever its workflow file is found.

The node inspector shows a step's view first, in a frame
([`ViewFrame.tsx`](../web/viewer/app/runs/[root]/[tag]/ViewFrame.tsx)) sandboxed to scripts
only, so it runs in an opaque origin. The frame asks for its context when it is ready; the viewer
answers with each file given its asset URL. A view imports its helper from `/_views/view.js`.
It only draws: it can open nothing in the viewer, reach no file it was not given, and load only
from the origins the project's `fx.yaml` lists in `view_origins`, which the run's `plan.json`
records. Looping parallax's compose step ships one that scrolls the composed layers, and
movie-sprite's finish step one that plays the loop's preview beside its contact sheet and checks.

## Serving and boundaries

`/api/assets/<root>/<tag>/<path>` serves files under one run folder of one configured root, and
a run's view templates and view files from its view cache folder. It validates the root key,
each tag segment and the portable artifact path, checks filesystem confinement, and refuses
symlink escapes. It serves known passive image, audio, video, model, text, and JSON media
types, with an opaque fallback and `nosniff`. It serves HTML only for a run's kept view
templates (`views/<sha256>.html`), always under a content security policy that
sandboxes it to scripts in an opaque origin and limits what it may load; it serves no other HTML,
and no SVG media type.

Nothing under [`lib/shell`](../web/viewer/lib/shell) starts a subprocess, and a docs check fails if
anything there imports one. Generation, retry, cache admission and artifact publication belong
to Grida FX, and deriving a run view to `stage_gen.runview`; the viewer only reads what it is
given. The web workspace imports no game engine. The viewer reads the run-view, catalog and
example wire formats through the shared parsers in [`web/ui/contracts`](../web/ui/contracts),
whose hand-authored fixtures a Python contract test also validates.

## Presentation

The shell uses Tailwind CSS v4. [`app/globals.css`](../web/viewer/app/globals.css) declares design
tokens and the transparent-image checkerboard; [`app/ui.ts`](../web/viewer/app/ui.ts) holds shared
utility class strings.

## Verification

Credential-free gates for this boundary are:

```sh
cd web
bun install --frozen-lockfile
bun run check
bun test
bun run --cwd viewer build
cd ..
uv run pytest -q tests/unit/test_runview.py tests/unit/test_run_views.py tests/unit/test_viewer.py
```

Tests cover multi-root discovery, the derived-view cache and its fallback, grouping by workflow,
generic view parsing, confined paths, bounded previews, node and graph inspection, the workflow
page, the specialized output views, and the launcher's environment and refusals. A browser check
can prove that supplied layers load and respond to preview controls. It does not establish
generated-media quality or prove that a game is playable.
