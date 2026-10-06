"""``scripts/examples.py promote`` makes an example only from a run whose calls a provider
answered: a stand-in run is refused before anything is imported or pinned."""

from __future__ import annotations

import importlib.util
import json
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType

REPOSITORY = Path(__file__).resolve().parents[3]
MANIFEST = REPOSITORY / "src/stage_gen/workflows/movie_sprite/workflow.toml"


def _load_script() -> ModuleType:
    path = REPOSITORY / "scripts/examples.py"
    spec = importlib.util.spec_from_file_location("examples_script", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_stand_in_run_is_not_promoted(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs/movie-sprite/2026-10-06-1"
    run_dir.mkdir(parents=True)
    plan = {"kind": "fx-graph-v1", "workflow": {"id": "movie-sprite"}, "stand_in": True}
    (run_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    manifest = MANIFEST.read_bytes()
    store = tmp_path / "store"
    errors = StringIO()

    arguments = ["promote", "movie-sprite", "--run", str(run_dir), "--id", "stand-in"]
    status = _load_script().main(
        [*arguments, "--examples", str(store)], stdout=StringIO(), stderr=errors
    )

    assert status == 2
    assert (
        "2026-10-06-1 is a stand-in run; an example is made from a run whose calls a provider "
        "answered"
    ) in errors.getvalue()
    assert not store.exists()
    assert MANIFEST.read_bytes() == manifest
