"""Reading an FX run folder: the run view and the names FX places files at.

The run here is a real FX run of a small workflow in a scratch project, its one paid step
answered by a stand-in: the drawing's first take is opaque, which its judge rejects, so a
second take is drawn and placed in a folder of its own. Every name the projection gives a file
is checked against the engine's own (``inspect --json``).
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from grida.fx import Answer, RunResult, StandInCall, run
from PIL import Image

from stage_gen.runview import (
    find_file,
    is_fx_run,
    is_stand_in,
    placed_path,
    project_run,
    read_events,
    read_plan,
    store_of,
    verify_run,
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
  clean:
    uses: fx/image.check_alpha@1
    judges: draw
    with: { image: "${{ steps.draw.outputs.image }}", expect: transparent }
    on_reject:
      regenerate: { max: 2 }
  loud:
    uses: ./nodes/test_nodes.py#shout
    with: { text: lantern }
  measure:
    title: Measure the picture
    uses: ./nodes/test_nodes.py#measure
    with: { image: "${{ inputs.picture }}" }
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
    assert view.kind == "stage-gen-run-view-v1" and view.schema_version == 4
    assert view.run_state == "succeeded" and view.known_cost_usd == 0
    draw = next(node for node in view.nodes if node.node_id == "draw#1")
    assert (draw.operation, draw.model, draw.provider) == ("image.generate", *ROUTE.split("@"))
    assert draw.title == "Draw a lantern"


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


def test_an_input_is_found_in_the_stand_in_store(flow: RunResult) -> None:
    plan = read_plan(flow.run_dir)
    digest = plan["inputs"]["picture"]["file"]
    store = store_of(flow.run_dir, plan)
    assert store.name == "stand-in" and store.parent == (flow.run_dir.parents[2] / "cache")
    assert find_file(flow.run_dir, digest, plan) == store / "files" / digest[:2] / digest
