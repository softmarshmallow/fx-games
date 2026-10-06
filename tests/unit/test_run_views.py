"""``scripts/view.py``: the FX runs it finds, and the run views it keeps fresh in the cache.

Every run here is built under ``tmp_path`` and every viewer is a stand-in that waits for what
the test expects and returns. A view must land in the cache only; each test that has one
written checks that the run folder is byte-for-byte as it was written.
"""

from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import time
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from grida.fx import run

from stage_gen import viewer
from stage_gen.runview import discover, view_key
from stage_gen.viewer import ViewerRequest
from tests.unit._fx import WORKFLOWS, failures, scratch_project

PARALLAX_INPUTS = WORKFLOWS / "looping_parallax/inputs/supplied_layers/make_inputs.py"
WAIT_SECONDS = 30.0


def _write(path: Path, document: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = document if isinstance(document, str) else json.dumps(document)
    path.write_text(text, encoding="utf-8")
    return path


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def _started_run(run_dir: Path) -> Path:
    """An FX run as it starts: its plan (here, one no view can be built from) and the record
    it appends to."""
    _write(run_dir / "plan.json", {"kind": "fx-graph-v1"})
    _write(run_dir / "events.jsonl", "")
    return run_dir


@pytest.fixture(scope="module")
def parallax_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real, free looping-parallax run: every layer is mirrored, so nothing is paid."""
    base = tmp_path_factory.mktemp("parallax")
    inputs = runpy.run_path(str(PARALLAX_INPUTS))["write_inputs"](base / "inputs")
    project = scratch_project(base / "project")
    completed = run("looping-parallax", input_files=[inputs], cwd=project)
    assert completed.ok, failures(completed)
    return completed.run_dir


class _Viewer:
    """A viewer that waits until ``ready`` holds (or a deadline passes), then returns."""

    def __init__(self, ready: Callable[[ViewerRequest], bool]) -> None:
        self.ready = ready
        self.requests: list[ViewerRequest] = []

    def __call__(self, request: ViewerRequest, **_: Any) -> int:
        self.requests.append(request)
        deadline = time.monotonic() + WAIT_SECONDS
        while not self.ready(request):
            if time.monotonic() > deadline:
                return 1
            time.sleep(0.05)
        return 0


@pytest.fixture(autouse=True)
def _cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


def _install(monkeypatch: pytest.MonkeyPatch, launch: Callable[..., int]) -> None:
    """``launch`` in place of the real viewer, which would start Bun."""
    monkeypatch.setattr(viewer, "launch", launch)


def _view(cwd: Path, *arguments: str, errors: StringIO | None = None) -> int:
    return viewer.main(list(arguments), stdout=StringIO(), stderr=errors or StringIO(), cwd=cwd)


def _view_of(request: ViewerRequest, run_dir: Path) -> Path:
    return request.view_cache / view_key(run_dir) / "execution-view.json"


# ---------------------------------------------------------------- the runs it finds


def test_it_finds_fx_runs_under_each_root_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, spikes, elsewhere = tmp_path / "out", tmp_path / "spikes", tmp_path / "elsewhere"
    expected = [
        _started_run(out / "runs/universe/2026-10-03-1"),
        _started_run(spikes / "review/facial-4k/yuzu/run-01"),
    ]
    _write(out / "ember-hollow/manifest.json", {"kind": "a delivered package"})
    _write(spikes / "plan-only/plan.json", {"kind": "fx-graph-v1"})
    _started_run(out / ".cache/run")
    _started_run(out / "node_modules/pkg")
    _started_run(out / "runs/universe/2026-10-03-1/files/inner")
    _started_run(out / "a/b/c/d/too-deep")
    _started_run(elsewhere / "outside")
    (out / "linked").symlink_to(elsewhere, target_is_directory=True)
    # A plan and record of another engine are foreign: neither listed nor searched below.
    _write(out / "runs/old/plan.json", {"kind": "other-graph-v2"})
    _write(out / "runs/old/events.jsonl", "")
    _started_run(out / "runs/old/files/inner")
    seen = _Viewer(lambda request: all(_view_of(request, run).is_file() for run in expected))
    _install(monkeypatch, seen)

    assert discover([out, spikes]) == [run.resolve() for run in expected]
    assert _view(tmp_path, str(out), str(spikes)) == 0
    time.sleep(0.2)  # one pass writes every view it finds
    kept = {path.name for path in seen.requests[0].view_cache.iterdir()}
    assert kept == {view_key(run) for run in expected}


# ---------------------------------------------------------------- the views it keeps


def _reported(errors: StringIO) -> set[str]:
    return set(re.findall(r"no view for (\S+):", errors.getvalue()))


def test_a_run_s_view_contexts_templates_and_files_are_written_into_the_cache_only(
    tmp_path: Path, parallax_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = shutil.copytree(parallax_run, tmp_path / "runs/parallax-01")
    before = _snapshot(run_dir)
    seen = _Viewer(lambda request: _view_of(request, run_dir).is_file())
    _install(monkeypatch, seen)

    assert _view(tmp_path, str(tmp_path / "runs")) == 0

    [request] = seen.requests
    assert request.view_cache == tmp_path / "cache/stage-gen/views"
    written = _view_of(request, run_dir)
    assert _snapshot(run_dir) == before
    view = json.loads(written.read_text(encoding="utf-8"))
    assert view["kind"] == "stage-gen-run-view-v1" and view["schema_version"] == 3
    assert view["run_state"] == "succeeded"
    assert {node["state"] for node in view["nodes"]} == {"succeeded"}
    contexts = json.loads((written.parent / "view-contexts.json").read_text(encoding="utf-8"))
    assert contexts["kind"] == "stage-gen-view-contexts-v1"
    compose = next(view for view in contexts["views"] if view["node_id"] == "compose#1")
    template = (written.parent / compose["template"]).read_text(encoding="utf-8")
    assert 'from "/_views/view.js"' in template
    preview = compose["outputs"]["preview"]
    assert preview["ref"].startswith("views/files/")
    assert (written.parent / preview["ref"]).read_bytes() == (
        run_dir / "files/compose/preview.png"
    ).read_bytes()
    for context in contexts["views"]:
        assert (written.parent / context["template"]).is_file()
        assert not (written.parent / context["template"]).is_symlink()


def test_a_view_is_written_again_only_when_its_run_changes(
    tmp_path: Path, parallax_run: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runs"
    good = shutil.copytree(parallax_run, root / "good")
    # Its plan has lost every instance: no view can be built from it, and the good run's
    # view is written all the same.
    broken = shutil.copytree(parallax_run, root / "broken")
    plan = json.loads((broken / "plan.json").read_text(encoding="utf-8"))
    (broken / "plan.json").write_text(
        json.dumps({**plan, "instances": "not a list"}), encoding="utf-8"
    )
    errors = StringIO()
    _install(
        monkeypatch,
        _Viewer(lambda request: _view_of(request, good).is_file() and bool(_reported(errors))),
    )
    assert _view(tmp_path, str(root), errors=errors) == 0
    assert _reported(errors) == {str(broken.resolve())}
    assert "view: no view for" in errors.getvalue()
    view = _view_of(ViewerRequest((root,), tmp_path / "cache/stage-gen/views", 3000, False), good)
    written = view.stat().st_mtime_ns

    # Nothing changed: the next view leaves it as it was.
    _install(monkeypatch, _Viewer(lambda request: True))
    assert _view(tmp_path, str(root)) == 0
    time.sleep(0.5)
    assert view.stat().st_mtime_ns == written

    # The run's record changed: it is written again.
    events = good / "events.jsonl"
    later = time.time() + 10
    os.utime(events, (later, later))
    _install(monkeypatch, _Viewer(lambda request: view.stat().st_mtime_ns > written))
    assert _view(tmp_path, str(root)) == 0


def test_the_view_key_is_the_real_path_hashed(tmp_path: Path) -> None:
    run_dir = _started_run(tmp_path / "runs/run-01")
    (tmp_path / "alias").symlink_to(tmp_path / "runs", target_is_directory=True)
    assert view_key(tmp_path / "alias/run-01") == view_key(run_dir)
    assert re.fullmatch(r"[0-9a-f]{16}", view_key(run_dir))


# ---------------------------------------------------------------- the command


def test_the_viewer_gets_the_roots_the_cache_and_the_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[ViewerRequest] = []

    def launch(request: ViewerRequest, **_: Any) -> int:
        seen.append(request)
        return 7

    _install(monkeypatch, launch)
    (tmp_path / "project/out/runs").mkdir(parents=True)
    (tmp_path / "project/fx.yaml").write_text("fx: project/v1\nruns: out/runs\n", encoding="utf-8")

    assert _view(tmp_path / "project", "--port", "3100", "--no-open") == 7
    assert seen == [
        ViewerRequest(
            roots=((tmp_path / "project/out/runs").resolve(),),
            view_cache=tmp_path / "cache/stage-gen/views",
            port=3100,
            open_browser=False,
        )
    ]


def test_a_missing_run_folder_or_a_bad_port_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, lambda request, **_: 0)
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path / "absent"), errors=errors) == 2
    assert "no run folder at" in errors.getvalue()
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path), "--port", "0", errors=errors) == 2
    assert "--port" in errors.getvalue()


def test_a_viewer_that_refuses_to_start_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(request: ViewerRequest, **_: Any) -> int:
        raise ValueError(viewer.REFUSAL)

    _install(monkeypatch, refuse)
    errors = StringIO()
    assert _view(tmp_path, str(tmp_path), errors=errors) == 2
    assert viewer.REFUSAL in errors.getvalue()
