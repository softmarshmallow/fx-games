"""An FX run, projected for the viewer: ``plan.json`` and ``events.jsonl`` as one run view.

The viewer draws every run from one document (``stage-gen-run-view-v1``). It is a pure
projection of the run folder: the plan the run started from, the record of what happened
(instances a later phase or take added included), and the files the record names. Nothing else
enters it, so a copied run folder projects the same on any machine; reading never writes, and
a record cut short by a crash is read up to its last whole line.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stage_gen.canonical import canonical_sha256
from stage_gen.runview.folder import (
    EVENTS_FILE,
    ending,
    files_of,
    placed_path,
    read_events,
    read_plan,
    route_id,
)
from stage_gen.runview.model import (
    RUN_VIEW_KIND,
    RUN_VIEW_SCHEMA_VERSION,
    CacheDisposition,
    NodeState,
    Resource,
    RetryOwner,
    RunState,
    RunView,
    RunViewArtifact,
    RunViewNode,
    ViewArchetype,
    artifact_media_type,
)

_DISPLAYS = (("image/", "image"), ("audio/", "audio"), ("video/", "video"), ("text/", "text"))
_ARCHETYPES = {
    "image": ViewArchetype.IMAGE,
    "structured": ViewArchetype.STRUCTURED,
    "vision": ViewArchetype.JUDGE,
    "video": ViewArchetype.VIDEO,
    "music": ViewArchetype.MUSIC,
    "sound": ViewArchetype.SOUND,
}
_FINISHED = frozenset({"node_finished", "node_failed", "node_skipped"})


def run_state(events: list[dict[str, Any]]) -> RunState:
    state: RunState = "planned"
    for event in events:
        name = event.get("event")
        if name == "run_started":
            state = "unfinished"
        elif name == "run_finished":
            state = "succeeded" if event.get("ok") else "failed"
        elif name == "run_cancelled":
            state = "canceled"
    return state


def _resource(route: str | None) -> str:
    if route is None:
        return "local"
    text = "".join(c if c.isalnum() else "." for c in route.lower())
    return ".".join(part for part in text.split(".") if part) or "route"


def _media_type(kind: str, artifact_ref: str) -> str:
    if "/" in kind:
        return kind
    return artifact_media_type(artifact_ref)


def _display(media_type: str) -> str:
    for prefix, display in _DISPLAYS:
        if media_type.startswith(prefix):
            return display
    return "data"


def _artifacts(
    run_dir: Path, identifier: str, path: str, outputs: Mapping[str, Any]
) -> list[RunViewArtifact]:
    artifacts: list[RunViewArtifact] = []
    for port, value in outputs.items():
        files = files_of(value)
        for index, file in enumerate(files):
            ref = placed_path(identifier, path, port, file, index, len(files))
            media_type = _media_type(str(file["kind"]), ref)
            artifacts.append(
                RunViewArtifact(
                    artifact_ref=ref,
                    sha256=file["digest"],
                    bytes=file["size"],
                    media_type=media_type,
                    present=(run_dir / ref).is_file(),
                    display=_display(media_type),
                )
            )
    return artifacts


def _archetype(entry: Mapping[str, Any]) -> ViewArchetype:
    if entry.get("judges"):
        return ViewArchetype.JUDGE
    for capability in entry.get("routes", {}):
        found = _ARCHETYPES.get(str(capability).split(".", 1)[0])
        if found is not None:
            return found
    return ViewArchetype.TRANSFORM


def project_run(run_dir: Path) -> RunView:
    """The run's view: every instance the plan or the record names, in that order."""

    plan = read_plan(run_dir)
    events = read_events(run_dir)
    state_of_run = run_state(events)
    ended = state_of_run in {"succeeded", "failed", "canceled"}
    steps: Mapping[str, Mapping[str, Any]] = plan.get("steps", {})
    workflow_id = str(plan.get("workflow", {}).get("id", "workflow"))

    entries: dict[str, dict[str, Any]] = {}
    for instance in plan.get("instances", []):
        if instance.get("state") != "absent":
            entries[instance["id"]] = dict(instance)
    last: dict[str, dict[str, Any]] = {}
    calls: dict[str, list[dict[str, Any]]] = {}
    invocation_id: str | None = None
    for event in events:
        name = event.get("event")
        if name == "run_started":
            invocation_id = event.get("invocation_id")
        identifier = event.get("id")
        if not isinstance(identifier, str):
            continue
        if name == "node_started":
            entry = entries.setdefault(identifier, {"id": identifier})
            for field in ("path", "step", "uses", "take", "identity", "reads", "routes"):
                if field in event:
                    entry[field] = event[field]
            last[identifier] = event
        elif name in _FINISHED:
            last[identifier] = event
        elif name == "call":
            calls.setdefault(identifier, []).append(event)

    nodes: list[RunViewNode] = []
    resources: dict[str, Resource] = {}
    for identifier, entry in entries.items():
        routes = {
            str(capability): found
            for capability, value in dict(entry.get("routes", {})).items()
            if (found := route_id(value)) is not None
        }
        route = next(iter(routes.values()), None)
        model, _, provider = (route or "").rpartition("@")
        resource_id = _resource(route)
        resources.setdefault(
            resource_id, Resource(resource_id=resource_id, rate_limit_owner="none")
        )
        final: Mapping[str, Any] = last.get(identifier) or {}
        name = final.get("event")
        state: NodeState
        error: str | None = None
        if name == "node_finished":
            state = "succeeded"
        elif name in {"node_failed", "node_skipped"}:
            state = "failed" if name == "node_failed" else "skipped"
            error = final.get("error") or final.get("reason")
        elif name == "node_started":
            state = "failed" if ended else "running"
            error = "the run ended before this step finished" if ended else None
        elif entry.get("state") == "done":
            state = "succeeded"
        else:
            state = "skipped" if ended else "pending"
            error = entry.get("reason")
        terminal = name in _FINISHED
        made = [call for call in calls.get(identifier, []) if not call.get("cached")]
        costs = [call.get("cost_usd") for call in made]
        known_cost = (
            round(sum(float(cost) for cost in costs if cost is not None), 6)
            if route is not None and all(cost is not None for cost in costs)
            else None
        )
        step = steps.get(str(entry.get("step", "")), {})
        path = str(entry.get("path", identifier))
        price = entry.get("price", {})
        identity = entry.get("identity")
        cache = final.get("cache") if name == "node_finished" else None
        nodes.append(
            RunViewNode(
                node_id=identifier,
                type_id=str(entry.get("uses", "")),
                title=step.get("title") or path.rsplit(".", 1)[-1],
                archetype=_archetype(entry),
                domain=workflow_id,
                description=step.get("description") or f"{entry.get('uses', 'step')} at {path}",
                depends_on=tuple(dep for dep in entry.get("reads", []) if dep in entries),
                operation="local" if route is None else next(iter(routes)),
                resource_id=resource_id,
                provider=provider or None,
                model=model or None,
                retry_owner=RetryOwner.NONE if route is None else RetryOwner.COMPONENT,
                max_attempts=1 if route is None else 6,
                cache_key=identity
                if isinstance(identity, str) and len(identity) == 64
                else hashlib.sha256(identifier.encode()).hexdigest(),
                estimated_duration_seconds=0.0,
                estimated_cost_low_usd=float(price.get("low_usd", 0.0)),
                estimated_cost_high_usd=float(price.get("high_usd", 0.0)),
                state=state,
                ended_offset_ms=final.get("offset_ms") if terminal else None,
                duration_ms=final.get("duration_ms") if terminal else None,
                cache=CacheDisposition(cache) if cache in {"hit", "miss"} else None,
                provider_operations=len(made) if route is not None else None,
                known_cost_usd=known_cost,
                error=str(error)[:2_000] if error else None,
                artifacts=tuple(_artifacts(run_dir, identifier, path, final.get("outputs", {})))
                if name == "node_finished"
                else (),
            )
        )

    last_ending = ending(events)
    log = run_dir / EVENTS_FILE
    return RunView(
        schema_version=RUN_VIEW_SCHEMA_VERSION,
        kind=RUN_VIEW_KIND,
        graph_sha256=str(plan.get("plan") or canonical_sha256(plan)),
        topology_sha256=canonical_sha256(
            sorted([node.node_id, sorted(node.depends_on)] for node in nodes)
        ),
        invocation_id=invocation_id,
        run_state=state_of_run,
        trace_modified_at=datetime.fromtimestamp(log.stat().st_mtime, UTC).isoformat()
        if log.is_file()
        else None,
        duration_ms=last_ending.get("offset_ms") if last_ending else None,
        known_cost_usd=last_ending.get("charged_usd") if last_ending else None,
        state_counts=dict(sorted(Counter(node.state for node in nodes).items())),
        resources=tuple(sorted(resources.values(), key=lambda r: r.resource_id)),
        nodes=tuple(nodes),
    )


def verify_run(run_dir: Path) -> list[str]:
    """Every step file the record names, checked in the run folder against its digest."""

    problems: list[str] = []
    for node in project_run(run_dir).nodes:
        for artifact in node.artifacts:
            path = run_dir / artifact.artifact_ref
            if not path.is_file():
                problems.append(f"{node.node_id}: {artifact.artifact_ref} is missing")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
                problems.append(
                    f"{node.node_id}: {artifact.artifact_ref} differs from its recorded digest"
                )
    return problems


__all__ = ["project_run", "run_state", "verify_run"]
