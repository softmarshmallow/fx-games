"""Drift checks: where a workflow's code, manifest, prose and examples disagree.

Each check returns readable problems, never raises, so ``scripts/catalog.py --check``
and ``tests/contract/test_workflow_registry.py`` report every disagreement at once.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from stage_gen.examples import Currency, DisplayNames, FiguresLedger, WorkflowExample

from ._registry import (
    CONTRACT_FILE,
    EXAMPLE_PAGES,
    PAGE_FILE,
    DiscoveredWorkflow,
    ExampleEntry,
    Identity,
    PlannedSample,
    WorkflowCode,
    WorkflowManifest,
    folder_of,
    sample_artifact_refs,
)

README_BEGIN = "<!-- workflows:begin -->"
README_END = "<!-- workflows:end -->"
WORKFLOWS_PATH = "src/stage_gen/workflows"
CHECKED_BY = "> **Checked by:**"
ENVIRONMENT = re.compile(r"^[A-Z_][A-Z0-9_]*=")


@dataclass(frozen=True, slots=True)
class LoadedExample:
    """A pinned example as found: its documents when present, and what was wrong."""

    entry: ExampleEntry
    document: WorkflowExample | None
    figures: FiguresLedger | None
    missing: bool
    problems: tuple[str, ...]
    currency: Currency | None


@dataclass(frozen=True, slots=True)
class LoadedWorkflow:
    discovered: DiscoveredWorkflow
    code: WorkflowCode
    identity: Identity
    sample: PlannedSample | None
    examples: tuple[LoadedExample, ...]

    @property
    def id(self) -> str:
        return self.discovered.id

    def cover(self) -> LoadedExample | None:
        return next((e for e in self.examples if e.entry.cover), None)

    def example_type_ids(self) -> frozenset[str]:
        return frozenset(
            node.type_id
            for example in self.examples
            if example.document is not None
            for node in example.document.nodes.values()
        )

    def any_missing(self) -> bool:
        return any(example.missing for example in self.examples)


@dataclass(frozen=True, slots=True)
class CheckContext:
    names: DisplayNames
    golden: Mapping[str, Any] | None = None
    readme: str | None = None
    game_orders: Mapping[str, int] = field(default_factory=dict)


def _slug_like(title: str, slug: str) -> bool:
    return not title.strip() or title.strip() == slug


def structure(workflow: LoadedWorkflow) -> list[str]:
    """Folder, prose files, steps, titles and relabelling."""
    problems: list[str] = []
    found, manifest, code = workflow.discovered, workflow.discovered.manifest, workflow.code
    prefix = f"{manifest.id}:"
    if found.folder != folder_of(manifest.id):
        problems.append(f"{prefix} folder {found.folder} differs from its id")
    for name in (PAGE_FILE, CONTRACT_FILE):
        if not found.root.joinpath(name).is_file():
            problems.append(f"{prefix} {name} is missing")
    page = found.root.joinpath(PAGE_FILE)
    if page.is_file():
        problems += _restated(manifest.id, page.read_text("utf-8"), manifest)
    contract = found.root.joinpath(CONTRACT_FILE)
    if contract.is_file() and CHECKED_BY not in contract.read_text("utf-8"):
        problems.append(f"{prefix} {CONTRACT_FILE} has no '{CHECKED_BY}' line")
    pages = found.root.joinpath(EXAMPLE_PAGES)
    declared = {entry.id for entry in manifest.examples}
    if pages.is_dir():
        for page in pages.iterdir():
            if page.name.endswith(".mdx") and page.name.removesuffix(".mdx") not in declared:
                problems.append(f"{prefix} {EXAMPLE_PAGES}/{page.name} names no pinned example")

    placed = code.type_ids()
    doubled = sorted({t for t in placed if placed.count(t) > 1})
    if doubled:
        problems.append(f"{prefix} types placed in two steps: {', '.join(doubled)}")
    implemented = code.implemented_types()
    if unplaced := sorted(implemented - set(placed)):
        problems.append(f"{prefix} types in no step: {', '.join(unplaced)}")
    if unknown := sorted(set(placed) - implemented):
        problems.append(f"{prefix} steps place types the code does not have: {unknown}")
    if workflow.sample is not None:
        planned = {node.type_id for node in workflow.sample.nodes}
        if outside := sorted(planned - set(placed)):
            problems.append(f"{prefix} the sample plan has types in no step: {outside}")
    if (workflow.sample is None) == (code.no_sample_plan is None):
        problems.append(f"{prefix} a missing sample plan needs a reason, and only then")

    if _slug_like(manifest.title, manifest.id):
        problems.append(f"{prefix} title {manifest.title!r} is empty or its raw slug")
    types = code.node_types()
    for step in code.steps:
        for member in step.members:
            type_id = member.type_id
            title = manifest.label(type_id, types.get(type_id))
            slug = re.split(r"[/.]", type_id)[-1]
            if _slug_like(title, slug):
                problems.append(f"{prefix} {type_id} has no reader title ({title!r})")
    for entry in manifest.examples:
        if _slug_like(entry.title, entry.id):
            problems.append(f"{prefix} example {entry.id} title is empty or its raw slug")
    return problems


def _restated(workflow_id: str, page: str, manifest: WorkflowManifest) -> list[str]:
    """The manifest is the one home of the summary and the output notes: the site renders them
    (an empty ``<File path=... />`` takes its note from ``[[outputs]]``), so a page that copies
    one keeps a second copy that drifts."""
    text = " ".join(page.split())
    problems: list[str] = []
    if (summary := " ".join(manifest.summary.split())) and summary in text:
        problems.append(f"{workflow_id}: {PAGE_FILE} restates the workflow.toml summary")
    problems += [
        f"{workflow_id}: {PAGE_FILE} restates the [[outputs]] note of {note.artifact_ref}; "
        f'write <File path="{note.artifact_ref}" /> instead'
        for note in manifest.outputs
        if " ".join(note.description.split()) in text
    ]
    return problems


def labels(workflow: LoadedWorkflow) -> list[str]:
    """A label may title only a type that appears in one of the workflow's pinned examples
    and not in its steps: a step's title lives in the workflow file."""
    problems: list[str] = []
    manifest, code = workflow.discovered.manifest, workflow.code
    own, seen = set(code.type_ids()), workflow.example_type_ids()
    for target in manifest.labels:
        if target in own:
            problems.append(
                f"{manifest.id}: [labels] retitles {target}, whose title is in the workflow file"
            )
        elif target not in seen and not workflow.any_missing():
            problems.append(f"{manifest.id}: [labels] names {target}, which no type or example has")
    return problems


def outputs(workflow: LoadedWorkflow) -> list[str]:
    """Each output note must name a port of the sample plan or a path of the cover example."""
    manifest = workflow.discovered.manifest
    refs = set() if workflow.sample is None else sample_artifact_refs(workflow.sample)
    refs |= {ref.rstrip("/") for ref in refs}
    cover = workflow.cover()
    if cover is not None and cover.document is not None:
        refs.update(cover.document.tree)
    unverifiable = cover is not None and cover.missing
    return [
        f"{manifest.id}: output {note.artifact_ref} is in neither the sample plan nor the cover"
        for note in manifest.outputs
        if note.artifact_ref.rstrip("/") not in refs and not unverifiable
    ]


def examples(workflows: Sequence[LoadedWorkflow], context: CheckContext) -> list[str]:
    """Pins, covers, landing order, relations and model display names."""
    problems: list[str] = []
    ids = {w.id for w in workflows}
    orders: dict[int, list[str]] = {}
    for owner, order in context.game_orders.items():
        orders.setdefault(order, []).append(owner)
    for workflow in workflows:
        manifest = workflow.discovered.manifest
        for related in manifest.related:
            if related not in ids or related == manifest.id:
                problems.append(f"{manifest.id}: related names unknown workflow {related}")
        covers = [e for e in manifest.examples if e.cover]
        if len(covers) > 1:
            problems.append(f"{manifest.id}: more than one cover example")
        if any(e.status != "approved" for e in covers):
            problems.append(f"{manifest.id}: the cover example must be approved")
        if len({e.id for e in manifest.examples}) != len(manifest.examples):
            problems.append(f"{manifest.id}: an example id is pinned twice")
        for entry in manifest.examples:
            if entry.order is not None:
                if entry.status != "approved":
                    problems.append(f"{manifest.id}/{entry.id}: only approved examples have cards")
                orders.setdefault(entry.order, []).append(f"{manifest.id}/{entry.id}")
        for example in workflow.examples:
            entry = example.entry
            problems.extend(f"{manifest.id}/{entry.id}: {p}" for p in example.problems)
            document = example.document
            if document is None:
                continue
            if document.example_id != entry.id or document.made_by.id != manifest.id:
                problems.append(f"{manifest.id}/{entry.id}: the document names another example")
            problems.extend(f"{manifest.id}/{entry.id}: {p}" for p in _own_steps(entry, document))
            for row in document.models:
                if row.provider != "local" and not context.names.knows_model(row.name):
                    problems.append(f"{manifest.id}/{entry.id}: model {row.name} has no name")
        if workflow.sample is not None:
            for node in workflow.sample.nodes:
                if node.model and node.model not in context.names.models:
                    problems.append(f"{manifest.id}: route model {node.model} has no name")
    for order, owners in sorted(orders.items()):
        if len(owners) > 1:
            problems.append(f"landing order {order} is claimed by {', '.join(owners)}")
    return problems


def _own_steps(entry: ExampleEntry, document: WorkflowExample) -> list[str]:
    """An example's own steps place each of its nodes once; its labels title its nodes."""
    nodes = set(document.nodes)
    problems = [
        f"labels names {node}, which is not a node of it"
        for node in entry.labels
        if node not in nodes
    ]
    if not entry.steps:
        return problems
    placed = [member for step in entry.steps for member in step.members]
    unknown = sorted(set(placed) - nodes)
    missing = sorted(nodes - set(placed))
    doubled = sorted({member for member in placed if placed.count(member) > 1})
    if unknown or missing or doubled:
        problems.append(
            f"steps must place every node once: unplaced {missing}, unknown {unknown}, "
            f"doubled {doubled}"
        )
    return problems


def game_example(
    owner: str,
    entry: Mapping[str, Any] | None,
    example: Mapping[str, Any],
    workflow_ids: set[str],
    names: DisplayNames,
) -> list[str]:
    """An example a game exported: it names its own game, related workflows that exist, and
    models with display names. Its pins and ledger are checked by ``verify_game_example``."""
    if entry is None:
        return []
    problems: list[str] = []
    if entry["made_by"] != {"kind": "game", "id": owner}:
        problems.append(f"entry.json says it was made by {entry['made_by']}, not the game {owner}")
    problems += [
        f"related names unknown workflow {related}"
        for related in entry["related"]
        if related not in workflow_ids
    ]
    problems += [
        f"model {row['name']} has no name"
        for row in example["models"]
        if row["provider"] != "local" and not names.knows_model(row["name"])
    ]
    return problems


def identity(workflow: LoadedWorkflow, golden: Mapping[str, Any]) -> list[str]:
    """``CODE.identity()`` must agree with the identity golden wherever the golden pins it."""
    inventory = {tuple(entry) for entry in golden["identities"]["node_types"]}
    return [
        f"{workflow.id}: identity node type {entry[0]} is not in the golden inventory"
        for entry in _entries(workflow.identity.get("node_types", []))
        if entry not in inventory
    ]


def _entries(value: object) -> Iterable[tuple[str, ...]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, list):
                yield tuple(str(part) for part in item)


def readme_table(workflows: Sequence[LoadedWorkflow]) -> str:
    rows = [
        "| Workflow | Id | Promise |",
        "| --- | --- | --- |",
        *(
            f"| [{w.discovered.manifest.title}]({WORKFLOWS_PATH}/{folder_of(w.id)}/{PAGE_FILE}) "
            f"| `{w.id}` | {w.discovered.manifest.promise} |"
            for w in workflows
        ),
    ]
    return "\n".join(rows)


def readme(workflows: Sequence[LoadedWorkflow], text: str) -> list[str]:
    if README_BEGIN not in text or README_END not in text:
        return [f"README.md has no {README_BEGIN} ... {README_END} workflow table"]
    current = text.split(README_BEGIN, 1)[1].split(README_END, 1)[0].strip()
    if current != readme_table(workflows):
        return [
            "README.md workflow table differs from workflow.toml; expected:\n"
            + readme_table(workflows)
        ]
    return []


def try_commands(workflow: LoadedWorkflow) -> list[str]:
    """Each ``[try]`` command must be ``[uv run] python -m grida.fx <verb> ...`` and parse
    against FX's own help; a ``plan`` or ``run`` command's other flags must be the workflow's
    inputs. A command may start with environment assignments."""
    manifest = workflow.discovered.manifest
    if manifest.try_ is None:
        return []
    problems: list[str] = []
    for command in manifest.try_.commands:
        words = shlex.split(command)
        while words and ENVIRONMENT.match(words[0]):
            words = words[1:]
        if words[:2] == ["uv", "run"]:
            words = words[2:]
        if tuple(words[: len(FX_PROGRAM)]) != FX_PROGRAM:
            problems.append(f"{manifest.id}: [try] command does not start with python -m grida.fx")
            continue
        problems += [
            f"{manifest.id}: [try] {p}" for p in fx_command_problems(words[len(FX_PROGRAM) :])
        ]
    return problems


#: How a command runs FX: the engine's own command line, through the interpreter.
FX_PROGRAM = ("python", "-m", "grida.fx")
#: The verbs whose unknown flags may be the target workflow's inputs.
_INPUT_VERBS = frozenset({"plan", "run"})
_OPTION = re.compile(r"^\s+(?:(?P<short>-\w),\s+)?(?P<long>--[\w-]+)(?:\s+<(?P<value>[^>]+)>)?")
_ARGUMENT = re.compile(r"^\s+(?P<open>[<\[])(?P<name>[^>\]]+)[>\]](?P<many>\.\.\.)?")
_COMMAND = re.compile(r"^\s+(?P<name>[a-z][a-z-]*)\s")


@dataclass(frozen=True, slots=True)
class _Verb:
    """One verb's command line, as its ``--help`` states it."""

    #: Each option, short and long, to whether it takes a value.
    options: Mapping[str, bool]
    #: Each positional argument: required, and whether it repeats.
    arguments: tuple[tuple[bool, bool], ...]


def _sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        if line and not line[0].isspace() and line.endswith(":"):
            current = sections.setdefault(line[:-1], [])
        elif current is not None and line.strip():
            current.append(line)
    return sections


@cache
def _fx_help(*verb: str) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "grida.fx", *verb, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"python -m grida.fx {' '.join(verb)} --help: {done.stderr.strip()}")
    return done.stdout


@cache
def _verbs() -> frozenset[str]:
    commands = _sections(_fx_help()).get("Commands", [])
    return frozenset(
        match["name"] for line in commands if (match := _COMMAND.match(line)) and line
    ) - {"help"}


@cache
def _verb(name: str) -> _Verb:
    sections = _sections(_fx_help(name))
    options: dict[str, bool] = {}
    for line in sections.get("Options", []):
        if (match := _OPTION.match(line)) is not None:
            takes = match["value"] is not None
            options[match["long"]] = takes
            if match["short"]:
                options[match["short"]] = takes
    arguments = tuple(
        (match["open"] == "<", match["many"] is not None)
        for line in sections.get("Arguments", [])
        if (match := _ARGUMENT.match(line)) is not None
    )
    return _Verb(options, arguments)


def fx_command_problems(words: Sequence[str]) -> list[str]:
    """What is wrong with one FX command line, given its words after ``python -m grida.fx``:
    its verb, options and arguments must be what ``python -m grida.fx <verb> --help`` states,
    and a ``plan`` or ``run`` of a first-party workflow may add that workflow's input flags."""
    shown = f"python -m grida.fx {shlex.join(words)}".rstrip()
    if not words:
        return [f"{shown} names no verb"]
    if list(words) in (["--help"], ["-h"], ["--version"], ["-V"]):
        return []
    verb_name, rest = words[0], list(words[1:])
    if verb_name not in _verbs():
        return [f"{shown}: {verb_name} is not an FX verb"]
    verb = _verb(verb_name)
    positional: list[str] = []
    unknown: list[str] = []
    problems: list[str] = []
    index = 0
    while index < len(rest):
        word = rest[index]
        index += 1
        if word == "--":
            positional += rest[index:]
            break
        if not word.startswith("-") or word == "-":
            positional.append(word)
            continue
        option, equals, _ = word.partition("=")
        if option not in verb.options:
            unknown.append(option)
            # An input flag takes its value as the next word, unless it was joined by "=".
            if not equals and index < len(rest) and not rest[index].startswith("--"):
                index += 1
            continue
        if verb.options[option] and not equals:
            if index >= len(rest):
                problems.append(f"{shown}: {option} needs a value")
            index += 1
        elif not verb.options[option] and equals:
            problems.append(f"{shown}: {option} takes no value")
    required = sum(1 for needed, _ in verb.arguments if needed)
    repeats = any(many for _, many in verb.arguments)
    if len(positional) < required:
        problems.append(f"{shown}: {verb_name} needs {required} argument(s)")
    elif not repeats and len(positional) > len(verb.arguments):
        problems.append(f"{shown}: unexpected arguments {positional[len(verb.arguments) :]}")
    if unknown:
        inputs = _input_names(positional[0]) if verb_name in _INPUT_VERBS and positional else None
        flags = {f"--{name.replace('_', '-')}" for name in inputs or ()}
        if strangers := [option for option in unknown if option not in flags]:
            problems.append(f"{shown} has unknown flags {strangers}")
    return problems


def _input_names(target: str) -> list[str] | None:
    """The input names of a workflow file or a first-party workflow id, from FX's schema of
    its inputs; None for any other target."""
    from ._fx import workflow_file

    if target.endswith((".yaml", ".yml")):
        path = Path(target).resolve()
        if not path.is_file():
            return None
    else:
        try:
            path = workflow_file(target)
        except ValueError:
            return None
    done = subprocess.run(
        [sys.executable, "-m", "grida.fx", "schema", path.name],
        capture_output=True,
        text=True,
        check=False,
        cwd=path.parent,
    )
    if done.returncode != 0:
        return None
    return list(json.loads(done.stdout).get("properties") or {})


def drift(workflows: Sequence[LoadedWorkflow], context: CheckContext) -> list[str]:
    problems: list[str] = []
    for workflow in workflows:
        problems += structure(workflow)
        problems += labels(workflow)
        problems += outputs(workflow)
        problems += try_commands(workflow)
        if context.golden is not None:
            problems += identity(workflow, context.golden)
    problems += examples(workflows, context)
    if context.readme is not None:
        problems += readme(workflows, context.readme)
    return problems


__all__ = [
    "FX_PROGRAM",
    "CheckContext",
    "LoadedExample",
    "LoadedWorkflow",
    "drift",
    "fx_command_problems",
    "game_example",
    "readme_table",
]
