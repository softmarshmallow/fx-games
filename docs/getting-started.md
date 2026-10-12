# Getting started

FX Games runs from a source checkout. You need Python 3.12 or newer,
[uv](https://docs.astral.sh/uv/) and, for the engine, cargo from [rustup.rs](https://rustup.rs).
The site also needs [Bun](https://bun.sh).

## Install and look around

```sh
git submodule update --init
uv sync --frozen
uv run python third_party/fx/tools/build_engine.py
uv run python -m grida.fx schema movie-sprite
uv run python -m grida.fx nodes
```

Every workflow runs on [Grida FX](https://github.com/gridaco/fx), the engine at
`third_party/fx`. The first line fetches it, `uv sync` installs its Python package, and
`build_engine.py` builds its Rust engine from the pinned commit; build it again after a pull
that moves the pin.

The installed workflows are listed in the [README](../README.md#workflows) and on the site, each
with its page. Every workflow is an FX workflow file, and the root `fx.yaml` finds each by its
id (`workflows: [src/fx_games/workflows]`), so `python -m grida.fx` runs them all with the same
verbs: `plan`, `run` and `inspect`. `schema <id>` prints the inputs a workflow takes, as JSON
Schema; each top-level scalar or file input is also a flag (`--medium live_action` for
universe), and lists, maps and nested objects, such as universe's `census`, come from an
`--inputs` file. `nodes` lists FX's built-in node types, and `nodes <type>` one type's
settings, ports and the routes that serve it. `uv run python -m grida.fx --help` lists every
command, and the [FX guide](https://github.com/gridaco/fx/blob/main/docs/guide/README.md)
documents them.

## Run a workflow

Looping parallax runs offline. A committed script writes two original layers and the
`inputs.yaml` that places them, and the run makes no provider calls:

```sh
uv run python src/fx_games/workflows/looping_parallax/inputs/supplied_layers/make_inputs.py out/looping-parallax-input
uv run python -m grida.fx plan looping-parallax --inputs out/looping-parallax-input/inputs.yaml
uv run python -m grida.fx run looping-parallax --inputs out/looping-parallax-input/inputs.yaml --deliver manifest=out/looping-parallax-try/manifest.json
uv run python -m grida.fx inspect looping-parallax --verify
```

`plan` prints each phase the run would execute and its price, before any spend. `run` writes
a new run folder under `out/runs/looping-parallax/`: the record of what happened
(`events.jsonl`), the plan it started from and every step's files; `--deliver` copies an
output where you want it. Results live in FX's store (`out/fx-cache`), so running again
reuses whatever did not change. `inspect` reads the newest run back, and `--verify`
re-checks every file against its recorded digest.

Workflows that call a provider refuse to spend without an explicit opt-in: `--live` and a
ceiling (`--max-usd`). They need your own provider keys, which FX reads from the environment
or the project's `.env` file. Read [provider setup](models/providers.md) before a live run.

## See runs and examples

```sh
uv run python -m grida.fx start --open
```

FX's viewer lists every run under `out/runs/`, grouped by workflow, and draws each run's graph
with its steps' files on a canvas. It never starts a run; the
[FX guide](https://github.com/gridaco/fx/blob/main/docs/guide/07-viewing.md) shows how to use it.

The [site](site.md) shows each workflow with the example it pins, and the docs. Build and serve
it locally:

```sh
(cd web/site && bun install --frozen-lockfile)
uv run python scripts/site.py build --allow-missing-examples
uv run python scripts/site.py serve --port 8790
```

## Write your own workflow

Your own workflow is an FX workflow file, or a Python builder for a graph that a file cannot
state; `python -m grida.fx plan` and `run` take either, with the same store, takes and run
record the installed workflows use. The
[FX guide](https://github.com/gridaco/fx/blob/main/docs/guide/README.md) shows how, from a
first workflow to your own node types, and the [glossary](glossary.md) names the parts.
