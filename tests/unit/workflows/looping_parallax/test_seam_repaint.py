"""Seam-repainted layers: admitted first, repainted through the wrap, else reflected.

The paid edit is answered by a stand-in at the capability, so the seam node's real request
and FX's checks of the answer run, and no call leaves the machine.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from grida.fx import Answer, Plan, RunResult, StandInCall, plan_async, run_async
from PIL import Image

from fx_games.media.codec import decode_rgba, encode_png
from tests.unit._fx import dispatch, finished, instances, problems, scratch_project

WIDTH, HEIGHT = 2048, 512
Painter = Callable[[Image.Image, Image.Image], Image.Image]


def _band(period: float) -> bytes:
    """An opaque band that varies smoothly across x; it loops only when ``period`` divides it."""

    image = Image.new("RGBA", (WIDTH, HEIGHT))
    pixels = image.load()
    assert pixels is not None
    for x in range(WIDTH):
        green = round(60 + 40 * math.sin(2 * math.pi * x / period))
        for y in range(HEIGHT):
            pixels[x, y] = (y // 2, green, 128, 255)
    return encode_png(image)


def _paint_through(conditioning: Image.Image, mask: Image.Image) -> Image.Image:
    """Carry each row straight across the masked span, as a provider that did its job would.

    The mask follows the edit endpoint's convention: transparent is editable.
    """

    editable = [x for x in range(mask.width) if mask.getpixel((x, 0))[3] == 0]  # type: ignore[index]
    left, right = editable[0] - 1, editable[-1] + 1
    painted = conditioning.copy()
    source = conditioning.load()
    target = painted.load()
    assert source is not None and target is not None
    for y in range(conditioning.height):
        a, b = source[left, y], source[right, y]
        assert isinstance(a, tuple) and isinstance(b, tuple)
        for x in range(left + 1, right):
            t = (x - left) / (right - left)
            target[x, y] = tuple(round(p + (q - p) * t) for p, q in zip(a, b, strict=True))
    return painted


def _project(tmp_path: Path, source: bytes, **layer: Any) -> Path:
    scratch_project(tmp_path)
    (tmp_path / "band.png").write_bytes(source)
    inputs = {
        "canvas": {"width": 640, "height": 360},
        "layers": [
            {
                "layer_id": "band",
                "file": "band.png",
                "parallax": 0.5,
                "loop_construction": "seam_repaint",
                **layer,
            }
        ],
    }
    path = tmp_path / "inputs.yaml"
    path.write_text(yaml.safe_dump(inputs))
    return path


async def _plan(tmp_path: Path, source: bytes, **layer: Any) -> Plan:
    inputs = _project(tmp_path, source, **layer)
    return await plan_async("looping-parallax", input_files=[inputs], cwd=tmp_path)


async def _run(
    tmp_path: Path, source: bytes, run_dir: Path, paint: Painter | None
) -> tuple[RunResult, list[StandInCall]]:
    """Run the layer, each edit answered by ``paint`` over what it was sent (``None`` sends the
    conditioning back untouched)."""

    sent: list[StandInCall] = []

    def edit(call: StandInCall) -> Answer:
        sent.append(call)
        conditioning = decode_rgba(call.request["image"].read_bytes())
        mask = decode_rgba(call.request["mask"].read_bytes())
        returned = conditioning if paint is None else paint(conditioning, mask)
        return Answer(files={"image": encode_png(returned)})

    inputs = _project(tmp_path, source)
    result = await run_async(
        "looping-parallax",
        input_files=[inputs],
        cwd=tmp_path,
        run_dir=run_dir,
        stand_in=dispatch({"image.edit": edit}),
    )
    return result, sent


def _verdict(result: RunResult, instance: str) -> str:
    verdict: str = finished(result, instance)["facts"]["verdict"]
    return verdict


def _layer(result: RunResult) -> dict[str, Any]:
    manifest = json.loads(result.outputs["manifest"].read_bytes())
    assert manifest["kind"] == "parallax-background-v2"
    layer: dict[str, Any] = manifest["layers"][0]
    return layer


async def test_a_repaint_through_the_wrap_keeps_the_drawn_period_and_is_reused(
    tmp_path: Path,
) -> None:
    planned = await _plan(tmp_path, _band(period=700))
    assert planned.ok, planned.problems
    result, sent = await _run(tmp_path, _band(period=700), tmp_path / "runs/first", _paint_through)

    assert result.ok, result.failures
    assert len(sent) == 1
    assert sent[0].request["size"] == f"1536x{HEIGHT}"
    assert "hard cut" in sent[0].request["prompt"]
    assert _verdict(result, "layer['band'].seam_ok#1") == "accept"
    layer = _layer(result)
    assert (layer["construction"], layer["width"], layer["height"]) == (
        "seam_repaint",
        WIDTH,
        HEIGHT,
    )

    again, sent_again = await _run(
        tmp_path, _band(period=700), tmp_path / "runs/again", _paint_through
    )
    assert again.ok
    assert sent_again == []


async def test_a_repaint_that_leaves_the_cut_is_redrawn_once_then_reflected(
    tmp_path: Path,
) -> None:
    result, sent = await _run(tmp_path, _band(period=700), tmp_path / "run", None)

    assert result.ok, result.failures
    assert len(sent) == 2
    assert _verdict(result, "layer['band'].seam_ok#1") == "reject"
    assert _verdict(result, "layer['band'].seam_ok#2") == "reject"
    layer = _layer(result)
    assert (layer["construction"], layer["width"]) == ("mirror_repeat", WIDTH * 2)


async def test_a_layer_that_already_loops_is_published_untouched_without_a_call(
    tmp_path: Path,
) -> None:
    source = _band(period=1024)
    result, sent = await _run(tmp_path, source, tmp_path / "run", _paint_through)

    assert result.ok, result.failures
    assert sent == []
    assert result.outputs["layers"]["band"].read_bytes() == source
    assert _layer(result)["construction"] == "admitted"


async def test_the_brief_is_identity_and_placement_is_not(tmp_path: Path) -> None:
    source = _band(period=700)

    def repaint(planned: Plan) -> str | None:
        found = next(i for i in instances(planned) if i["id"] == "layer['band'].repaint#1")
        identity: str | None = found["identity"]
        return identity

    base = repaint(await _plan(tmp_path, source))
    described = repaint(await _plan(tmp_path, source, description="Low green hills."))
    moved = repaint(await _plan(tmp_path, source, offset_y=12.0))
    assert base is not None
    assert described != base
    assert moved == base


async def test_seam_repaint_is_refused_where_it_cannot_run(tmp_path: Path) -> None:
    upright = await _plan(tmp_path, _band(period=700), repeat_y=True)
    assert "repeats on x only" in problems(upright)
    narrow = encode_png(Image.new("RGBA", (1024, HEIGHT), (10, 20, 30, 255)))
    refused = await _plan(tmp_path, narrow)
    assert "1536 px seam window" in problems(refused)
