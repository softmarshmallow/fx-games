"""A workflow written as an FX workflow file, as the catalog, the checks and the runs see it.

The folder holds ``workflow.yaml`` beside its own ``fx.yaml``. Every fact the catalog needs is
read from that file by :func:`describe`, without planning it: each leaf step is one catalog
type (``<folder>/<step path>``) titled by its ``title:``, whose contract version is the type
identity FX resolves its ``uses`` to; each top-level step is one reader step. The sample plan
is FX's plan of the committed sample inputs (``fx-graph-v1``), and a run is an FX run folder,
projected from the folder alone by :mod:`fx_games.runview`.

:func:`write_project` writes every scratch project FX Games' code and tests plan in, so the
first-party workflows are found by id from anywhere.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any, Final

import yaml
from grida.fx import Plan, Workflow, plan, spec_of

from fx_games.runview.folder import (
    FX_GRAPH_KIND,
    PROJECT_FILE,
    is_fx_run,
    project_file,
    read_plan,
    suffix_of_kind,
)

from ._registry import Identity, NodeType, Step, WorkflowCode, node_type_inventory

WORKFLOW_FILE: Final = "workflow.yaml"
#: The folder every first-party workflow home sits in.
WORKFLOWS_ROOT: Final[Path] = Path(__file__).resolve().parent

PROJECT_HEADER = "project/v1"
WORKFLOW_HEADER = "workflow/v1"
_OUTPUT_REF = re.compile(r"steps\.(?P<step>[A-Za-z0-9_.*\[\]'\"-]+?)\.outputs\.(?P<port>\w+)")
_BUILDER = re.compile(r"^(?P<file>.+\.py):(?P<function>[A-Za-z_][A-Za-z0-9_]*)$")
#: One port line of ``python -m grida.fx nodes <type>``: ``output  image: image/png``.
_NODES_PORT = re.compile(r"^\s*output\s+(?P<name>\w+):\s*(?P<notation>\S+)\s*$")


# ---------------------------------------------------------------- project files


def write_project(
    folder: Path,
    *,
    runs: str | None = None,
    cache: str | None = None,
    routes: Mapping[str, str] | None = None,
    route_tables: Sequence[Path] = (),
    workflows: Sequence[Path] = (WORKFLOWS_ROOT,),
) -> Path:
    """Write ``folder/fx.yaml`` and return ``folder``, to plan and run in (as ``cwd``).

    ``workflows`` are the folders FX finds workflows by id in, as absolute paths: the
    first-party workflows by default. ``runs``, ``cache``, ``routes`` and ``route_tables`` are
    written only when given. Paths are JSON-quoted, which FX's YAML reads as strings.
    """

    folder.mkdir(parents=True, exist_ok=True)
    lines = [f"fx: {PROJECT_HEADER}"]
    if workflows:
        listed = ", ".join(json.dumps(str(Path(entry).resolve())) for entry in workflows)
        lines.append(f"workflows: [{listed}]")
    if runs is not None:
        lines.append(f"runs: {json.dumps(runs)}")
    if cache is not None:
        lines.append(f"cache: {json.dumps(cache)}")
    if routes:
        lines.append("routes:")
        lines += [f"  {capability}: {json.dumps(route)}" for capability, route in routes.items()]
    if route_tables:
        listed = ", ".join(json.dumps(str(Path(table).resolve())) for table in route_tables)
        lines.append(f"route_tables: [{listed}]")
    (folder / PROJECT_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def _workflow_header(document: Any) -> bool:
    return isinstance(document, dict) and document.get("fx") == WORKFLOW_HEADER


def workflow_file(workflow_id: str) -> Path:
    """The first-party workflow file that declares ``workflow_id``: a ``*.yaml`` directly in a
    home folder under :data:`WORKFLOWS_ROOT` whose header is ``fx: workflow/v1``."""

    for home in sorted(WORKFLOWS_ROOT.iterdir()):
        if not home.is_dir() or home.name[0] in "_.":
            continue
        for candidate in sorted(home.glob("*.yaml")):
            if candidate.name == PROJECT_FILE or ".takes." in candidate.name:
                continue
            document = _read_yaml(candidate)
            if _workflow_header(document) and document.get("id") == workflow_id:
                return candidate
    raise ValueError(f"no first-party workflow has the id {workflow_id!r}")


# ---------------------------------------------------------------- plans


@dataclass(frozen=True, slots=True)
class RouteRef:
    """The route a planned instance binds to one capability."""

    route: str
    fingerprint: str
    model: str
    provider: str


@dataclass(frozen=True, slots=True)
class Instance:
    """One ``instances[]`` row of an ``fx-graph-v1`` plan."""

    id: str
    path: str
    step: str
    takes: tuple[int, ...]
    take: int
    uses: str
    type_identity: str | None
    with_: Mapping[str, Any]
    routes: Mapping[str, RouteRef]
    state: str
    identity: Any
    phase: int
    key: str | None
    judges: str | None
    judged_by: tuple[str, ...]
    needs: tuple[str, ...]
    reads: tuple[str, ...]
    waiting_on: tuple[str, ...]
    low_usd: float
    high_usd: float

    @property
    def inputs_from(self) -> tuple[str, ...]:
        """Every instance it reads, waits on or needs: its upstream in the graph."""
        return tuple(sorted({*self.reads, *self.waiting_on, *self.needs} - {self.id}))

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> Instance:
        takes = tuple(int(take) for take in row["take"])
        routes = {}
        for capability, bound in (row.get("routes") or {}).items():
            model, _, provider = str(bound["route"]).rpartition("@")
            routes[capability] = RouteRef(
                route=str(bound["route"]),
                fingerprint=str(bound["fingerprint"]),
                model=model,
                provider=provider,
            )
        price = row.get("price") or {}
        return cls(
            id=str(row["id"]),
            path=str(row["path"]),
            step=str(row["step"]),
            takes=takes,
            take=takes[-1],
            uses=str(row["uses"]),
            type_identity=row.get("type"),
            with_=dict(row.get("with") or {}),
            routes=routes,
            state=str(row["state"]),
            identity=row.get("identity"),
            phase=int(row.get("phase", 1)),
            key=row.get("key"),
            judges=row.get("judges"),
            judged_by=tuple(row.get("judged_by") or ()),
            needs=tuple(row.get("needs") or ()),
            reads=tuple(row.get("reads") or ()),
            waiting_on=tuple(row.get("waiting_on") or ()),
            low_usd=float(price.get("low_usd", 0.0)),
            high_usd=float(price.get("high_usd", 0.0)),
        )


def _document(planned: Plan | Mapping[str, Any]) -> Mapping[str, Any]:
    return planned.document if isinstance(planned, Plan) else planned


def instances(planned: Plan | Mapping[str, Any]) -> tuple[Instance, ...]:
    """Every instance of a plan, or of its ``document``."""
    return tuple(Instance.from_row(row) for row in _document(planned).get("instances") or ())


def first_takes(planned: Plan | Mapping[str, Any]) -> tuple[Instance, ...]:
    """The instances a first run makes: present, and on their first take at every level."""
    return tuple(
        instance
        for instance in instances(planned)
        if instance.state != "absent" and all(take == 1 for take in instance.takes)
    )


# ---------------------------------------------------------------- describing a workflow


@dataclass(frozen=True, slots=True)
class StepDescription:
    """One leaf step: a node type used once in the workflow (however often it repeats)."""

    path: str
    #: The top-level step it belongs to (itself when it is one).
    group: str
    title: str | None
    description: str | None
    uses: str
    #: What the step's type is called by identity: ``<file>#<name>@<version>`` for a project
    #: type, ``fx/<name>@<major>.<version>`` for a built-in (FX ``spec/identity.md`` section
    #: 6), so a minor bump of a built-in moves it as it moves every key that uses it.
    type_identity: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkflowDescription:
    id: str
    path: Path
    #: Top-level step name -> (title, description), in file order.
    groups: dict[str, tuple[str | None, str | None]]
    steps: tuple[StepDescription, ...]
    #: Declared output name -> where it lands in a run folder (``outputs/...``).
    outputs: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Resolved:
    identity: str
    capabilities: tuple[str, ...]
    #: Output port name -> (kind, shape).
    outputs: Mapping[str, tuple[str, str]]


@cache
def _builtin_classes() -> dict[str, str]:
    """``free``, ``paid`` or ``judge`` for each built-in, as ``python -m grida.fx nodes`` lists."""
    listed = _fx_text("nodes")
    classes = {}
    for line in listed.splitlines():
        words = line.split()
        if len(words) == 2:
            classes[words[0]] = words[1]
    return classes


@cache
def _builtin_outputs(uses: str) -> dict[str, tuple[str, str]]:
    """A built-in's output ports, read from ``python -m grida.fx nodes <uses>``."""
    ports = {}
    for line in _fx_text("nodes", uses).splitlines():
        match = _NODES_PORT.match(line)
        if match is None:
            continue
        notation = match["notation"].rstrip("?")
        shape = "list" if notation.endswith("[]") else "keyed" if notation.endswith("{}") else "one"
        ports[match["name"]] = (notation.rstrip("[]{}"), shape)
    return ports


@cache
def _builtin_identities() -> dict[str, str]:
    """Each built-in's type identity, ``fx/<name>@<major>.<version>``, as FX resolves it.

    ``python -m grida.fx nodes`` lists ``uses`` names only, so this expands a probe workflow
    with one bare step per built-in: the expansion carries ``types`` (FX ``spec/identity.md``
    section 6) though the bare steps have problems. Offline; it reads no ``.env``.
    """

    listed = sorted(_builtin_classes())
    steps = "".join(f"  s{index}:\n    uses: {uses}\n" for index, uses in enumerate(listed))
    with tempfile.TemporaryDirectory(prefix="fx-games-fx-types-") as folder:
        probe = Path(folder) / "types.yaml"
        probe.write_text(
            f"fx: {WORKFLOW_HEADER}\nid: types\ntitle: Types\nsteps:\n{steps}", encoding="utf-8"
        )
        done = subprocess.run(
            [sys.executable, "-m", "grida.fx", "expand", probe.name],
            capture_output=True,
            text=True,
            check=False,
            cwd=folder,
            env={**os.environ, "GRIDA_FX_DISABLE_DOTENV": "1", "GRIDA_FX_NETWORK": "off"},
        )
    try:
        types = json.loads(done.stdout)["types"]
    except (ValueError, KeyError, TypeError):
        raise ValueError(f"python -m grida.fx expand: {done.stderr.strip()}") from None
    identities = {uses: str((types.get(uses) or {}).get("identity") or "") for uses in listed}
    unknown = sorted(uses for uses, identity in identities.items() if not identity)
    if unknown:
        raise ValueError(f"FX resolved no identity for {', '.join(unknown)}")
    return identities


def _fx_text(*arguments: str) -> str:
    done = subprocess.run(
        [sys.executable, "-m", "grida.fx", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise ValueError(f"python -m grida.fx {' '.join(arguments)}: {done.stderr.strip()}")
    return done.stdout


@contextmanager
def _inside(root: Path, cwd: Path | None = None) -> Iterator[None]:
    """``root`` first on ``sys.path`` (and ``cwd`` the working directory), as FX's node host
    has them while it loads a project module."""
    previous_path = list(sys.path)
    previous_cwd = Path.cwd()
    sys.path.insert(0, str(root))
    if cwd is not None:
        os.chdir(cwd)
    try:
        yield
    finally:
        sys.path[:] = previous_path
        if cwd is not None:
            os.chdir(previous_cwd)


_MODULES: dict[Path, ModuleType] = {}


def _project_module(root: Path, file: Path) -> ModuleType:
    """A project module loaded the way FX's node host loads it, once per file."""
    file = file.resolve()
    if file in _MODULES:
        return _MODULES[file]
    relative = file.relative_to(root).as_posix()
    name = "_fx_games_fx_" + hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(name, file)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with _inside(root):
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    _MODULES[file] = module
    return module


def _resolve(uses: str, home: Path) -> _Resolved:
    """A step's type, read without planning: a project type from its module, a built-in from
    ``python -m grida.fx nodes``."""

    if uses.startswith("fx/"):
        kind = _builtin_classes().get(uses)
        if kind is None:
            raise ValueError(f"{uses} is not a built-in FX knows")
        capability = uses.removeprefix("fx/").rsplit("@", 1)[0]
        return _Resolved(
            identity=_builtin_identities()[uses],
            capabilities=(capability,) if kind == "paid" else (),
            outputs=_builtin_outputs(uses),
        )
    reference, _, attribute = uses.partition("#")
    file = (home / reference).resolve()
    module = _project_module(home, file)
    spec = spec_of(getattr(module, attribute, None))
    if spec is None:
        raise ValueError(f"{uses} names no node type")
    if spec.version is None:
        raise ValueError(f"{uses} has no version; every first-party node type is versioned")
    return _Resolved(
        identity=f"{file.relative_to(home).as_posix()}#{attribute}@{spec.version}",
        capabilities=tuple(sorted(spec.calls)),
        outputs={name: (port.kind, port.shape) for name, port in spec.outputs.items()},
    )


def _leaves(steps: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Mapping[str, Any]]]:
    for name, step in steps.items():
        path = f"{prefix}{name}"
        if isinstance(step.get("steps"), Mapping):
            yield from _leaves(step["steps"], f"{path}.")
        else:
            yield path, step


def _landing(name: str, expression: Any, resolved: Mapping[str, _Resolved]) -> str:
    """Where a declared output lands in a run folder (FX ``spec/store.md`` section 8)."""
    match = _OUTPUT_REF.search(str(expression))
    found = None if match is None else resolved.get(match["step"])
    port = None if found is None or match is None else found.outputs.get(match["port"])
    if port is None or port[1] != "one":
        return f"outputs/{name}/"
    return f"outputs/{name}{suffix_of_kind(port[0])}"


def _target(target: str | Path, cwd: Path) -> tuple[Path, Path, Mapping[str, Any]]:
    """``(workflow file, home, document)`` of a workflow file, a first-party id, or a builder
    ``<file>.py:<function>`` (built with no arguments)."""

    text = os.fspath(target)
    builder = _BUILDER.match(text)
    if builder is not None:
        project = project_file(cwd)
        home = cwd if project is None else project.parent
        built = _build(cwd / builder["file"], builder["function"], home, cwd, {})
        return cwd / builder["file"], home, built.document()
    is_file = Path(text).suffix in (".yaml", ".yml")
    path = (cwd / text).resolve() if is_file else workflow_file(text)
    project = project_file(path)
    home = path.parent if project is None else project.parent
    document = _read_yaml(path)
    if not _workflow_header(document):
        raise ValueError(f"{path} is not an FX workflow file (fx: {WORKFLOW_HEADER})")
    return path, home, document


def describe(target: str | Path, *, cwd: Path | None = None) -> WorkflowDescription:
    """A workflow's steps, types and outputs, read without inputs, routes or prices."""

    path, home, document = _target(target, (cwd or Path.cwd()).resolve())
    declared: Mapping[str, Any] = document.get("steps") or {}
    resolved: dict[str, _Resolved] = {}
    steps = []
    for top, step in declared.items():
        for leaf, body in _leaves({top: step}):
            uses = str(body.get("uses") or "")
            found = resolved[leaf] = _resolve(uses, home)
            steps.append(
                StepDescription(
                    path=leaf,
                    group=top,
                    title=body.get("title"),
                    description=body.get("description"),
                    uses=uses,
                    type_identity=found.identity,
                    capabilities=found.capabilities,
                )
            )
    return WorkflowDescription(
        id=str(document["id"]),
        path=path,
        groups={
            name: (step.get("title"), step.get("description")) for name, step in declared.items()
        },
        steps=tuple(steps),
        outputs={
            name: _landing(name, expression, resolved)
            for name, expression in (document.get("outputs") or {}).items()
        },
    )


def _build(
    file: Path, function: str, root: Path, cwd: Path, arguments: Mapping[str, str]
) -> Workflow:
    """Run a builder in this process the way FX's node host runs it: the project root first on
    ``sys.path``, the module and the builder in ``cwd``."""
    with _inside(root, cwd):
        module = _project_module(root, file)
        builder = getattr(module, function, None)
        if not callable(builder):
            raise ValueError(f"{file.name} has no function {function}")
        built = builder(**arguments)
    if not isinstance(built, Workflow):
        raise TypeError(f"{function} returned {type(built).__name__}, not a grida.fx.Workflow")
    return built


def declared_outputs(
    target: str | Path, *, cwd: Path, arguments: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The workflow's declared outputs, name -> expression: read from a workflow file or a
    first-party id, or from what a builder ``<file>.py:<function>`` returns for ``arguments``
    in ``cwd``."""

    cwd = cwd.resolve()
    builder = _BUILDER.match(os.fspath(target))
    if builder is None:
        _, _, document = _target(target, cwd)
    else:
        project = project_file(cwd)
        root = cwd if project is None else project.parent
        built = _build(cwd / builder["file"], builder["function"], root, cwd, arguments or {})
        document = built.document()
    return {str(name): str(value) for name, value in (document.get("outputs") or {}).items()}


# ---------------------------------------------------------------- the catalog's view


@dataclass(frozen=True, slots=True)
class SampleNode:
    """One planned instance, in the shape the catalog draws a sample plan from."""

    node_id: str
    type_id: str
    operation: str
    provider: str | None
    model: str | None
    depends_on: tuple[str, ...]
    ports: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class SamplePlan:
    """The plan of a workflow's sample inputs: its instances, and where its outputs land."""

    kind: str
    topology_sha256: str
    nodes: tuple[SampleNode, ...]
    artifact_refs: frozenset[str] = field(default_factory=frozenset)


def _operation(capabilities: Sequence[str]) -> str:
    return capabilities[0].replace(".", "_") if capabilities else "local"


def _node_type(folder: str, step: StepDescription) -> NodeType:
    return NodeType(
        type_id=f"{folder}/{step.path.replace('.', '/')}",
        title=step.title or step.path.rsplit(".", 1)[-1],
        operation=_operation(step.capabilities),
        contract_version=step.type_identity,
    )


@dataclass(frozen=True, slots=True)
class FxWorkflow:
    """One folder's workflow file, described once, with a catalog type per leaf step."""

    folder: str
    root: Path
    description: WorkflowDescription
    types: dict[str, NodeType]

    @classmethod
    def read(cls, package: str) -> FxWorkflow:
        root = Path(str(resources.files(package)))
        description = describe(root / WORKFLOW_FILE)
        folder = package.rsplit(".", 1)[-1]
        types = {step.path: _node_type(folder, step) for step in description.steps}
        return cls(folder, root, description, types)

    def steps(self) -> tuple[Step, ...]:
        """Each top-level step, titled for readers, with the types of its leaf steps."""

        return tuple(
            Step(
                title or name,
                note or "",
                tuple(
                    self.types[step.path] for step in self.description.steps if step.group == name
                ),
            )
            for name, (title, note) in self.description.groups.items()
        )

    def owns_run(self, run_dir: Path) -> bool:
        if not is_fx_run(run_dir):
            return False
        return bool(read_plan(run_dir).get("workflow", {}).get("id") == self.description.id)

    def sample_plan(self, scratch: Path, inputs: Path) -> SamplePlan:
        """FX's plan of the sample inputs, made in a scratch project at ``scratch``."""

        write_project(scratch)
        planned = plan(self.description.id, input_files=[inputs], cwd=scratch)
        if not planned.ok:
            problems = "; ".join(f"{p['where']}: {p['message']}" for p in planned.problems)
            raise ValueError(f"{self.description.id}: the sample does not plan: {problems}")
        live = [i for i in instances(planned) if i.state in {"planned", "maybe", "done"}]
        ids = {instance.id for instance in live}
        nodes = []
        for instance in live:
            route = next(iter(instance.routes.values()), None)
            nodes.append(
                SampleNode(
                    node_id=instance.id,
                    type_id=self.types[instance.step].type_id,
                    operation=_operation(sorted(instance.routes)),
                    provider=None if route is None else route.provider,
                    model=None if route is None else route.model,
                    depends_on=tuple(dep for dep in instance.inputs_from if dep in ids),
                )
            )
        topology = json.dumps(
            sorted([node.node_id, list(node.depends_on)] for node in nodes), separators=(",", ":")
        )
        return SamplePlan(
            kind=FX_GRAPH_KIND,
            topology_sha256=hashlib.sha256(topology.encode()).hexdigest(),
            nodes=tuple(nodes),
            artifact_refs=frozenset(self.description.outputs.values()),
        )


def fx_workflow(
    package: str,
    *,
    make_inputs: str | None = None,
    sample_inputs: str | None = None,
    no_sample_plan: str | None = None,
    import_example: Callable[..., Any] | None = None,
    no_importer: str | None = None,
    read_library: Callable[..., Any] | None = None,
) -> WorkflowCode:
    """The ``CODE`` of a workflow folder written as ``workflow.yaml``.

    The sample plan is FX's plan of the sample: ``make_inputs`` is the folder-relative script
    whose ``write_inputs(target)`` draws one and returns its inputs file, and
    ``sample_inputs`` a committed inputs file instead.
    """

    if make_inputs is not None and sample_inputs is not None:
        raise ValueError("a sample is drawn by make_inputs or committed as sample_inputs")
    workflow = FxWorkflow.read(package)

    def identity() -> Identity:
        return {
            "node_types": node_type_inventory(workflow.types.values()),
        }

    def sample_plan(scratch: Path) -> SamplePlan | None:
        if make_inputs is not None:
            written = runpy.run_path(str(workflow.root / make_inputs))["write_inputs"]
            return workflow.sample_plan(scratch, Path(written(scratch / "inputs")))
        if sample_inputs is not None:
            return workflow.sample_plan(scratch, workflow.root / sample_inputs)
        return None

    return WorkflowCode(
        steps=workflow.steps(),
        identity=identity,
        implemented_types=lambda: frozenset(t.type_id for t in workflow.types.values()),
        sample_plan=sample_plan,
        owns_run=workflow.owns_run,
        no_sample_plan=no_sample_plan,
        import_example=import_example,
        no_importer=no_importer,
        read_library=read_library,
    )


__all__ = [
    "WORKFLOWS_ROOT",
    "WORKFLOW_FILE",
    "FxWorkflow",
    "Instance",
    "RouteRef",
    "SampleNode",
    "SamplePlan",
    "StepDescription",
    "WorkflowDescription",
    "declared_outputs",
    "describe",
    "first_takes",
    "fx_workflow",
    "instances",
    "workflow_file",
    "write_project",
]
