"""Helpers for tests that plan and run workflows on FX, over public ``grida.fx`` names only.

A plan's instances are read as the raw rows of its ``fx-graph-v1`` document; a run's facts
from its events. A stand-in is one callable of a :class:`grida.fx.StandInCall`; ``dispatch``
makes one from a handler per capability, declining every other call.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from grida.fx import DECLINE, InputFile, Plan, RunResult, StandInCall

from fx_games.workflows._fx import write_project

REPOSITORY = Path(__file__).resolve().parents[2]
WORKFLOWS = REPOSITORY / "src/fx_games/workflows"
GAMES = REPOSITORY / "godot/games"

type Handler = Callable[[StandInCall], Any]


def scratch_project(
    folder: Path, *, workflows: bool = True, runs: str = "runs", cache: str = "cache"
) -> Path:
    """A project at ``folder`` whose runs and store stay inside it, finding the first-party
    workflows by id unless ``workflows`` is false."""
    return write_project(
        folder, runs=runs, cache=cache, workflows=(WORKFLOWS,) if workflows else ()
    )


def game_project(game: str, tmp_path: Path) -> Path:
    """A copy of a game's pipeline project at ``tmp_path/<game>``, its runs and store inside it.

    Plan the game's builder with ``cwd=`` the returned folder.
    """
    source = GAMES / game
    target = tmp_path / game
    (target / "pipeline").mkdir(parents=True, exist_ok=True)
    lines = []
    for line in (source / "fx.yaml").read_text("utf-8").splitlines():
        if line.startswith("runs:"):
            line = "runs: runs"
        elif line.startswith("cache:"):
            line = "cache: cache"
        lines.append(line)
    (target / "fx.yaml").write_text("\n".join(lines) + "\n", "utf-8")
    if (source / "fx.lock").is_file():
        shutil.copyfile(source / "fx.lock", target / "fx.lock")
    shutil.copytree(
        source / "pipeline/nodes",
        target / "pipeline/nodes",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copyfile(source / "pipeline/workflow.py", target / "pipeline/workflow.py")
    return target


def instances(plan: Plan) -> list[dict[str, Any]]:
    """Every instance row of the plan."""
    return [dict(row) for row in plan.document.get("instances") or []]


def first_takes(plan: Plan) -> list[dict[str, Any]]:
    """The rows a first run would make: present, and on their first take everywhere."""
    return [row for row in instances(plan) if row["state"] != "absent" and set(row["take"]) <= {1}]


def calls_of(plan: Plan) -> Counter[str]:
    """How many first-take instances call each capability."""
    return Counter(capability for row in first_takes(plan) for capability in row["routes"])


def by_step(plan: Plan) -> dict[str, dict[str, Any]]:
    """The first-take row of each step path (the last one, for a repeated step)."""
    return {row["step"]: row for row in first_takes(plan)}


def ceiling(plan: Plan) -> float | None:
    """The plan's ceiling in US dollars: ``--max-usd``, else a budget; None when it has none."""
    value = plan.document["estimate"]["ceiling_usd"]
    return None if value is None else float(value)


def problems(plan: Plan) -> str:
    return "; ".join(problem["message"] for problem in plan.problems)


def failures(result: RunResult) -> dict[str, str]:
    """Each failed instance's message, or why the run stopped when none failed."""
    failed = {id_: failure.message for id_, failure in result.failures.items()}
    return failed or {"stopped": str(result.stopped)}


def _finished_events(result: RunResult) -> list[Mapping[str, Any]]:
    return [event for event in result.events if event.get("event") == "node_finished"]


def finished(result: RunResult, id_: str) -> dict[str, Any]:
    """The last ``node_finished`` event of an instance (its ``facts``, ``cache``, ...)."""
    found = [event for event in _finished_events(result) if event.get("id") == id_]
    if not found:
        raise KeyError(f"{id_} never finished; finished: {sorted(caches(result))}")
    return dict(found[-1])


def caches(result: RunResult) -> dict[str, str]:
    """``hit`` or ``miss`` by instance id, over every finished instance."""
    return {str(event["id"]): str(event["cache"]) for event in _finished_events(result)}


def deliver(result: RunResult, folder: Path, output: str = "package") -> None:
    """Copy a keyed collection output's files into ``folder``, each at its key."""
    for key, file in result.outputs[output].items():
        target = folder / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file.path, target)


def schema_of(call: StandInCall) -> dict[str, Any]:
    """The JSON Schema a structured call asks for, inlined or as a file."""
    schema = call.request["schema"]
    if isinstance(schema, InputFile):
        schema = json.loads(schema.read_bytes())
    if not isinstance(schema, dict):
        raise TypeError(f"the call's schema is {type(schema).__name__}, not an object")
    return schema


def verify(run_dir: Path) -> list[str]:
    """What ``inspect --verify`` finds wrong with a run folder; empty when it verifies."""
    done = subprocess.run(
        [sys.executable, "-m", "grida.fx", "inspect", str(run_dir), "--verify"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 0:
        return []
    return (done.stdout + done.stderr).splitlines() or [f"exit {done.returncode}"]


def _decline(call: StandInCall) -> Any:
    del call
    return DECLINE


def dispatch(handlers: Mapping[str, Handler]) -> Handler:
    """One stand-in from a handler per capability; every other call is declined."""
    return lambda call: handlers.get(call.capability, _decline)(call)


__all__ = [
    "GAMES",
    "REPOSITORY",
    "WORKFLOWS",
    "by_step",
    "caches",
    "calls_of",
    "ceiling",
    "deliver",
    "dispatch",
    "failures",
    "finished",
    "first_takes",
    "game_project",
    "instances",
    "problems",
    "scratch_project",
    "verify",
]
