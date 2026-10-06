"""Host support for character-3d: the closure a qualification binds, and admission.

A support record is a reviewed deployment decision kept outside any run folder; no model
writes it. It says one configuration was qualified. That configuration is a closure, not
a hash of every installed file: the node types as ``fx.lock`` pins their source, the
workflow file, the core contract versions, each route with its contract, each paid step's
price, the Blender build, and the settings the cohort ran with. The brief, the reference
picture and the supplied parts may vary.

A run is supported only when its plan has exactly the recorded closure. Anything else runs
in development and claims nothing. ``run_supported`` admits a plan and then runs that same
plan, so nothing can change between the check and the run.

    python -m stage_gen.workflows.character_3d.support target --inputs inputs.yaml
    python -m stage_gen.workflows.character_3d.support run --record support.json \\
        --inputs inputs.yaml --live --max-usd 30
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from grida.fx import Plan, RunResult, run
from grida.fx import plan as make_plan

from stage_gen.runview import RUN_VIEW_KIND

type JsonObject = dict[str, Any]

WORKFLOW_ID = "character-3d"
HOME = Path(__file__).resolve().parent
#: The inputs that are the character, not the configuration: they may differ from the cohort.
CHARACTER_INPUTS = frozenset({"brief", "parts", "reference"})
_EVIDENCE = frozenset(
    {"cohort_manifest", "qualification_report", "calibration_report", "release_review"}
)
_RECORD_FIELDS = frozenset({"schema_version", "decision", "qualification_id", "target", "evidence"})


class SupportRefused(ValueError):
    """A support record that does not cover this configuration, or is not a valid decision."""


def _digest(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _blender() -> Path | None:
    """The Blender FX binds: ``GRIDA_FX_TOOL_BLENDER`` when set, else ``blender`` on PATH."""

    configured = os.environ.get("GRIDA_FX_TOOL_BLENDER")
    if configured:
        return Path(configured) if Path(configured).is_file() else None
    found = shutil.which("blender")
    return Path(found) if found is not None else None


def blender_build(executable: str | Path | None = None) -> JsonObject:
    """The Blender build a run would use: its executable's bytes."""

    found = Path(executable) if executable else _blender()
    if found is None or not found.is_file():
        raise SupportRefused("no Blender to bind: install it or set GRIDA_FX_TOOL_BLENDER")
    return {"sha256": _sha256_file(found)}


def closure(plan: Plan, *, blender: JsonObject) -> JsonObject:
    """What a qualification of this plan binds, apart from its settings."""

    if not plan.ok:
        problems = "; ".join(problem["message"] for problem in plan.problems)
        raise SupportRefused(f"the plan is refused, so it has no closure: {problems}")
    document = plan.document
    workflow = document["workflow"]
    if workflow["id"] != WORKFLOW_ID:
        raise SupportRefused(f"support binds {WORKFLOW_ID}, not {workflow['id']}")
    routes: dict[str, JsonObject] = {}
    prices: dict[str, list[float]] = {}
    for instance in document["instances"]:
        for capability, route in instance["routes"].items():
            routes[capability] = {"route": route["route"], "fingerprint": route["fingerprint"]}
        if instance["routes"]:
            # Route prices are not part of a fingerprint; a paid step's price shows a repricing.
            prices[instance["step"]] = [
                instance["price"]["low_usd"],
                instance["price"]["high_usd"],
            ]
    return {
        "workflow_sha256": _sha256_file(HOME / workflow["file"]),
        # Each type's identity and the digests of its source: what fx.lock pins.
        "types": dict(sorted(document["types"].items())),
        "contracts": {
            "workflow_document": "fx: workflow/v1",
            "graph": document["kind"],
            "run_events": "fx-run-events-v1",
            "run_view": RUN_VIEW_KIND,
        },
        "routes": dict(sorted(routes.items())),
        "prices": dict(sorted(prices.items())),
        "blender": dict(blender),
    }


@functools.cache
def _input_schema() -> JsonObject:
    """The JSON Schema the workflow's inputs compile to, as FX prints it."""

    done = subprocess.run(
        [sys.executable, "-m", "grida.fx", "schema", str(HOME / "workflow.yaml")],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SupportRefused(f"the workflow's inputs have no schema: {done.stderr.strip()}")
    schema: JsonObject = json.loads(done.stdout)
    return schema


def _with_defaults(schema: Mapping[str, Any], value: Any) -> Any:
    """``value`` with every default the schema states filled in, as FX fills them: a group of
    settings left out takes each of its fields' defaults."""

    if not isinstance(value, Mapping):
        return value
    filled = dict(value)
    for name, field in schema.get("properties", {}).items():
        if name in filled:
            filled[name] = _with_defaults(field, filled[name])
        elif "default" in field:
            filled[name] = field["default"]
        elif "properties" in field:
            filled[name] = _with_defaults(field, {})
    return filled


def planned_inputs(input_files: Sequence[Path]) -> JsonObject:
    """The inputs a plan of these files runs with: the files merged by name in order, the
    later winning, as FX merges them, and every default filled in."""

    given: JsonObject = {}
    for path in input_files:
        document = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            raise SupportRefused(f"{Path(path).name}: an inputs file maps input names to values")
        given.update(document)
    filled: JsonObject = _with_defaults(_input_schema(), given)
    return filled


def settings(inputs: Mapping[str, Any]) -> JsonObject:
    """The settings a cohort ran with: every input except the character itself."""

    chosen = {k: v for k, v in inputs.items() if k not in CHARACTER_INPUTS}
    chosen["entry"] = "brief" if inputs.get("brief") is not None else "parts"
    plain: JsonObject = json.loads(json.dumps(chosen, sort_keys=True, default=str))
    return plain


def support_target(plan: Plan, *, inputs: Mapping[str, Any], blender: JsonObject) -> JsonObject:
    """The exact target a support record must name for this plan, made from ``inputs``
    (:func:`planned_inputs`), to be supported."""

    return {"closure": closure(plan, blender=blender), "settings": settings(inputs)}


def admit(record: Mapping[str, Any] | None, target: Mapping[str, Any]) -> JsonObject:
    """Supported when ``record`` qualifies exactly ``target``; development without one."""

    if record is None:
        return {
            "schema_version": 1,
            "mode": "development",
            "support_qualified": False,
            "target_sha256": _digest(target),
        }
    if set(record) != _RECORD_FIELDS:
        raise SupportRefused("a support record has exactly " + ", ".join(sorted(_RECORD_FIELDS)))
    if (
        type(record["schema_version"]) is not int
        or record["schema_version"] != 1
        or record["decision"] != "qualified_for_support"
        or not isinstance(record["qualification_id"], str)
        or re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,95}", record["qualification_id"]) is None
    ):
        raise SupportRefused("the support decision is invalid or not qualified")
    evidence = record["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != _EVIDENCE:
        raise SupportRefused("a support decision names its complete reviewed evidence")
    if not all(_is_sha(value) for value in evidence.values()):
        raise SupportRefused("support evidence is named by SHA-256")
    if record["target"] != target:
        changed = sorted(
            key
            for part in ("closure", "settings")
            for key in set(record["target"].get(part, {})) | set(target.get(part, {}))
            if record["target"].get(part, {}).get(key) != target.get(part, {}).get(key)
        )
        raise SupportRefused(
            "the support record covers another configuration; changed: " + ", ".join(changed)
        )
    return {
        "schema_version": 1,
        "mode": "supported",
        "support_qualified": True,
        "target_sha256": _digest(target),
        "support_record_sha256": _digest(dict(record)),
        "qualification_id": record["qualification_id"],
    }


def run_supported(
    plan: Plan,
    record: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
    blender: JsonObject,
    run_dir: Path | None = None,
    live: bool = False,
) -> tuple[JsonObject, RunResult]:
    """Admit ``plan`` against ``record``, then run that same plan; refuses before any spend.
    The plan carries its own ceiling: a plan runs with the options it was planned with."""

    admission = admit(record, support_target(plan, inputs=inputs, blender=blender))
    result = run(plan, run_dir=run_dir, live=live)
    (result.run_dir / "support.json").write_text(json.dumps(admission, indent=2) + "\n")
    return admission, result


# ------------------------------------------------------------------------------ command


def _input_files(arguments: argparse.Namespace) -> list[Path]:
    # FX reads them from the project folder, so they are named from here, absolutely.
    return [Path(path).resolve() for path in arguments.inputs]


def _plan(arguments: argparse.Namespace) -> Plan:
    return make_plan(
        WORKFLOW_ID,
        input_files=_input_files(arguments),
        max_usd=arguments.max_usd,
        cwd=Path(arguments.project) if arguments.project else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m stage_gen.workflows.character_3d.support")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("target", "check", "run"):
        command = commands.add_parser(name)
        command.add_argument("--inputs", action="append", default=[], required=True)
        command.add_argument("--blender", default=None)
        command.add_argument("--project", default=None)
        command.add_argument("--max-usd", type=float, default=None)
        if name != "target":
            command.add_argument("--record", required=True)
        if name == "run":
            command.add_argument("--live", action="store_true")
            command.add_argument("--run-dir", default=None)
    arguments = parser.parse_args(argv)
    try:
        planned = _plan(arguments)
        inputs = planned_inputs(_input_files(arguments))
        blender = blender_build(arguments.blender)
        target = support_target(planned, inputs=inputs, blender=blender)
        if arguments.command == "target":
            print(json.dumps(target, indent=2, sort_keys=True))
            return 0
        record = yaml.safe_load(Path(arguments.record).read_text(encoding="utf-8"))
        if arguments.command == "check":
            print(json.dumps(admit(record, target), indent=2, sort_keys=True))
            return 0
        run_dir = Path(arguments.run_dir).resolve() if arguments.run_dir else None
        admission, _ = run_supported(
            planned,
            record,
            inputs=inputs,
            blender=blender,
            run_dir=run_dir,
            live=arguments.live,
        )
        print(json.dumps(admission, indent=2, sort_keys=True))
        return 0
    except SupportRefused as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
