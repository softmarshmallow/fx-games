"""A node type declares no view: FX records only a step's ``view:``.

FX's plan keeps each step's ``view`` setting and nothing a node type says about views, so a
``view=`` on ``@node(...)`` would be dropped without a word. A view belongs to the step in the
workflow file (``view: true`` or ``view: ./views/<name>.html``).
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from typing import TypeGuard

REPOSITORY = Path(__file__).resolve().parents[2]
ROOTS = ("src", "godot")


def _sources() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *ROOTS],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [REPOSITORY / name for name in listed if name.endswith(".py")]


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
    assert found == [], "a node type declares a view; set the step's view: instead\n" + "\n".join(
        found
    )
