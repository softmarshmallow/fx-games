from __future__ import annotations

import ast
import importlib
import re
from importlib.util import resolve_name
from pathlib import Path

# test-owner: product
SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
GAME_SOURCE_ROOTS = (
    SOURCE_ROOT.parent / "godot/games/_shared/python/src",
    SOURCE_ROOT.parent / "godot/tools/python/src",
    *(
        SOURCE_ROOT.parent / f"godot/games/{game}/pipeline/src"
        for game in ("bellweather", "iron_petal_unit", "ember_hollow", "the_grain")
    ),
)
GAME_MODULES = (
    "demo_game_tools",
    "demo_game_collection",
    "bellweather_pipeline",
    "iron_petal_unit_pipeline",
    "ember_hollow_pipeline",
    "the_grain_pipeline",
)
COMPONENT_ROOT = SOURCE_ROOT / "stage_gen" / "components"
FORBIDDEN_COMPONENT_DEPENDENCIES = ("stage_gen.workflows",)


def _package_for(path: Path) -> str:
    root = next(
        root
        for root in (SOURCE_ROOT, *GAME_SOURCE_ROOTS, SOURCE_ROOT.parent)
        if path.is_relative_to(root)
    )
    parts = path.relative_to(root).with_suffix("").parts
    if parts[-1] == "__init__":
        return ".".join(parts[:-1])
    return ".".join(parts[:-1])


def _imported_modules(node: ast.Import | ast.ImportFrom, package: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    base = node.module or ""
    if node.level:
        base = resolve_name(f"{'.' * node.level}{base}", package)
    candidates = [base] if base else []
    candidates.extend(f"{base}.{alias.name}" for alias in node.names if base and alias.name != "*")
    return tuple(candidates)


def test_components_do_not_import_application_or_provider_layers() -> None:
    violations: list[str] = []
    for path in _python_sources(COMPONENT_ROOT):
        package = _package_for(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for imported in _imported_modules(node, package):
                if any(
                    imported == forbidden or imported.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_COMPONENT_DEPENDENCIES
                ):
                    relative = path.relative_to(SOURCE_ROOT.parent)
                    violations.append(f"{relative}:{node.lineno} imports {imported}")
    assert not violations, "component import boundary violations:\n" + "\n".join(violations)


WORKFLOW_ROOT = SOURCE_ROOT / "stage_gen" / "workflows"

_ACTIVE_IMAGE_MODEL_ID = re.compile(r"^(?:(?:openai|fal-ai)/)?gpt-image-[0-9][A-Za-z0-9._/-]*$")


def test_active_image_routes_have_one_application_authority() -> None:
    """Image routes live in fx.yaml; no Python names an image model.

    A route is bound by a project file's ``routes:``, so a same-spec promotion is one line
    there and never a source sweep. Historical prose and fixture data live outside these
    production Python roots.
    """

    violations: list[str] = []
    for path in _python_sources(SOURCE_ROOT / "stage_gen"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative = path.relative_to(SOURCE_ROOT.parent)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and _ACTIVE_IMAGE_MODEL_ID.fullmatch(node.value)
            ):
                violations.append(
                    f"{relative}:{node.lineno} owns active image model {node.value!r}"
                )
    assert not violations, "a Python source names an image model:\n" + "\n".join(violations)


def _module_of(root: Path) -> str:
    return ".".join(root.relative_to(SOURCE_ROOT).parts)


def _workflow_roots() -> dict[str, tuple[Path, ...]]:
    """Each workflow's own source root: its package."""

    return {
        entry.name: (entry,)
        for entry in sorted(WORKFLOW_ROOT.iterdir())
        if entry.is_dir() and entry.name[0] not in "_."
    }


#: The registry's declarations (Step, WorkflowCode, run readers) every workflow states
#: itself with. It is not a workflow, and it imports none.
WORKFLOW_DECLARATIONS = "stage_gen.workflows._registry"
#: How a workflow written as a workflow file declares itself to the registry.
WORKFLOW_FILE_DECLARATIONS = "stage_gen.workflows._fx"
#: Modules at the workflows root that read every workflow; they load one only on demand,
#: through ``load_code``, and import none statically.
WORKFLOW_REGISTRY_MODULES = ("_registry.py", "_catalog.py", "_checks.py", "_fx.py")


def test_workflows_do_not_import_each_other() -> None:
    """Workflows share code through declared homes (canonical, media, components, the
    example contract in stage_gen.examples), never through another workflow's modules. A
    workflow imports only its own package and the registry's declarations."""

    workflows = _workflow_roots()
    assert len(workflows) >= 5, f"expected at least 5 workflow packages, found {sorted(workflows)}"
    violations: list[str] = []
    for name, roots in workflows.items():
        own = (
            f"stage_gen.workflows.{name}",
            *(_module_of(root) for root in roots),
            WORKFLOW_DECLARATIONS,
            WORKFLOW_FILE_DECLARATIONS,
        )
        for root in roots:
            for path in _python_sources(root):
                violations.extend(
                    violation
                    for violation, imported in _import_violation_pairs(
                        path, ("stage_gen.workflows",)
                    )
                    if not any(_matches(imported, allowed) for allowed in own)
                )
    assert not violations, "workflow-to-workflow import violations:\n" + "\n".join(violations)


def test_registry_and_example_contract_import_no_workflow() -> None:
    """The registry reads workflows lazily, and the public example contract knows none."""

    paths = [WORKFLOW_ROOT / name for name in WORKFLOW_REGISTRY_MODULES]
    paths.append(SOURCE_ROOT / "stage_gen" / "examples.py")
    missing = sorted(str(path.relative_to(SOURCE_ROOT)) for path in paths if not path.is_file())
    assert not missing, f"registry modules moved; update this rule: {missing}"
    violations = [
        violation
        for path in paths
        for violation, imported in _import_violation_pairs(path, ("stage_gen.workflows",))
        if not _matches(imported, WORKFLOW_DECLARATIONS)
        and not imported.startswith("stage_gen.workflows._")
    ]
    assert not violations, "a registry module imports a workflow:\n" + "\n".join(violations)


def _import_violation_pairs(path: Path, forbidden: tuple[str, ...]) -> list[tuple[str, str]]:
    package = _package_for(path)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for imported in _imported_modules(node, package):
            if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in forbidden):
                violations.append(
                    (
                        f"{path.relative_to(SOURCE_ROOT.parent)}:{node.lineno} imports {imported}",
                        imported,
                    )
                )
    return violations


def _import_violations(path: Path, forbidden: tuple[str, ...]) -> list[str]:
    return [violation for violation, _ in _import_violation_pairs(path, forbidden)]


CONSUMER_ROOTS = (
    SOURCE_ROOT / "stage_gen",
    SOURCE_ROOT.parent / "tests",
    SOURCE_ROOT.parent / "scripts",
    *GAME_SOURCE_ROOTS,
)


def _python_sources(root: Path) -> list[Path]:
    """Every scan must match at least one file, or a moved root would pass vacuously."""

    sources = sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    assert sources, f"{root.relative_to(SOURCE_ROOT.parent)} matched no Python source"
    return sources


APPLICATION_UTILITY_MODULES = ("contracts", "fs", "provenance", "canonical", "media")


def test_application_utilities_import_no_engine() -> None:
    """Stage Gen's own utilities are engine-free, so none of them may import FX."""

    root = SOURCE_ROOT / "stage_gen"
    violations: list[str] = []
    for name in APPLICATION_UTILITY_MODULES:
        module = root / f"{name}.py"
        for path in [module] if module.is_file() else _python_sources(root / name):
            violations.extend(_import_violations(path, ("grida",)))
    assert not violations, "an application utility imports FX:\n" + "\n".join(violations)


def _matches(imported: str, allowed: str) -> bool:
    return imported == allowed or imported.startswith(f"{allowed}.")


#: Where FX is driven from outside the product's own sources: the games' pipelines, their
#: Python tools and tests, and the Godot tools.
FX_CONSUMER_SOURCES = (
    *(
        path
        for pattern in ("*/pipeline/nodes", "*/pipeline/workflow.py", "*/tools", "*/tests")
        for path in sorted((SOURCE_ROOT.parent / "godot/games").glob(pattern))
        if path.is_file() or any(path.rglob("*.py"))
    ),
    SOURCE_ROOT.parent / "godot/tools",
)
#: What `grida.fx` exports, read without importing it statically (this file is scanned too).
FX_SURFACE = frozenset(importlib.import_module("grida.fx").__all__)


def _consumer_sources() -> list[Path]:
    sources: set[Path] = set()
    for root in (*CONSUMER_ROOTS, *FX_CONSUMER_SOURCES):
        sources.update([root] if root.is_file() else _python_sources(root))
    return sorted(sources)


def _fx_import_violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative = path.relative_to(SOURCE_ROOT.parent)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            violations += [
                f"{relative}:{node.lineno} imports {alias.name}; write from grida.fx import X"
                for alias in node.names
                if alias.name.split(".")[0] == "grida"
            ]
            continue
        if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
            continue
        if node.module.split(".")[0] == "grida" and node.module != "grida.fx":
            violations.append(f"{relative}:{node.lineno} imports {node.module}, not grida.fx")
        elif node.module == "grida.fx":
            violations += [
                f"{relative}:{node.lineno} imports grida.fx.{alias.name}, which it does not export"
                for alias in node.names
                if alias.name not in FX_SURFACE
            ]
    return violations


def test_fx_is_imported_only_through_its_declared_surface() -> None:
    """FX is imported only as ``from grida.fx import X`` with ``X`` in ``grida.fx.__all__``:
    never a private module, never ``grida.fx.std``."""

    violations = [found for path in _consumer_sources() for found in _fx_import_violations(path)]
    assert not violations, "imports past FX's declared surface:\n" + "\n".join(violations)


def test_product_source_never_statically_imports_optional_consumers() -> None:
    violations: list[str] = []
    for root in (
        SOURCE_ROOT / "stage_gen",
        SOURCE_ROOT.parent / "scripts",
    ):
        for path in _python_sources(root):
            violations.extend(_import_violations(path, (*GAME_MODULES, "concept_studio")))
    assert not violations, "product imports an optional consumer:\n" + "\n".join(violations)


def test_shared_game_code_has_no_named_game_or_collection_dependencies() -> None:
    violations: list[str] = []
    for path in _python_sources(GAME_SOURCE_ROOTS[0] / "demo_game_tools"):
        violations.extend(_import_violations(path, GAME_MODULES[1:]))
    assert not violations, "shared code imports its consumer:\n" + "\n".join(violations)


def test_game_pipelines_do_not_import_other_games_or_collection_tooling() -> None:
    violations: list[str] = []
    for root, own_module in zip(GAME_SOURCE_ROOTS[2:], GAME_MODULES[2:], strict=True):
        forbidden = tuple(module for module in GAME_MODULES[1:] if module != own_module)
        for path in _python_sources(root):
            violations.extend(_import_violations(path, forbidden))
    assert not violations, "game imports a sibling consumer:\n" + "\n".join(violations)


#: Modules earlier refactors and the move onto FX retired, the old engine's packages included:
#: each is gone, and nothing imports it.
RETIRED_MODULES = (
    "stage_gen.interfaces",
    "stage_gen.runs",
    "stage_gen.pipeline",
    "stage_gen.application.runs",
    "stage_gen.components._node_kit",
    "stage_gen.capabilities",
    "demo_game_tools.preparation",
    "gnode",
    "gnode_std",
    "stage_gen.orchestration",
    "stage_gen.model_routes",
    "stage_gen.model_policy_maintenance",
    "stage_gen.image_binding",
    "stage_gen.image_product",
    "stage_gen.config",
    "stage_gen.identity",
    "stage_gen.workflows._gnode",
    "stage_gen.workflows._reference",
    "stage_gen.viewer",
    "stage_gen.runview.contexts",
    "stage_gen.runview.facts",
    "stage_gen.runview.refresh",
)


def test_retired_modules_are_gone_and_imported_by_nothing() -> None:
    present = [
        module
        for module in RETIRED_MODULES
        for root in (SOURCE_ROOT, *GAME_SOURCE_ROOTS)
        if (root / Path(*module.split("."))).with_suffix(".py").exists()
        or (root / Path(*module.split("."))).is_dir()
    ]
    assert not present, f"retired modules are back: {present}"
    violations = [
        violation
        for path in _consumer_sources()
        for violation in _import_violations(path, RETIRED_MODULES)
    ]
    assert not violations, "imports of retired modules:\n" + "\n".join(violations)
