"""Every documented FX command parses against the real command line.

A command shown to a reader is a promise: a renamed verb, a dropped flag or a misspelt
workflow id must fail here, not on the reader's machine. Commands are read from fenced
``sh``/``bash`` blocks in README.md, the live docs (``docs/`` without its history roots),
each workflow's ``page.mdx``, ``contract.md`` and example pages, the Godot docs, and each
``workflow.toml`` ``[try]`` table. A ``python -m grida.fx`` command is checked against what
``python -m grida.fx <verb> --help`` states, with only its workflow's own input flags beside
it. A retired command line, or a bare ``grida-fx``, fails wherever it is still shown. None is
executed.
"""

from __future__ import annotations

import re
import shlex
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from stage_gen.workflows._checks import FX_PROGRAM, fx_command_problems

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPOSITORY_ROOT / "src/stage_gen/workflows"
#: History describes what was true when it was written, so its commands are not held to today.
HISTORY_ROOTS = ("docs/decisions/", "docs/plans/", "docs/research/", "docs/media/")
FENCE = re.compile(
    r"^(?P<indent>[ \t]*)```(?P<info>[^\n`]*)\n(?P<body>.*?)^(?P=indent)```", re.M | re.S
)
SHELL_FENCES = {"sh", "bash", "shell", "console"}
ENVIRONMENT = re.compile(r"^[A-Z_][A-Z0-9_]*=")
#: The ``uv run`` options a documented command may carry before its program.
UV_RUN_FLAGS_WITH_VALUE = {"--group", "--extra", "--with", "--python", "--directory"}
COMMAND_SEPARATORS = {"&&", "||", ";", "|"}
FX = " ".join(FX_PROGRAM)
#: Command lines a reader may no longer be shown; FX's viewer replaced ``scripts/view.py``.
RETIRED_PROGRAMS = ("stage-gen", "gnode", "grida-fx", "scripts/view.py")


@dataclass(frozen=True, slots=True)
class Documented:
    source: str
    arguments: tuple[str, ...]
    program: str = FX

    def __str__(self) -> str:
        return f"{self.source}: {self.program} {shlex.join(self.arguments)}"


def _documents() -> list[Path]:
    documents = [REPOSITORY_ROOT / "README.md"]
    documents += [
        path
        for path in sorted((REPOSITORY_ROOT / "docs").rglob("*.md"))
        if not path.relative_to(REPOSITORY_ROOT).as_posix().startswith(HISTORY_ROOTS)
    ]
    for pattern in ("*/page.mdx", "*/contract.md", "*/examples/*.mdx"):
        documents += sorted(WORKFLOWS.glob(pattern))
    documents += [
        path
        for path in sorted((REPOSITORY_ROOT / "godot").rglob("*.md"))
        if "docs" in path.relative_to(REPOSITORY_ROOT / "godot").parts[:-1]
        and "history" not in path.parts
    ]
    return documents


def _logical_lines(body: str) -> Iterator[str]:
    """A shell block's lines, with backslash continuations joined."""
    pending = ""
    for line in body.splitlines():
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        yield pending + stripped
        pending = ""
    if pending:
        yield pending


def _program(words: list[str]) -> tuple[str, tuple[str, ...]] | None:
    """The program a command runs, after env assignments and ``uv run``, and its arguments;
    None for a command this test does not hold to anything."""
    while words and ENVIRONMENT.match(words[0]):
        words = words[1:]
    if words[:2] == ["uv", "run"]:
        words = words[2:]
        while words and words[0].startswith("--"):
            flag = words.pop(0)
            if flag in UV_RUN_FLAGS_WITH_VALUE and "=" not in flag:
                words = words[1:]
    if tuple(words[: len(FX_PROGRAM)]) == FX_PROGRAM:
        return FX, tuple(words[len(FX_PROGRAM) :])
    if words[:1] == ["python"]:
        words = words[1:]
    if words and words[0] in RETIRED_PROGRAMS:
        return words[0], tuple(words[1:])
    return None


def _commands(line: str) -> Iterator[tuple[str, tuple[str, ...]]]:
    """The FX and retired invocations in one shell line."""
    try:
        tokens = shlex.split(line, comments=True)
    except ValueError:
        return
    command: list[str] = []
    for token in [*tokens, ";"]:
        if token not in COMMAND_SEPARATORS:
            command.append(token)
            continue
        found = _program(command)
        command = []
        if found is not None:
            yield found


def documented_commands() -> list[Documented]:
    found: list[Documented] = []
    for document in _documents():
        relative = document.relative_to(REPOSITORY_ROOT).as_posix()
        for fence in FENCE.finditer(document.read_text(encoding="utf-8")):
            if fence.group("info").strip().split(" ")[0] not in SHELL_FENCES:
                continue
            for line in _logical_lines(fence.group("body")):
                found.extend(
                    Documented(relative, command, program) for program, command in _commands(line)
                )
    for manifest in sorted(WORKFLOWS.glob("*/workflow.toml")):
        relative = manifest.relative_to(REPOSITORY_ROOT).as_posix()
        table = tomllib.loads(manifest.read_text(encoding="utf-8")).get("try", {})
        for command in table.get("commands", []):
            program = _program(shlex.split(command))
            assert program is not None, f"{relative}: [try] command must run {FX}"
            found.append(Documented(f"{relative} [try]", program[1], program[0]))
    return found


DOCUMENTED = documented_commands()


def test_the_scan_reads_every_kind_of_source() -> None:
    sources = {command.source for command in DOCUMENTED}
    assert "README.md" in sources
    assert any(source.startswith("docs/") for source in sources)
    assert any(source.endswith("/page.mdx") for source in sources)
    assert any(source.endswith("/contract.md") for source in sources)
    assert any(source.startswith("godot/") for source in sources)
    assert sum(source.endswith("[try]") for source in sources) == len(
        list(WORKFLOWS.glob("*/workflow.toml"))
    )


@pytest.mark.parametrize("command", DOCUMENTED, ids=str)
def test_documented_command_parses_with_the_real_cli(command: Documented) -> None:
    assert command.program not in RETIRED_PROGRAMS, (
        f"{command}: {command.program} is retired; show uv run {FX}"
    )
    problems = fx_command_problems(command.arguments)
    assert not problems, f"{command.source}: {problems}"


def test_a_retired_command_fails_the_parse() -> None:
    for retired in (
        ("show", "universe"),
        ("view",),
        ("catalog", "export", "--out", "site"),
        ("plan",),
        ("plan", "universe", "--no-such-input", "x"),
        ("inspect", "universe", "--write-view"),
    ):
        assert fx_command_problems(retired), retired


def test_a_retired_program_is_found_and_refused() -> None:
    for program in RETIRED_PROGRAMS:
        assert [found for found, _ in _commands(f"uv run {program} plan universe")] == [program]
