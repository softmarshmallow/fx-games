# test-owner: product
from __future__ import annotations

import importlib.util
import shlex
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import yaml

FX = ("python", "-m", "grida.fx")


def load_check_script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "check.py"
    spec = importlib.util.spec_from_file_location("fx_games_check", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: dataclasses resolve their annotations through
    # sys.modules, and the gate script declares two.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_offline_gate_removes_provider_credentials_and_lists_required_checks() -> None:
    check = load_check_script()
    environment = check.sanitized_environment(
        {
            "PATH": "/bin",
            "OPENAI_API_KEY": "openai",
            "OPENROUTER_API_KEY": "openrouter",
            "FAL_KEY": "fal",
            "ELEVENLABS_API_KEY": "elevenlabs",
            "TRIPO_API_KEY": "tripo",
            "GRIDA_FX_PYTHON": "/elsewhere/python",
            "GRIDA_FX_NETWORK": "on",
        },
        python="/venv/bin/python",
    )
    # FX is held offline whatever the caller set: node bodies on the gate's interpreter, no
    # .env, no network.
    assert environment == {
        "PATH": "/bin",
        "GRIDA_FX_PYTHON": "/venv/bin/python",
        "GRIDA_FX_DISABLE_DOTENV": "1",
        "GRIDA_FX_NETWORK": "off",
    }
    assert check.sanitized_environment({"GRIDA_FX_BIN": "/opt/grida-fx"})["GRIDA_FX_BIN"] == (
        "/opt/grida-fx"
    )
    commands = check.commands("python", scope="all")
    assert ("pytest",) in commands
    assert ("ruff", "format", "--check", ".") in commands
    typecheck = next(command for command in commands if command[0] == "mypy")
    assert typecheck[:5] == ("mypy", "--strict", "src", "tests", "scripts")
    root = Path(__file__).parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    members = project["tool"]["uv"]["workspace"]["members"]
    assert {member + "/src" for member in members if member.startswith("godot/")} <= set(typecheck)
    assert all((root / target).exists() for target in typecheck[2:])
    # The copyable template retains its existing typed script; game-local
    # wrappers are exercised as commands, avoiding multiple modules named prepare.
    assert [target for target in typecheck if target.endswith("prepare.py")] == [
        "godot/templates/asset_consumer/prepare.py"
    ]
    assert ("python", "scripts/check_docs.py") in commands
    assert ("bun", "test") in commands
    assert ("python", "scripts/site.py", "build", "--allow-missing-examples") in commands
    assert check.commands("python", scope="web")[3] == (
        "python",
        "scripts/site.py",
        "build",
        "--allow-missing-examples",
    )
    # Godot owns discovery, fixture preparation and the different native adapters.
    # The root gate delegates without maintaining a second project/test roster.
    assert commands.count(("python", "godot/tools/check.py")) == 1
    assert not any("godot/tools/run_native_suite.py" in command for command in commands)
    assert check.commands("python", scope="godot")[1] == ("python", "godot/tools/check.py")
    assert not any(
        "gnode" in item or "conformance" in item for command in commands for item in command
    )


def test_every_scope_starts_with_the_engine() -> None:
    check = load_check_script()
    # The tests, the site and the catalog all plan, so FX's engine comes first: built from the
    # submodule, or only probed when GRIDA_FX_BIN names one.
    for scope in ("product", "web", "godot", "games", "docs", "all"):
        assert check.commands("python", scope=scope)[0] == ("python", check.ENGINE_BUILD)
        assert check.commands("python", scope=scope, engine_bin="/opt/grida-fx")[0] == (
            *FX,
            "--version",
        )


def test_games_gate_exercises_local_defaults_variants_and_explicit_sources() -> None:
    check = load_check_script()
    commands = check.commands("python", scope="games")
    game_scripts = [
        command
        for command in commands
        if command[0] == "python" and command[1].endswith("/pipeline/prepare.py")
    ]
    # The Grain's script proves its case; every asset of every game is built with FX.
    assert game_scripts == [("python", "godot/games/the_grain/pipeline/prepare.py")]
    # Each game's lock and each package's plan are checked, Ember Hollow's at every scope.
    assert commands.count((*FX, "lock", "--check")) == 4
    for builder, package, extra in (
        ("build", "inputs", ()),
        ("build", "inputs/default", ()),
        ("build", "inputs/waves", ()),
        ("room", "inputs/rooms/window", ()),
        ("room", "inputs/rooms/motor_court", ()),
        ("scene", "inputs", ()),
        *(("build", "inputs", ("--arg", f"scope={scope}")) for scope in ("minimal", "full")),
    ):
        assert (
            *FX,
            "plan",
            f"pipeline/workflow.py:{builder}",
            "--arg",
            f"package={package}",
            *extra,
            "--check",
        ) in commands
    assert all("--live" not in command for command in commands)
    validators = [
        command
        for command in commands
        if command[:2] == ("python", "godot/tools/validate_game_package.py")
    ]
    assert {command[3] for command in validators if command[2] == "--input"} == {
        "godot/games/bellweather/inputs/default",
        "godot/games/bellweather/inputs/waves",
        "godot/games/iron_petal_unit/inputs",
    }
    assert (
        "demo-games",
        "scenario",
        "check",
        "--input",
        "godot/games/the_grain/inputs",
    ) in commands
    assert ("demo-games", "case", "bundle", "--help") in commands
    assert all("legacy" not in command and "main.toml" not in command for command in commands)


def test_ci_uses_the_same_typecheck_surface_as_the_aggregate_gate() -> None:
    check = load_check_script()
    commands = check.commands("python", scope="all")
    typecheck = next(command for command in commands if command[0] == "mypy")
    workflow = (Path(__file__).parents[2] / ".github/workflows/gate.yml").read_text()
    body = workflow.split("      - name: Typecheck product and optional consumers\n", 1)[1]
    lines = body.splitlines()[1:]
    script_lines = []
    for line in lines:
        if not line.startswith("          "):
            break
        script_lines.append(line.strip())
    assert tuple(shlex.split(" ".join(script_lines))) == ("uv", "run", "--all-groups", *typecheck)
    games = [command for command in commands if command[0] == "mypy"][1:]
    body = workflow.split("      - name: Typecheck game projects\n", 1)[1]
    game_lines = []
    for line in body.splitlines()[1:]:
        if not line.startswith("          "):
            break
        game_lines.append(line.strip())
    assert [tuple(shlex.split(line)) for line in game_lines] == [
        ("uv", "run", "--all-groups", *command) for command in games
    ]


def test_ci_gates_on_the_engine_it_builds_once() -> None:
    gate = yaml.safe_load((Path(__file__).parents[2] / ".github/workflows/gate.yml").read_text())
    jobs = gate["jobs"]
    built = [step for step in jobs["engine"]["steps"] if "run" in step]
    assert any("third_party/fx/tools/build_engine.py" in step["run"] for step in built)
    # Every job that runs the gate script plans, so it waits for the engine and downloads it.
    gating = [
        name
        for name, job in jobs.items()
        if any("scripts/check.py" in step.get("run", "") for step in job["steps"])
    ]
    assert set(gating) == {"product", "optional-python", "web", "godot"}
    for name in gating:
        job = jobs[name]
        needs = job.get("needs", [])
        assert "engine" in ([needs] if isinstance(needs, str) else needs), name
        assert any(
            step.get("uses", "").startswith("actions/download-artifact") for step in job["steps"]
        ), name
        assert any("GRIDA_FX_BIN=" in step.get("run", "") for step in job["steps"]), name


def test_the_gate_reports_every_step_rather_than_stopping_at_the_first() -> None:
    check = load_check_script()
    outcomes = [
        check.Outcome(check.Step(("ruff", "format", "--check", ".")), 1, 0.5),
        check.Outcome(check.Step(("pytest",)), 0, 12.0),
        check.Outcome(check.Step(("bun", "test")), None, 0.0),
    ]
    table = check.report(outcomes)
    lines = table.splitlines()
    assert lines[0].startswith("FAIL") and "exit   1" in lines[0]
    assert lines[1].startswith("PASS")
    assert lines[2].startswith("FAIL") and "exit   -" in lines[2]
    assert lines[-1] == "offline gate: 1 of 3 steps passed in 12s"


def test_product_gate_does_not_require_optional_consumers() -> None:
    check = load_check_script()
    commands = check.commands("python")
    assert all(command[0] != "bun" for command in commands)
    assert all(not item.startswith("godot/") for command in commands for item in command)
    assert ("mypy", "--strict", "src") in commands
    tests = next(command for command in commands if command[0] == "pytest")
    assert len(tests) > 3
    assert not any("test_godot_" in item for item in tests)


def test_product_gate_runs_the_workflows_through_their_command_lines() -> None:
    from fx_games.workflows._registry import discover

    check = load_check_script()
    commands = check.commands("python")
    assert not any(command[0] == "stage-gen" for command in commands)
    files = {w.id for w in discover() if w.root.joinpath("workflow.yaml").is_file()}
    assert files == {w.id for w in discover()}
    paid = {"character-3d", "portrait-motion", "universe"}
    for workflow in files - paid:
        assert (*FX, "run", workflow) in {command[:5] for command in commands}
        assert (*FX, "inspect", workflow, "--verify") in commands
    # A run of all paid calls is planned, phases and ceilings included; pytest runs it offline.
    for workflow in paid:
        assert (*FX, "plan", workflow) in {command[:5] for command in commands}
    # FX locks a folder, not an id: each workflow home's own lock.
    homes = {f"src/fx_games/workflows/{w.root.name}" for w in discover()}
    assert {(*FX, "lock", home, "--check") for home in homes} <= set(commands)
    # The runs happen in a scratch project written by the product's one project writer, so FX
    # finds the workflows by id from outside the repository.
    project = next(command for command in commands if "write_project" in " ".join(command))
    assert project[:2] == ("python", "-c")
    assert (*FX, "--help") in commands
    assert any(command[1:3] == ("scripts/catalog.py", "--check") for command in commands)
    assert all("--live" not in command for command in commands)
    assert not any(
        command[0].startswith("stage-gen-") for command in check.commands("python", scope="all")
    )


def test_owned_test_gates_partition_every_offline_test() -> None:
    from scripts.test_ownership import CONSUMER_TEST_ROOTS, TestOwner, paths_for
    from scripts.test_ownership import test_owners as collect_owners

    root = Path(__file__).parents[2]
    owned = collect_owners(root)
    assert owned["tests/integration/test_game_cli_imports.py"] == "games"
    expected = {
        str(path.relative_to(root))
        for folder in ("tests", *CONSUMER_TEST_ROOTS)
        for path in (root / folder).rglob("test_*.py")
    }
    assert set(owned) == expected
    scopes: tuple[TestOwner, ...] = ("product", "games", "godot", "web")
    groups = [set(paths_for(root, scope)) for scope in scopes]
    assert set.union(*groups) == expected
    assert sum(map(len, groups)) == len(expected)
