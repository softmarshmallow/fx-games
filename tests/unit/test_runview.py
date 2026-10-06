"""Reading an FX run folder: the run view, the view contexts and the names FX places files at.

The run here is a real FX run of a small workflow in a scratch project, its one paid step
answered by a stand-in: the drawing's first take is opaque, which its judge rejects, so a
second take is drawn and placed in a folder of its own. Every name the projection gives a file
is checked against the engine's own (``inspect --json``).
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from grida.fx import Answer, RunResult, StandInCall, run
from PIL import Image

from stage_gen.runview import (
    VIEW_CONTEXT_KIND,
    find_file,
    is_fx_run,
    is_stand_in,
    placed_path,
    project_run,
    read_events,
    read_plan,
    store_of,
    verify_run,
    view_contexts,
    workflow_home,
)
from stage_gen.workflows._fx import write_project
from tests.unit._fx import failures

ROUTE = "gpt-image-2.5-sunburst@openai"
FLOW = """\
fx: workflow/v1
id: flow
title: Flow
inputs:
  picture: { type: file, kind: image }
steps:
  draw:
    title: Draw a lantern
    uses: fx/image.generate@1
    with: { prompt: a lantern, background: transparent, size: 64x64 }
    view: true
  clean:
    uses: fx/image.check_alpha@1
    judges: draw
    with: { image: "${{ steps.draw.outputs.image }}", expect: transparent }
    on_reject:
      regenerate: { max: 2 }
  loud:
    uses: ./nodes/test_nodes.py#shout
    with: { text: lantern }
    view: ./views/words.html
  quiet:
    uses: ./nodes/test_nodes.py#shout
    with: { text: unseen }
  measure:
    title: Measure the picture
    uses: ./nodes/test_nodes.py#measure
    with: { image: "${{ inputs.picture }}" }
    view: true
  words:
    for_each: [harbour, lantern]
    key: ${{ item }}
    steps:
      loud:
        title: Shout it
        uses: ./nodes/test_nodes.py#shout
        with: { text: "${{ item }}" }
outputs:
  image: ${{ steps.draw.outputs.image }}
  words: ${{ steps.words.*.loud.outputs.text }}
view: ./views/whole.html
"""
NODES = """\
from PIL import Image

from grida.fx import Ctx, node


@node("shout", params={"text": str}, outputs={"text": "text/plain"})
def shout(ctx: Ctx) -> dict:
    return {"text": ctx.out.text(ctx.params["text"].upper())}


@node("measure", inputs={"image": "image"}, outputs={"size": "json"})
def measure(ctx: Ctx) -> dict:
    with Image.open(ctx.inputs["image"].path) as picture:
        width, height = picture.size
    return {"size": ctx.out.json({"width": width, "height": height})}
"""
WORDS = "<!doctype html><p>words</p>\n"
WHOLE = "<!doctype html><p>the whole run</p>\n"


def _png(width: int, height: int, alpha: int) -> bytes:
    picture = Image.new("RGBA", (width, height), (32, 24, 16, alpha))
    picture.paste((200, 120, 40, 255), (width // 4, height // 4, width * 3 // 4, height * 3 // 4))
    out = io.BytesIO()
    picture.save(out, "PNG")
    return out.getvalue()


def _answer(call: StandInCall) -> Answer:
    # Take 1 is opaque everywhere, which the judge rejects; take 2 has a clear background.
    return Answer(files={"image": _png(64, 64, 255 if call.take == 1 else 0)})


def _project(folder: Path) -> Path:
    write_project(
        folder, runs="runs", cache="cache", routes={"image.generate": ROUTE}, workflows=()
    )
    (folder / "nodes").mkdir()
    (folder / "nodes/test_nodes.py").write_text(NODES, encoding="utf-8")
    (folder / "views").mkdir()
    (folder / "views/words.html").write_text(WORDS, encoding="utf-8")
    (folder / "views/whole.html").write_text(WHOLE, encoding="utf-8")
    (folder / "flow.yaml").write_text(FLOW, encoding="utf-8")
    (folder / "art").mkdir()
    (folder / "art/picture.png").write_bytes(_png(40, 30, 255))
    (folder / "inputs.yaml").write_text("picture: art/picture.png\n", encoding="utf-8")
    return folder


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    project = _project(tmp_path_factory.mktemp("runview") / "project")
    result = run("flow.yaml", input_files=["inputs.yaml"], cwd=project, stand_in=_answer)
    assert result.ok, failures(result)
    return result


def _inspected(run_dir: Path) -> dict[str, list[str]]:
    done = subprocess.run(
        [sys.executable, "-m", "grida.fx", "inspect", str(run_dir), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    steps = json.loads(done.stdout)["run"]["steps"]
    return {step["id"]: sorted(file["path"] for file in step["files"]) for step in steps}


def _contexts(run_dir: Path) -> dict[str, dict[str, Any]]:
    return {
        context["node_id"] or "workflow": context for context in view_contexts(run_dir).contexts
    }


# ---------------------------------------------------------------- the run view


def test_the_run_view_names_every_file_where_fx_placed_it(flow: RunResult) -> None:
    view = project_run(flow.run_dir)

    projected = {
        node.node_id: sorted(artifact.artifact_ref for artifact in node.artifacts)
        for node in view.nodes
        if node.state == "succeeded"
    }
    assert projected == _inspected(flow.run_dir)
    assert projected["draw#2"] == ["files/draw#2/image.png"]
    assert projected["words['lantern'].loud#1"] == ["files/words__lantern__.loud/text.txt"]
    assert verify_run(flow.run_dir) == []
    assert view.kind == "stage-gen-run-view-v1" and view.schema_version == 3
    assert view.run_state == "succeeded" and view.known_cost_usd == 0
    draw = next(node for node in view.nodes if node.node_id == "draw#1")
    assert (draw.operation, draw.model, draw.provider) == ("image.generate", *ROUTE.split("@"))
    assert draw.archetype == "image" and draw.title == "Draw a lantern"


def test_a_run_is_told_by_its_plan_kind_and_its_mode(flow: RunResult, tmp_path: Path) -> None:
    assert is_fx_run(flow.run_dir) and is_stand_in(flow.run_dir)
    other = tmp_path / "other-run"
    other.mkdir()
    (other / "plan.json").write_text(json.dumps({"kind": "other-graph-v2"}), encoding="utf-8")
    assert not is_fx_run(other)


def test_placed_names_follow_fx(tmp_path: Path) -> None:
    png = {"kind": "image/png", "digest": "0" * 64}
    assert placed_path("draw#2", "draw", "image", png, 0, 1) == "files/draw#2/image.png"
    assert placed_path("draw#1.3", "draw", "image", png, 0, 1) == "files/draw#1.3/image.png"
    keyed = {**png, "key": "a/../hero.png"}
    assert placed_path("e['ada'].d#1", "e['ada'].d", "images", keyed, 0, 2) == (
        "files/e__ada__.d/images/a/_/hero.png"
    )
    assert placed_path("x#1", "x", "image", png, 1, 2) == "files/x/image/1.png"
    long = "é" * 200
    capped = placed_path(f"{long}#1", long, "image", png, 0, 1).split("/")[1]
    assert len(capped.encode()) <= 255 and "~" in capped


def test_a_cancelled_run_and_its_spend(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs/cancelled"
    run_dir.mkdir(parents=True)
    plan = {
        "kind": "fx-graph-v1",
        "workflow": {"id": "flow", "title": "Flow", "file": "flow.yaml"},
        "plan": "a" * 64,
        "steps": {"draw": {"title": "Draw", "description": None, "uses": "x", "view": False}},
        "instances": [
            {
                "id": "draw#1",
                "path": "draw",
                "step": "draw",
                "uses": "fx/image.generate@1",
                "take": [1],
                "state": "planned",
                "routes": {"image.generate": {"route": ROUTE, "fingerprint": "b" * 64}},
                "reads": [],
                "price": {"low_usd": 0.18, "high_usd": 0.25},
            }
        ],
    }
    (run_dir / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    envelope = {"kind": "fx-run-events-v1", "invocation_id": "i", "plan": "a" * 64}
    events: list[dict[str, Any]] = [
        {**envelope, "event": "run_started", "offset_ms": 0},
        {
            **envelope,
            "event": "node_started",
            "offset_ms": 1,
            "id": "draw#1",
            "path": "draw",
            "step": "draw",
            "take": [1],
            "routes": {"image.generate": ROUTE},
            "with": {},
        },
        {**envelope, "event": "call", "offset_ms": 2, "id": "draw#1", "cost_usd": 0.2},
        {**envelope, "event": "run_cancelled", "offset_ms": 3, "charged_usd": 0.2},
    ]
    lines = "".join(json.dumps(event) + "\n" for event in events)
    # A last line the run never finished is left out.
    (run_dir / "events.jsonl").write_text(lines + '{"event": "node_fini', encoding="utf-8")

    assert len(read_events(run_dir)) == 4
    view = project_run(run_dir)
    assert view.run_state == "canceled" and view.known_cost_usd == 0.2
    (draw,) = view.nodes
    assert (draw.state, draw.known_cost_usd, draw.provider_operations) == ("failed", 0.2, 1)
    assert draw.error == "the run ended before this step finished"


# ---------------------------------------------------------------- the view contexts


def test_step_views_read_their_step(flow: RunResult) -> None:
    views = view_contexts(flow.run_dir)
    contexts = _contexts(flow.run_dir)
    assert set(contexts) == {"draw#1", "draw#2", "loud#1", "measure#1", "workflow"}
    for context in views.contexts:
        assert context["kind"] == VIEW_CONTEXT_KIND
        assert views.templates[context["template"]].is_file()

    draw = contexts["draw#2"]
    assert draw["step"]["title"] == "Draw a lantern"
    assert (draw["step"]["take"], draw["step"]["cost_usd"]) == (2, 0)
    assert draw["step"]["with"]["prompt"] == "a lantern"
    assert draw["inputs"] == {}
    assert draw["run"] == {
        "id": flow.run_dir.name,
        "workflow": "flow",
        "status": "succeeded",
        "cost_usd": 0,
    }
    image = draw["outputs"]["image"]
    assert image["ref"] == f"views/files/{image['digest']}.png"
    assert views.files[image["ref"]] == flow.run_dir / "files/draw#2/image.png"
    assert (image["facts"]["width"], image["facts"]["has_alpha"]) == (64, True)
    generic = views.templates[draw["template"]].read_text(encoding="utf-8")
    assert 'from "/_views/view.js"' in generic and "<title>Pictures</title>" in generic

    loud = contexts["loud#1"]
    assert views.templates[loud["template"]].read_text(encoding="utf-8") == WORDS
    assert loud["template"] == f"views/{hashlib.sha256(WORDS.encode()).hexdigest()}.html"
    assert loud["outputs"]["text"]["kind"] == "text/plain"


def test_a_json_output_is_inlined_and_an_input_is_found_in_the_stand_in_store(
    flow: RunResult,
) -> None:
    views = view_contexts(flow.run_dir)
    measure = _contexts(flow.run_dir)["measure#1"]
    assert "<title>Data</title>" in views.templates[measure["template"]].read_text("utf-8")
    assert measure["outputs"]["size"]["value"] == {"width": 40, "height": 30}
    picture = measure["inputs"]["image"]
    assert (picture["facts"]["width"], picture["facts"]["height"]) == (40, 30)
    plan = read_plan(flow.run_dir)
    store = store_of(flow.run_dir, plan)
    assert store.name == "stand-in" and store.parent == (flow.run_dir.parents[2] / "cache")
    source = find_file(flow.run_dir, picture["digest"], plan)
    assert source == store / "files" / picture["digest"][:2] / picture["digest"]
    assert views.files[picture["ref"]] == source


def test_the_workflow_view_reads_the_whole_run(flow: RunResult) -> None:
    views = view_contexts(flow.run_dir)
    whole = _contexts(flow.run_dir)["workflow"]
    assert whole["scope"] == "workflow" and whole["node_id"] is None
    assert views.templates[whole["template"]].read_text(encoding="utf-8") == WHOLE
    instances = whole["steps"]["words"]["instances"]
    assert [instance["key"] for instance in instances] == ["harbour", "lantern"]
    loud = instances[1]["steps"]["loud"]
    assert (loud["title"], loud["status"]) == ("Shout it", "succeeded")
    assert views.files[loud["outputs"]["text"]["ref"]].read_text(encoding="utf-8") == "LANTERN"
    assert whole["outputs"]["image"]["kind"] == "image/png"
    assert whole["run"]["status"] == "succeeded"


def test_a_view_outside_the_home_or_through_a_link_is_not_shown(
    flow: RunResult, tmp_path: Path
) -> None:
    project = tmp_path / "project"
    shutil.copytree(flow.run_dir.parents[2], project, symlinks=True)
    run_dir = project / flow.run_dir.relative_to(flow.run_dir.parents[2])
    assert workflow_home(run_dir, read_plan(run_dir)) == project.resolve()
    outside = tmp_path / "outside.html"
    outside.write_text(WORDS, encoding="utf-8")
    (project / "views/words.html").unlink()
    (project / "views/words.html").symlink_to(outside)
    workflow = (project / "flow.yaml").read_text(encoding="utf-8")
    (project / "flow.yaml").write_text(
        workflow.replace("view: ./views/whole.html", "view: ../outside.html"), encoding="utf-8"
    )
    # The step's view is read from the plan, the workflow's from its file.
    shown = _contexts(run_dir)
    assert "loud#1" not in shown and "workflow" not in shown
    assert {"draw#1", "draw#2", "measure#1"} <= set(shown)


SEVERAL = """\
fx: workflow/v1
id: several
title: Several
steps:
  sketch:
    uses: ./nodes/several.py#sketch
    view: true
  assemble:
    uses: ./nodes/several.py#assemble
    view: true
"""
SEVERAL_NODES = """\
from PIL import Image

from grida.fx import Ctx, node


@node("sketch", outputs={"canonical": "image/png", "bundle": "json"})
def sketch(ctx: Ctx) -> dict:
    picture = Image.new("RGBA", (8, 8), (200, 120, 40, 255))
    return {"canonical": ctx.out.png(picture), "bundle": ctx.out.json({"views": 1})}


@node("assemble", outputs={"model": "model/gltf-binary", "record": "json"})
def assemble(ctx: Ctx) -> dict:
    model = ctx.out.bytes(b"glTF" + bytes(8), "model/gltf-binary")
    return {"model": model, "record": ctx.out.json({"parts": 2})}
"""


def test_a_generic_view_follows_its_kinds_not_its_port_names(tmp_path: Path) -> None:
    """A run records ports in sorted order, so ``view: true`` picks by kind: a picture beside
    data shows pictures though its port sorts after the data, and data beside a model still
    shows the data."""

    project = write_project(tmp_path / "project", runs="runs", cache="cache", workflows=())
    (project / "nodes").mkdir()
    (project / "nodes/several.py").write_text(SEVERAL_NODES, encoding="utf-8")
    (project / "several.yaml").write_text(SEVERAL, encoding="utf-8")
    result = run("several.yaml", cwd=project)
    assert result.ok, failures(result)
    finished = {
        event["id"]: list(event["outputs"])
        for event in read_events(result.run_dir)
        if event.get("event") == "node_finished"
    }
    assert finished["sketch#1"] == ["bundle", "canonical"]
    assert finished["assemble#1"] == ["model", "record"]

    views = view_contexts(result.run_dir)
    contexts = _contexts(result.run_dir)
    sketch = views.templates[contexts["sketch#1"]["template"]].read_text(encoding="utf-8")
    assert "<title>Pictures</title>" in sketch
    assemble = views.templates[contexts["assemble#1"]["template"]].read_text(encoding="utf-8")
    assert "<title>Data</title>" in assemble
