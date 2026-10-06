"""Looping parallax through FX, offline: placement reruns only the compose step."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from grida.fx import RunResult, run_async
from PIL import Image

from stage_gen.media.codec import encode_png
from tests.unit._fx import caches, scratch_project, verify


def _source() -> bytes:
    image = Image.new("RGBA", (8, 4), "#182d47")
    for x in range(4):
        for y in range(4):
            image.putpixel((x, y), (80, 120, 160, 255))
    return encode_png(image)


def _inputs(tmp_path: Path, name: str, **layer: Any) -> Path:
    (tmp_path / "clouds.png").write_bytes(_source())
    document = {
        "canvas": {"width": 32, "height": 8},
        "layers": [{"layer_id": "clouds", "file": "clouds.png", "repeat_y": True, **layer}],
    }
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document))
    return path


async def _run(project: Path, inputs: Path) -> RunResult:
    return await run_async("looping-parallax", input_files=[inputs], cwd=project)


async def test_moving_a_layer_reuses_its_repeat_and_recomposes(tmp_path: Path) -> None:
    project = scratch_project(tmp_path)
    first = await _run(project, _inputs(tmp_path, "first.yaml"))
    moved = await _run(project, _inputs(tmp_path, "moved.yaml", offset_x=3.0))

    assert first.ok and moved.ok
    cached = caches(moved)
    assert cached["layer['clouds'].mirror#1"] == "hit"
    assert cached["compose#1"] == "miss"
    manifest = json.loads(moved.outputs["manifest"].read_bytes())
    (layer,) = manifest["layers"]
    assert (layer["asset_ref"], layer["offset_x"], layer["construction"]) == (
        "parallax/layers/clouds.png",
        3.0,
        "mirror_repeat",
    )
    assert (layer["width"], layer["height"]) == (16, 8)
    assert verify(moved.run_dir) == []
