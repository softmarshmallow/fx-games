"""What each view of an FX run reads: a step's view, and the workflow's own view.

A step chooses a view with its ``view:`` setting: ``true`` picks a generic template by the kind
of its first output file (pictures, data or clips), and a path names a template in the
workflow's home. A workflow names its own view with a top-level ``view:``. FX records neither
template, so they are read here: the step's setting from the plan, the workflow's from its
file. A context (``stage-gen-view-context-v1``) is a projection of the run; the templates and
the files it shows are named by digest (``views/<sha>.html``, ``views/files/<digest><suffix>``)
for the view cache to keep, and their sources are listed beside the contexts. Nothing is
written into the run.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from stage_gen.runview.facts import FactsReader, file_facts
from stage_gen.runview.folder import (
    PROJECT_FILE,
    ending,
    files_of,
    find_file,
    placed_files,
    project_file,
    read_events,
    read_plan,
    relative_within,
    suffix_of_kind,
)
from stage_gen.runview.project import run_state

VIEW_CONTEXT_KIND = "stage-gen-view-context-v1"
#: A JSON file a view shows is inlined up to this size; past it the view reads its URL.
INLINE_JSON_BYTES = 256 * 1024
#: The generic templates ``view: true`` picks from, by kind and then by family.
#: The generic template for a kind or its family, in precedence order: a ``view: true`` step
#: shows the first of these any of its output files has, whatever its ports are named (a run
#: records ports in canonical, sorted order, not as declared).
GENERIC_VIEWS = {"image": "image.html", "video": "video.html", "json": "json.html"}
_TEMPLATES = Path(__file__).resolve().parent / "views"


@dataclass(slots=True)
class RunViews:
    """A run's view contexts, and the sources of the templates and files they name, keyed by
    where the view cache keeps each (``views/<sha>.html``, ``views/files/<digest><suffix>``)."""

    contexts: list[dict[str, Any]] = field(default_factory=list)
    templates: dict[str, Path] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)


def view_file(digest: str, kind: str) -> str:
    """Where the view cache keeps a file a view shows."""

    return f"views/files/{digest}{suffix_of_kind(kind)}"


def _workflow_document(path: Path) -> dict[str, Any] | None:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    return document if isinstance(document, dict) else None


def _workflow_file(run_dir: Path, plan: Mapping[str, Any]) -> Path | None:
    """The workflow file the run was planned from, found again: under the planning project, or
    in the installed workflow of that id. A builder's (``<file>:<function>``) has none."""

    workflow = plan.get("workflow", {})
    identifier, file = workflow.get("id"), workflow.get("file")
    if not isinstance(identifier, str) or not isinstance(file, str) or ":" in file:
        return None
    from stage_gen.workflows._registry import WORKFLOWS_PACKAGE, folder_of

    candidates: list[Path] = []
    project = project_file(run_dir)
    if project is not None:
        candidates.append(project.parent / file)
    packaged = resources.files(WORKFLOWS_PACKAGE).joinpath(folder_of(identifier))
    candidates.append(Path(str(packaged)) / Path(file).name)
    for candidate in candidates:
        if candidate.suffix not in {".yaml", ".yml"} or not candidate.is_file():
            continue
        document = _workflow_document(candidate)
        if document is not None and document.get("id") == identifier:
            return candidate
    return None


def workflow_home(run_dir: Path, plan: Mapping[str, Any]) -> Path | None:
    """The home of the run's workflow: the folder of the nearest ``fx.yaml`` at or above its
    file, where its ``./`` paths are found; None when the file is not found again."""

    found = _workflow_file(run_dir, plan)
    if found is None:
        return None
    for folder in (found.parent, *found.parent.parents):
        if (folder / PROJECT_FILE).is_file():
            return folder
    return found.parent


def _kinds(outputs: Mapping[str, Any]) -> set[str]:
    """The kind of every file of every output, and each kind's family."""
    kinds: set[str] = set()
    for value in outputs.values():
        for file in files_of(value):
            kind = str(file["kind"])
            kinds.update((kind, kind.split("/", 1)[0]))
    return kinds


def template_for(setting: Any, outputs: Mapping[str, Any], home: Path | None) -> Path | None:
    """The template a ``view:`` setting names: a path in the home (never outside it, never
    through a symbolic link), or for ``true`` the generic template of the first kind or family
    in :data:`GENERIC_VIEWS` order that any output file has; None for anything else."""

    if setting is True:
        kinds = _kinds(outputs)
        for kind, name in GENERIC_VIEWS.items():
            if kind in kinds:
                return _TEMPLATES / name
        return None
    if isinstance(setting, str) and setting and home is not None:
        root = home.resolve()
        candidate = root / setting
        if relative_within(root, candidate) and candidate.is_file():
            return candidate
    return None


class _Collector:
    """Builds the contexts of one run, collecting the templates and files they name."""

    def __init__(
        self,
        run_dir: Path,
        plan: Mapping[str, Any],
        events: list[dict[str, Any]],
        facts_reader: FactsReader | None,
    ) -> None:
        self.run_dir = run_dir
        self.plan = plan
        self.placed = placed_files(run_dir, events)
        self.facts_reader = facts_reader
        self.views = RunViews()

    def template(self, source: Path) -> str:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        ref = f"views/{digest}.html"
        self.views.templates[ref] = source
        return ref

    def value(self, value: Mapping[str, Any]) -> Any:
        if "file" in value:
            file = value["file"]
            kind, digest = str(file["kind"]), str(file["digest"])
            ref = view_file(digest, kind)
            found: dict[str, Any] = {
                "kind": kind,
                "digest": digest,
                "size": file["size"],
                "key": file.get("key"),
                "ref": ref,
                "facts": {},
            }
            try:
                path = find_file(self.run_dir, digest, self.plan, placed=self.placed)
            except FileNotFoundError:
                return found
            self.views.files[ref] = path
            if self.facts_reader is not None:
                found["facts"] = dict(self.facts_reader(path, kind, digest))
            if kind == "json" and file["size"] <= INLINE_JSON_BYTES:
                found["value"] = json.loads(path.read_text(encoding="utf-8"))
            return found
        if "collection" in value:
            return {key: self.value(item) for key, item in value["collection"]}
        if "list" in value:
            return [self.value(item) for item in value["list"]]
        if value.get("none"):
            return None
        return value.get("value")


def _holds_files(value: Mapping[str, Any]) -> bool:
    if "file" in value:
        return True
    items = [item for _, item in value.get("collection", [])] + list(value.get("list", []))
    return bool(items) and all(_holds_files(item) for item in items)


_SEGMENT = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?:\[(?P<key>'(?:[^'\\]|\\.)*')\])?")


def _path_parts(path: str) -> list[tuple[str, str | None]]:
    """``entity['bellwright'].draw`` as ``[("entity", "bellwright"), ("draw", None)]``."""

    parts: list[tuple[str, str | None]] = []
    position = 0
    while position < len(path):
        match = _SEGMENT.match(path, position)
        if match is None:
            return [(path, None)]
        key = match["key"]
        unquoted = None if key is None else re.sub(r"\\(.)", r"\1", key[1:-1])
        parts.append((match["name"], unquoted))
        position = match.end()
        if position < len(path):
            if path[position] != ".":
                return [(path, None)]
            position += 1
    return parts


def _place_step(tree: dict[str, Any], path: str, entry: dict[str, Any]) -> None:
    """File one step's entry under its groups: a repeat holds ``instances`` by key."""

    node = tree
    parts = _path_parts(path)
    for name, key in parts[:-1]:
        if key is None:
            node = node.setdefault(name, {"steps": {}})["steps"]
            continue
        instances = node.setdefault(name, {"instances": []})["instances"]
        instance = next((i for i in instances if i["key"] == key), None)
        if instance is None:
            instance = {"key": key, "status": "succeeded", "steps": {}}
            instances.append(instance)
        if entry["status"] != "succeeded":
            instance["status"] = entry["status"]
        node = instance["steps"]
    name, key = parts[-1]
    if key is None:
        node[name] = entry
        return
    instances = node.setdefault(name, {"instances": []})["instances"]
    instances[:] = [i for i in instances if i["key"] != key]
    instances.append({"key": key, **entry})


def _workflow_context(
    collector: _Collector,
    events: list[dict[str, Any]],
    run: Mapping[str, Any],
    template: str,
) -> dict[str, Any]:
    """The whole run, as a workflow's own view reads it: every step by name, a repeat's
    instances in the plan's order, and outputs."""

    declared: Mapping[str, Mapping[str, Any]] = collector.plan.get("steps", {})
    order = {
        str(row.get("id")): index
        for index, row in enumerate(collector.plan.get("instances", []))
        if isinstance(row, Mapping)
    }
    started: dict[str, Mapping[str, Any]] = {}
    ended: dict[str, Mapping[str, Any]] = {}
    statuses = {"node_finished": "succeeded", "node_failed": "failed", "node_skipped": "skipped"}
    for event in events:
        name = event.get("event")
        identifier = event.get("id")
        if not isinstance(identifier, str):
            continue
        if name == "node_started":
            started[identifier] = event
        elif name in statuses:
            ended.pop(identifier, None)
            ended[identifier] = event
    tree: dict[str, Any] = {}
    seen = {identifier: index for index, identifier in enumerate(ended)}
    for identifier in sorted(ended, key=lambda i: (order.get(i, len(order)), seen[i])):
        final = ended[identifier]
        start = started.get(identifier, {})
        path = str(final.get("path", identifier))
        step = declared.get(str(start.get("step", "")), {})
        takes = start.get("take") or [1]
        _place_step(
            tree,
            path,
            {
                "path": path,
                "title": step.get("title") or path.rsplit(".", 1)[-1],
                "status": statuses[str(final.get("event"))],
                "take": takes[-1],
                "facts": final.get("facts", {}),
                "outputs": {
                    output: collector.value(value)
                    for output, value in final.get("outputs", {}).items()
                },
            },
        )
    last = ending(events)
    outputs = last.get("outputs", {}) if last and last.get("event") == "run_finished" else {}
    return {
        "kind": VIEW_CONTEXT_KIND,
        "scope": "workflow",
        "node_id": None,
        "template": template,
        "steps": tree,
        "outputs": {name: collector.value(value) for name, value in outputs.items()},
        "run": run,
    }


def view_contexts(run_dir: Path, *, facts_reader: FactsReader | None = file_facts) -> RunViews:
    """Each finished step with a view, as its view reads it (``stage-gen-view-context-v1``),
    then the whole run, when the workflow has a view of its own (``scope: workflow``).

    ``step`` is the step: its path, title, status, take, cost and every resolved ``with``
    value; ``inputs`` are the files among them and ``outputs`` the files it made, each
    ``{kind, digest, size, key, ref, facts}`` (``ref`` is where the view cache keeps it; a host
    adds its ``url``), a small JSON file with its parsed ``value``; ``facts`` are the step's
    facts and ``run`` the run it belongs to.
    """

    plan = read_plan(run_dir)
    events = read_events(run_dir)
    collector = _Collector(run_dir, plan, events, facts_reader)
    home = workflow_home(run_dir, plan)
    steps: Mapping[str, Mapping[str, Any]] = plan.get("steps", {})
    settings = {
        str(instance["id"]): instance.get("view")
        for instance in plan.get("instances", [])
        if isinstance(instance, Mapping) and "id" in instance
    }
    started: dict[str, dict[str, Any]] = {}
    shown: dict[str, dict[str, Any]] = {}
    spent: dict[str, float] = {}
    for event in events:
        identifier = event.get("id")
        if not isinstance(identifier, str):
            continue
        if event.get("event") == "node_started":
            started[identifier] = event
            shown.pop(identifier, None)
        elif event.get("event") == "node_finished":
            shown[identifier] = event
        elif event.get("event") == "call" and isinstance(event.get("cost_usd"), int | float):
            spent[identifier] = spent.get(identifier, 0.0) + float(event["cost_usd"])
    last = ending(events)
    run = {
        "id": run_dir.name,
        "workflow": plan.get("workflow", {}).get("id"),
        "status": run_state(events),
        "cost_usd": last.get("charged_usd") if last else None,
    }
    for identifier, done in shown.items():
        start = started.get(identifier, {})
        declared = steps.get(str(start.get("step", "")), {})
        setting = settings.get(identifier, declared.get("view"))
        outputs = done.get("outputs", {})
        source = template_for(setting, outputs, home)
        if source is None:
            continue
        path = str(done.get("path", identifier))
        given = start.get("with", {})
        collector.views.contexts.append(
            {
                "kind": VIEW_CONTEXT_KIND,
                "scope": "node",
                "node_id": identifier,
                "template": collector.template(source),
                "step": {
                    "path": path,
                    "step": start.get("step"),
                    "title": declared.get("title") or path.rsplit(".", 1)[-1],
                    "status": "succeeded",
                    "take": start.get("take", [1])[-1] if start.get("take") else 1,
                    "cost_usd": round(spent.get(identifier, 0.0), 6),
                    "with": {name: collector.value(value) for name, value in given.items()},
                },
                "inputs": {
                    name: collector.value(value)
                    for name, value in given.items()
                    if _holds_files(value)
                },
                "outputs": {name: collector.value(value) for name, value in outputs.items()},
                "facts": done.get("facts", {}),
                "run": run,
            }
        )
    workflow_file = _workflow_file(run_dir, plan)
    document = _workflow_document(workflow_file) if workflow_file is not None else None
    whole = template_for((document or {}).get("view"), {}, home)
    if whole is not None:
        collector.views.contexts.append(
            _workflow_context(collector, events, run, collector.template(whole))
        )
    return collector.views


__all__ = [
    "GENERIC_VIEWS",
    "INLINE_JSON_BYTES",
    "VIEW_CONTEXT_KIND",
    "RunViews",
    "template_for",
    "view_contexts",
    "view_file",
    "workflow_home",
]
