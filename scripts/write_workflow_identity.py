#!/usr/bin/env python3
"""Check or write the workflow identity golden: every identity a code move must not change.

tests/contract/fixtures/workflow-identity.json holds values only - digests, strings,
versions and cache keys - never a module path, so moving code changes this script's
imports and never the fixture. Each section prices what a change to it would cost:

  identities               the run-view version and the product node-type inventory
  cache_keys               instance id -> identity for offline plans and free runs over
                           committed files or the constant bytes in
                           workflow-identity-inputs.json, and the key of each paid call a
                           free run made through a stand-in that answers with constant bytes

The input bytes are constants captured once. Nothing here regenerates them with Pillow or
FFmpeg, runs a provider or reads a credential: every run is a stand-in run in a scratch
project, offline.

    uv run python scripts/write_workflow_identity.py --check
    uv run python scripts/write_workflow_identity.py --only identities
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import runpy
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from grida.fx import Answer, RunResult, StandInCall, plan, run

import stage_gen
from stage_gen.fs import atomic_write_text
from stage_gen.runview import RUN_VIEW_SCHEMA_VERSION, read_plan
from stage_gen.workflows._fx import FxWorkflow, instances, write_project
from stage_gen.workflows._registry import NodeType, discover

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPOSITORY_ROOT / "tests/contract/fixtures"
GOLDEN_PATH = FIXTURES / "workflow-identity.json"
INPUTS_PATH = FIXTURES / "workflow-identity-inputs.json"

PACKAGE_ROOT = Path(stage_gen.__file__).parent
UNIVERSE_INPUTS = PACKAGE_ROOT / "workflows/universe/inputs/lantern_ferry/inputs.yaml"
UNIVERSE_ANSWERS = FIXTURES / "universe/lantern_ferry.answers.json"

type Section = dict[str, Any]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _node_types() -> Iterable[NodeType]:
    # A workflow file's steps, each titled and typed by the FX type it uses.
    for workflow in discover():
        if workflow.root.joinpath("workflow.yaml").is_file():
            yield from FxWorkflow.read(workflow.package).types.values()


def identities(scratch: Path) -> Section:
    del scratch
    inventory = {
        (node_type.type_id, node_type.cache_identity, node_type.contract_version)
        for node_type in _node_types()
    }
    return {
        "view_schema_version": RUN_VIEW_SCHEMA_VERSION,
        "node_types": [list(entry) for entry in sorted(inventory)],
    }


def materialize_inputs(name: str, scratch: Path) -> Path:
    """Write one set of the constant input bytes into ``scratch`` and return its root."""
    encoded = json.loads(INPUTS_PATH.read_text(encoding="utf-8"))[name]
    root = scratch / "inputs" / name
    for relative, data in encoded.items():
        parts = PurePosixPath(relative).parts
        if PurePosixPath(relative).is_absolute() or ".." in parts:
            raise ValueError(f"identity input escapes its root: {relative}")
        target = root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(data, validate=True))
    return root


#: The looping-parallax sample's placement over the constant layer bytes.
PARALLAX_INPUTS = {
    "canvas": {"width": 640, "height": 360},
    "layers": [
        {"layer_id": "distant_hills", "file": "distant_hills.png", "order": 0, "parallax": 0.2},
        {"layer_id": "near_trees", "file": "near_trees.png", "order": 1, "parallax": 0.7},
    ],
}


def _project(scratch: Path) -> Path:
    """A scratch FX project that finds the first-party workflows by id, its runs and store
    inside it."""
    return write_project(scratch / "project", runs="runs", cache="cache")


def _run_keys(result: RunResult) -> dict[str, str]:
    """Every finished step's identity, a step the plan already ran (``at: plan``) included,
    and every paid call's key, of one run."""
    planned = read_plan(result.run_dir).get("instances") or []
    keys = {str(i["id"]): str(i["identity"]) for i in planned if i.get("state") == "done"}
    finished = {event["id"] for event in result.events if event.get("event") == "node_finished"}
    for event in result.events:
        if event.get("event") == "node_started" and event["id"] in finished:
            keys[str(event["id"])] = str(event["identity"])
        elif event.get("event") == "call":
            keys[f"{event['id']} {event['capability']}"] = str(event["call"])
    return dict(sorted(keys.items()))


def _ran(name: str, result: RunResult) -> dict[str, str]:
    if not result.ok:
        failed = {id_: failure.message for id_, failure in result.failures.items()}
        raise RuntimeError(f"the {name} sample failed: {failed or result.stopped}")
    return _run_keys(result)


def run_looping_parallax(scratch: Path) -> dict[str, str]:
    """The sample run offline, free: every identity, downstream of results included."""
    root = materialize_inputs("looping-parallax", scratch)
    inputs = root / "inputs.yaml"
    inputs.write_text(json.dumps(PARALLAX_INPUTS), encoding="utf-8")
    result = run("looping-parallax", input_files=[inputs], cwd=_project(scratch))
    return _ran("looping-parallax", result)


def run_movie_sprite_take(scratch: Path) -> dict[str, str]:
    """The take path run offline, free: the paid take answered with a constant clip, so
    every step identity and the take's call key are pinned, finishing included."""
    root = materialize_inputs("movie-sprite-take", scratch)
    inputs = root / "take.yaml"
    inputs.write_text(
        json.dumps(
            {
                "character": "character.png",
                "seconds": 3,
                "resolution": "360p",
                "finish": "finish.json",
            }
        ),
        encoding="utf-8",
    )
    clip = (root / "take.mp4").read_bytes()

    def take(call: StandInCall) -> Answer:
        assert call.capability == "video.generate", call.capability
        return Answer(files={"video": clip})

    result = run("movie-sprite", input_files=[inputs], cwd=_project(scratch), stand_in=take)
    return _ran("movie-sprite take", result)


def _text(value: Any) -> str:
    """A request's text, sent as written or as the file that holds it."""
    return value if isinstance(value, str) else str(value.read_bytes().decode("utf-8"))


def _schema(value: Any) -> Mapping[str, Any]:
    """A request's schema, sent as the object or as the file that holds it."""
    if isinstance(value, Mapping):
        return value
    schema: Mapping[str, Any] = json.loads(value.read_bytes())
    return schema


def _universe_answers() -> Callable[[StandInCall], Answer]:
    """Every paid call of the lantern_ferry world, answered from committed constants."""

    answers = json.loads(UNIVERSE_ANSWERS.read_text(encoding="utf-8"))
    pictures = {
        size: base64.b64decode(encoded) for size, encoded in answers["images_png_base64"].items()
    }

    def answer(call: StandInCall) -> Answer:
        if call.capability == "image.generate":
            return Answer(files={"image": pictures[str(call.request["size"])]})
        assert call.capability == "structured.generate", call.capability
        title = str(_schema(call.request["schema"])["title"])
        value = answers[title]
        if title in {"EntityDirection", "ImageReview"}:
            prompt = _text(call.request["prompt"])
            bound = re.search(r"(?:Bound|Required) entity_id: (\w+)", prompt)
            assert bound is not None, title
            value = value[bound[1]]
        return Answer.json(value)

    return answer


def run_universe(scratch: Path) -> dict[str, str]:
    """The committed lantern_ferry world, run free: every call answered from constants, so
    every step identity and every paid call's key is pinned, the gallery included."""
    result = run(
        "universe",
        input_files=[UNIVERSE_INPUTS],
        cwd=_project(scratch),
        stand_in=_universe_answers(),
    )
    return _ran("universe", result)


#: Draws the portrait sample and answers its paid calls from the sample's own colours.
PORTRAIT_INPUTS_SCRIPT = PACKAGE_ROOT / "workflows/portrait_motion/inputs/make_inputs.py"


def run_portrait_motion(scratch: Path) -> dict[str, str]:
    """The face path run offline, free: every paid call answered by the sample's stand-in,
    so every step identity and every call's key is pinned, the reconstruction included."""
    root = materialize_inputs("portrait-motion", scratch)
    inputs = root / "face.yaml"
    inputs.write_text(
        json.dumps({"portrait": "sprite.png", "spec": "spec.json", "face_crop": True}),
        encoding="utf-8",
    )
    stand_in = runpy.run_path(str(PORTRAIT_INPUTS_SCRIPT))["stand_in"]
    result = run("portrait-motion", input_files=[inputs], cwd=_project(scratch), stand_in=stand_in)
    return _ran("portrait", result)


CHARACTER_INPUTS = PACKAGE_ROOT / "workflows/character_3d/inputs/sample/inputs.yaml"


def plan_character_3d(scratch: Path) -> dict[str, str]:
    """The committed brief planned offline: the identity of every step a plan can know
    (a run needs Blender, so the rest is pinned by the workflow's own offline tests)."""
    planned = plan("character-3d", input_files=[CHARACTER_INPUTS], cwd=_project(scratch))
    if not planned.ok:
        raise RuntimeError(f"the character sample does not plan: {planned.problems}")
    return dict(
        sorted((i.id, str(i.identity)) for i in instances(planned) if i.identity is not None)
    )


#: Each pinned plan or free run.
CACHE_KEY_PLANS: dict[str, Callable[[Path], dict[str, str]]] = {
    "character-3d": plan_character_3d,
    "looping-parallax": run_looping_parallax,
    "movie-sprite-take": run_movie_sprite_take,
    "portrait-motion": run_portrait_motion,
    "universe": run_universe,
}


def cache_keys(scratch: Path) -> Section:
    return {name: build(scratch / name) for name, build in CACHE_KEY_PLANS.items()}


SECTIONS: dict[str, Callable[[Path], Section]] = {
    "identities": identities,
    "cache_keys": cache_keys,
}


def compute(names: Iterable[str]) -> dict[str, Section]:
    with tempfile.TemporaryDirectory(prefix="workflow-identity-") as scratch:
        return {name: SECTIONS[name](Path(scratch) / name) for name in names}


def render(sections: Mapping[str, Section]) -> str:
    return json.dumps(sections, indent=1, sort_keys=True) + "\n"


def differences(expected: object, actual: object, prefix: str = "") -> list[str]:
    """Dotted paths that differ between two JSON values; the whole failure message."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        lines: list[str] = []
        for key in sorted(set(expected) | set(actual), key=str):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in actual:
                lines.append(f"  removed {path}")
            elif key not in expected:
                lines.append(f"  added   {path}")
            else:
                lines.extend(differences(expected[key], actual[key], path))
        return lines
    if expected == actual:
        return []
    if isinstance(expected, list) and isinstance(actual, list):
        before = [json.dumps(item) for item in expected]
        after = [json.dumps(item) for item in actual]
        changed = [f"  removed {prefix} item {item}" for item in before if item not in after]
        changed += [f"  added   {prefix} item {item}" for item in after if item not in before]
        return changed or [f"  changed {prefix}: order or repetition"]
    return [f"  changed {prefix}: {json.dumps(expected)} -> {json.dumps(actual)}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="compare without writing")
    parser.add_argument("--only", choices=tuple(SECTIONS), help="check or rewrite one section")
    args = parser.parse_args(argv)
    # Every engine this script starts stays offline and reads no ``.env``.
    os.environ.update(GRIDA_FX_DISABLE_DOTENV="1", GRIDA_FX_NETWORK="off")
    names = (args.only,) if args.only else tuple(SECTIONS)
    actual = compute(names)
    pinned: dict[str, Section] = (
        json.loads(GOLDEN_PATH.read_text(encoding="utf-8")) if GOLDEN_PATH.is_file() else {}
    )
    if args.check:
        lines = [
            line
            for name in names
            for line in (
                differences(pinned[name], actual[name], name)
                if name in pinned
                else [f"  missing section {name}"]
            )
        ]
        for line in lines:
            print(line)
        if lines:
            print("workflow identity moved; read the diff before rewriting any section")
            return 1
        print("workflow identity is current")
        return 0
    atomic_write_text(GOLDEN_PATH, render({**pinned, **actual}), mode=0o644)
    print(f"wrote {', '.join(names)} to {GOLDEN_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
