#!/usr/bin/env python3
"""Run the complete credential-free offline gate, and report every step.

The gate used to stop at its first failure. That is the wrong shape for a
gate that a human reads once a day: a formatting drift at step one hid a
type error at step three and a failing contract test at step four for days,
because "it stopped" and "it passed" looked the same from a distance. Every
step now runs, every step is timed, and the verdict is a table.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from stage_gen.provider_env import PROVIDER_ENV_KEYS

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
WEB_ROOT = REPOSITORY_ROOT / "web" / "site"


@dataclass(frozen=True)
class Step:
    command: tuple[str, ...]
    cwd: Path = REPOSITORY_ROOT


@dataclass(frozen=True)
class Outcome:
    step: Step
    returncode: int | None
    seconds: float

    @property
    def passed(self) -> bool:
        return self.returncode == 0


def sanitized_environment(
    source: dict[str, str] | None = None, *, python: str = sys.executable
) -> dict[str, str]:
    """The caller's environment without provider credentials, with FX held offline: node bodies
    run on ``python``, no ``.env`` is read and no provider is reached. ``GRIDA_FX_BIN`` and
    ``GRIDA_FX_TOOL_*`` pass through."""
    environment = dict(os.environ if source is None else source)
    for variable in PROVIDER_ENV_KEYS:
        environment.pop(variable, None)
    environment["GRIDA_FX_PYTHON"] = python
    environment["GRIDA_FX_DISABLE_DOTENV"] = "1"
    environment["GRIDA_FX_NETWORK"] = "off"
    return environment


def commands(
    python: str = sys.executable, *, scope: str = "product", engine_bin: str | None = None
) -> tuple[tuple[str, ...], ...]:
    """The repository-rooted command list, kept for callers that read it as data."""

    return tuple(
        step.command
        for step in steps(python, scratch=Path("/dev/null"), scope=scope, engine_bin=engine_bin)
    )


WORKFLOWS_ROOT = "src/stage_gen/workflows"
#: Builds FX's engine from the submodule and puts it where ``python -m grida.fx`` finds it.
ENGINE_BUILD = "third_party/fx/tools/build_engine.py"


def _fx(python: str, *args: str) -> tuple[str, ...]:
    return (python, "-m", "grida.fx", *args)


def _engine_step(python: str, engine_bin: str | None) -> Step:
    """Every later step that plans or runs needs the engine: an engine named by ``GRIDA_FX_BIN``
    is only probed, otherwise the submodule's engine is built (cargo rebuilds only what changed)."""
    if engine_bin:
        return Step(_fx(python, "--version"))
    return Step((python, ENGINE_BUILD))


def _scratch_project(python: str, project: Path) -> Step:
    """An FX project in the scratch folder that finds the first-party workflows by id; its runs
    and its store stay inside it. Written by the one project writer the product uses."""
    program = (
        "import pathlib, sys; from stage_gen.workflows._fx import write_project; "
        "write_project(pathlib.Path(sys.argv[1]))"
    )
    return Step((python, "-c", program, str(project)))


# Source roots are explicit: checking each game wrapper named prepare.py in one
# mypy invocation would invent duplicate top-level modules. Their typed behavior
# lives in these packages; the wrappers are exercised by the local smoke commands.
GAME_PYTHON_ROOTS = (
    "godot/packages/scenario_runtime/authoring/src",
    "godot/games/_shared/python/src",
    "godot/games/bellweather/pipeline/src",
    "godot/games/iron_petal_unit/pipeline/src",
    "godot/games/ember_hollow/pipeline/src",
    "godot/games/the_grain/pipeline/src",
    "godot/tools/python/src",
)
#: Games built with FX: each one's builder and node modules are typed in their own run,
#: because node modules are top-level files whose names would collide across projects.
GAME_PROJECTS = (
    "godot/games/iron_petal_unit",
    "godot/games/bellweather",
    "godot/games/the_grain",
    "godot/games/ember_hollow",
)
#: The builder a one-builder game plans from its own folder.
BUILDER = "pipeline/workflow.py:build"
#: Each game's builders, the packages each one plans offline, and any other arguments.
GAME_PLANS: tuple[tuple[str, tuple[tuple[str, str, tuple[str, ...]], ...]], ...] = (
    ("iron_petal_unit", ((BUILDER, "inputs", ()),)),
    ("bellweather", ((BUILDER, "inputs/default", ()), (BUILDER, "inputs/waves", ()))),
    (
        "the_grain",
        (
            ("pipeline/workflow.py:room", "inputs/rooms/window", ()),
            ("pipeline/workflow.py:room", "inputs/rooms/motor_court", ()),
            ("pipeline/workflow.py:scene", "inputs", ()),
        ),
    ),
    (
        "ember_hollow",
        tuple(
            (BUILDER, "inputs", ("--arg", f"scope={scope}"))
            for scope in ("minimal", "props", "actors", "full")
        ),
    ),
)
GAME_TYPED_TOOLS = (
    "godot/games/bellweather/tools/author_terrain.py",
    "godot/games/bellweather/tools/design_map.py",
    "godot/games/bellweather/tools/prove_climbable_bands.py",
    "godot/games/bellweather/tools/render_asset_scale_figures.py",
    "godot/tools/parity_diff.py",
    "godot/tools/render_terrain_atlas_qa.py",
    "godot/tools/validate_game_package.py",
    "godot/tools/write_game_contract_identities.py",
    "godot/tools/write_game_graph_contract.py",
)


def _game_typechecks() -> tuple[Step, ...]:
    return tuple(
        Step(("mypy", "--strict", f"{game}/pipeline/workflow.py", f"{game}/pipeline/nodes"))
        for game in GAME_PROJECTS
    )


def _game_steps(python: str, *, scratch: Path) -> tuple[Step, ...]:
    """Exercise game-owned preparation entry points without provider work."""
    result = [
        # The Grain's script proves its case; its rooms and scene are planned below.
        Step((python, "godot/games/the_grain/pipeline/prepare.py")),
    ]
    # A game built with FX: its node types are locked and its builders plan each of its
    # packages, offline, from the game's folder.
    for game, plans in GAME_PLANS:
        home = REPOSITORY_ROOT / "godot/games" / game
        result.append(Step(_fx(python, "lock", "--check"), cwd=home))
        result.extend(
            Step(
                _fx(python, "plan", builder, "--arg", f"package={package}", *extra, "--check"),
                cwd=home,
            )
            for builder, package, extra in plans
        )
    result.extend(
        Step((python, "godot/tools/validate_game_package.py", "--input", input_path))
        for input_path in (
            "godot/games/bellweather/inputs/default",
            "godot/games/bellweather/inputs/waves",
            "godot/games/iron_petal_unit/inputs",
        )
    )
    result.extend(
        Step(("demo-games", "scenario", "check", "--input", input_path))
        for input_path in (
            "godot/games/bellweather/inputs/default",
            "godot/games/the_grain/inputs",
        )
    )
    result.append(Step(("demo-games", "case", "bundle", "--help")))
    return tuple(result)


CHARACTER_SAMPLE = "src/stage_gen/workflows/character_3d/inputs/sample/inputs.yaml"


def _asset_steps(python: str, *, scratch: Path) -> tuple[Step, ...]:
    """Run a real local workflow through FX (``python -m grida.fx``), check every workflow
    home's lock, and plan every workflow whose calls are all paid."""
    from stage_gen.workflows._registry import discover

    parallax = "src/stage_gen/workflows/looping_parallax/inputs/supplied_layers"
    inputs = scratch / "parallax-inputs"
    movie = "src/stage_gen/workflows/movie_sprite/inputs/supplied_clip"
    clip = scratch / "movie-sprite-inputs"
    portrait = "src/stage_gen/workflows/portrait_motion/inputs/make_inputs.py"
    face = scratch / "portrait-inputs"
    # A scratch folder with its own fx.yaml: the runs and their store stay inside it.
    project = scratch / "workflow-project"
    files = [w for w in discover() if w.root.joinpath("workflow.yaml").is_file()]
    return (
        # FX locks a folder: each workflow home's own fx.lock.
        *(
            Step(_fx(python, "lock", f"{WORKFLOWS_ROOT}/{workflow.root.name}", "--check"))
            for workflow in files
        ),
        Step((python, f"{parallax}/make_inputs.py", str(inputs))),
        _scratch_project(python, project),
        Step(
            _fx(python, "run", "looping-parallax", "--inputs", str(inputs / "inputs.yaml")),
            cwd=project,
        ),
        Step(_fx(python, "inspect", "looping-parallax", "--verify"), cwd=project),
        # movie-sprite: the paid take is only planned; the supplied clip is finished for free.
        Step((python, f"{movie}/make_inputs.py", str(clip))),
        Step(_fx(python, "plan", "movie-sprite", "--inputs", str(clip / "take.yaml")), cwd=project),
        Step(_fx(python, "run", "movie-sprite", "--inputs", str(clip / "clip.yaml")), cwd=project),
        Step(_fx(python, "inspect", "movie-sprite", "--verify"), cwd=project),
        # portrait-motion: every call is paid, so both paths are planned; pytest runs them on
        # the sample's stand-in answers.
        Step((python, portrait, str(face))),
        *(
            Step(_fx(python, "plan", "portrait-motion", "--inputs", str(face / name)), cwd=project)
            for name in ("face.yaml", "whole.yaml")
        ),
        # universe: the plan prices the world phase exactly and the gallery at its ceiling.
        Step(
            _fx(
                python,
                "plan",
                "universe",
                "--inputs",
                str(
                    REPOSITORY_ROOT
                    / "src/stage_gen/workflows/universe/inputs/lantern_ferry/inputs.yaml"
                ),
                "--check",
            ),
            cwd=project,
        ),
        # character-3d: every agent, mesh and rig call is paid, and its run needs Blender; the
        # committed brief is planned, and pytest runs the graph on stand-ins.
        Step(
            _fx(
                python,
                "plan",
                "character-3d",
                "--inputs",
                str(REPOSITORY_ROOT / CHARACTER_SAMPLE),
            ),
            cwd=project,
        ),
        Step(_fx(python, "--help")),
        Step(
            (
                python,
                "scripts/catalog.py",
                "--check",
                "--allow-missing-examples",
                "--out",
                str(scratch / "catalog"),
            )
        ),
    )


def steps(
    python: str = sys.executable,
    *,
    scratch: Path,
    scope: str = "product",
    engine_bin: str | None = None,
) -> tuple[Step, ...]:
    """Owned gates; the default product gate needs neither Bun nor Godot. Every scope starts
    with FX's engine, because its tests, the site and the catalog all plan."""
    from scripts.test_ownership import paths_for

    product_tests = paths_for(REPOSITORY_ROOT, "product")
    groups: dict[str, tuple[Step, ...]] = {
        "product": (
            Step(
                (
                    "ruff",
                    "format",
                    "--check",
                    "src",
                    "scripts",
                    *product_tests,
                )
            ),
            Step(("ruff", "check", "src", "scripts", *product_tests)),
            Step(("mypy", "--strict", "src")),
            Step(("pytest", *product_tests)),
            Step((python, "-m", "build", "--no-isolation")),
            *_asset_steps(python, scratch=scratch),
        ),
        "web": (
            Step(("bun", "run", "check"), WEB_ROOT),
            Step(("bun", "test"), WEB_ROOT),
            # The static site, from the catalog and whatever the example store holds.
            Step((python, "scripts/site.py", "build", "--allow-missing-examples")),
            Step(("pytest", *paths_for(REPOSITORY_ROOT, "web"))),
        ),
        "godot": (
            Step((python, "godot/tools/check.py")),
            Step(("pytest", *paths_for(REPOSITORY_ROOT, "godot"))),
        ),
        "games": (
            Step(("pytest", *paths_for(REPOSITORY_ROOT, "games"))),
            *_game_typechecks(),
            *_game_steps(python, scratch=scratch),
        ),
        "docs": (Step((python, "scripts/check_docs.py")),),
    }
    if scope == "all":
        return (
            _engine_step(python, engine_bin),
            Step(("ruff", "format", "--check", ".")),
            Step(("ruff", "check", ".")),
            Step(
                (
                    "mypy",
                    "--strict",
                    "src",
                    "tests",
                    "scripts",
                    *GAME_PYTHON_ROOTS,
                    *GAME_TYPED_TOOLS,
                    "godot/templates/asset_consumer/prepare.py",
                )
            ),
            Step(("pytest",)),
            *groups["web"][:3],
            *groups["godot"][:-1],
            *groups["docs"],
            *groups["games"][1:],
            *_asset_steps(python, scratch=scratch),
            Step((python, "-m", "build", "--no-isolation")),
        )
    if scope not in groups:
        raise ValueError(f"unknown verification scope: {scope}")
    return (_engine_step(python, engine_bin), *groups[scope])


def run_step(step: Step, environment: dict[str, str]) -> Outcome:
    printable = " ".join(step.command)
    print(f"+ {printable}", flush=True)
    started = time.monotonic()
    try:
        completed = subprocess.run(step.command, cwd=step.cwd, env=environment, check=False)
    except OSError as error:
        print(f"  could not start: {error}", file=sys.stderr, flush=True)
        return Outcome(step, None, time.monotonic() - started)
    return Outcome(step, completed.returncode, time.monotonic() - started)


def report(outcomes: Sequence[Outcome]) -> str:
    width = max(len(" ".join(outcome.step.command)) for outcome in outcomes)
    lines = []
    for outcome in outcomes:
        verdict = "PASS" if outcome.passed else "FAIL"
        code = "-" if outcome.returncode is None else str(outcome.returncode)
        printable = " ".join(outcome.step.command)
        lines.append(f"{verdict}  {outcome.seconds:7.1f}s  exit {code:>3}  {printable:<{width}}")
    failed = [outcome for outcome in outcomes if not outcome.passed]
    total = sum(outcome.seconds for outcome in outcomes)
    summary = (
        f"offline gate: {len(outcomes) - len(failed)} of {len(outcomes)} steps passed "
        f"in {total:.0f}s"
    )
    return "\n".join([*lines, summary])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run credential-free checks for an owned surface")
    parser.add_argument(
        "--scope",
        choices=("product", "web", "godot", "games", "docs", "all"),
        default="product",
    )
    args = parser.parse_args()
    environment = sanitized_environment(python=sys.executable)
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    with tempfile.TemporaryDirectory(prefix="stage-gen-gate-") as scratch:
        outcomes = [
            run_step(step, environment)
            for step in steps(
                scratch=Path(scratch).resolve(),
                scope=args.scope,
                engine_bin=environment.get("GRIDA_FX_BIN"),
            )
        ]
    print()
    print(report(outcomes), flush=True)
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
