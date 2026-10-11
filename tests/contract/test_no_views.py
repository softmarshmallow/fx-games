"""Nothing here declares a view: runs are seen in FX's viewer (decision 0075).

FX records a step's ``view:`` for views it may render later and renders none, and Stage Gen
keeps no viewer of its own, so a ``view:`` in a workflow file, or a ``view=`` on ``@node(...)``,
would be a declaration nothing reads.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import TypeGuard

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTS = ("src", "godot")


def _sources(suffixes: tuple[str, ...] = (".py",)) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *ROOTS],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [REPOSITORY / name for name in listed if name.endswith(suffixes)]


def _is_node(decorator: ast.expr) -> TypeGuard[ast.Call]:
    if not isinstance(decorator, ast.Call):
        return False
    called = decorator.func
    return (isinstance(called, ast.Name) and called.id == "node") or (
        isinstance(called, ast.Attribute) and called.attr == "node"
    )


def test_no_node_type_declares_a_view() -> None:
    found: list[str] = []
    sources = _sources()
    assert sources, "no Python sources found under src/ and godot/"
    for path in sources:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for definition in ast.walk(tree):
            if not isinstance(definition, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for decorator in definition.decorator_list:
                if _is_node(decorator) and any(kw.arg == "view" for kw in decorator.keywords):
                    where = f"{path.relative_to(REPOSITORY)}:{decorator.lineno}"
                    found.append(f"{where} @node(view=...) on {definition.name}")
    assert found == [], "a node type declares a view\n" + "\n".join(found)


def test_no_workflow_file_declares_a_view() -> None:
    found = [
        f"{path.relative_to(REPOSITORY)}:{number}"
        for path in _sources((".yaml", ".yml"))
        if path.is_file() and path.read_text(encoding="utf-8").startswith("fx: workflow/")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.match(r"\s*view:", line)
    ]
    assert found == [], "a workflow file declares a view\n" + "\n".join(found)
