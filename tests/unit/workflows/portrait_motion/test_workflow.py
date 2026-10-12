"""Portrait motion through FX, offline: every stage, every refusal, and the example.

The sample's stand-in answers each paid call from the drawn character's own colours and
returns the sheet as it was sent, so the whole chain runs; a test swaps one answer to make a
stage refuse.
"""

from __future__ import annotations

import json
import runpy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from grida.fx import Answer, RunResult, StandInCall, run_async
from PIL import Image

from fx_games.examples import ImportRequest, MadeBy, currency, verify, write_example
from fx_games.workflows._registry import load_code
from tests.unit._fx import caches, schema_of, scratch_project

MAKE = runpy.run_path(
    str(
        Path(__file__).resolve().parents[4]
        / "src/fx_games/workflows/portrait_motion/inputs/make_inputs.py"
    )
)


class StandIn:
    """The sample's stand-in, counting calls, with one structured answer replaceable."""

    def __init__(self, replace: Mapping[str, Any] | None = None) -> None:
        self.replace = dict(replace or {})
        self.calls: list[str] = []

    def __call__(self, call: StandInCall) -> Any:
        if call.capability == "structured.generate":
            schema = MAKE["schema_name"](schema_of(call))
            self.calls.append(schema)
            if schema in self.replace:
                return Answer.json(self.replace[schema])
        elif call.capability == "image.edit":
            self.calls.append("sheet")
        return MAKE["stand_in"](call)


async def _run(tmp_path: Path, inputs: str, stand_in: StandIn, run: str) -> RunResult:
    folder = tmp_path / "inputs"
    MAKE["write_inputs"](folder)
    MAKE["write_whole"](folder)
    project = scratch_project(tmp_path / "project")
    return await run_async(
        "portrait-motion",
        input_files=[folder / inputs],
        cwd=project,
        run_dir=project / "runs" / run,
        stand_in=stand_in,
    )


def _result(outcome: RunResult) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (outcome.run_dir / "outputs/result.json").read_text(encoding="utf-8")
    )
    return document


async def test_the_face_goes_back_on_the_sprite_unchanged_outside_its_patches(
    tmp_path: Path,
) -> None:
    stand_in = StandIn()
    outcome = await _run(tmp_path, "face.yaml", stand_in, "face")

    assert outcome.ok, outcome.failures
    assert stand_in.calls == ["location", "admission", "sheet", "geometry", "quality"]
    assert _result(outcome)["status"] == "complete"
    outputs = outcome.run_dir / "outputs"
    with Image.open(outputs / "states/rest--rest.png") as rest:
        assert rest.size == (900, 1400) and rest.mode == "RGBA"
    assert len(list((outputs / "states").glob("*.png"))) == 9
    assert len(list((outputs / "patches").glob("*.png"))) == 6
    manifest = json.loads((outputs / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "portrait-face-motion-v2"
    assert manifest["patch_application"] == "replace_selected_rgb_preserve_original_alpha"


async def test_a_whole_portrait_keeps_its_reviewed_combinations(tmp_path: Path) -> None:
    stand_in = StandIn()
    outcome = await _run(tmp_path, "whole.yaml", stand_in, "whole")

    assert outcome.ok, outcome.failures
    assert stand_in.calls == ["admission", "sheet", "geometry", "quality"]
    outputs = outcome.run_dir / "outputs"
    assert _result(outcome)["status"] == "complete"
    assert not (outputs / "patches").exists()
    assert len(list((outputs / "states").glob("*.png"))) == 9


async def test_running_again_pays_for_nothing(tmp_path: Path) -> None:
    first = StandIn()
    assert (await _run(tmp_path, "face.yaml", first, "one")).ok
    again = StandIn()
    outcome = await _run(tmp_path, "face.yaml", again, "two")

    assert outcome.ok and again.calls == []
    assert set(caches(outcome).values()) == {"hit"}


@pytest.mark.parametrize(
    ("replace", "refused_at", "calls"),
    [
        (
            {"location": {"status": "not_locatable", "bbox_xyxy": None, "reason": "No face."}},
            "face",
            ["location"],
        ),
        (
            {
                "admission": {
                    **MAKE["admission"](),
                    "features": [
                        {**feature, "route": "unsupported", "reason": "uncertain_boundary"}
                        for feature in MAKE["admission"]()["features"]
                    ],
                }
            },
            "admission",
            ["location", "admission"],
        ),
        (
            {
                "quality": {
                    **MAKE["quality"](["mouth"]),
                    "status": "fail",
                    "features": [
                        {"feature_id": f, "status": "fail", "reason": "A ghost lid survives."}
                        for f in ("canvas_left_eye", "canvas_right_eye", "mouth")
                    ],
                }
            },
            "quality",
            ["location", "admission", "sheet", "geometry", "quality"],
        ),
    ],
)
async def test_a_refusal_ends_the_chain_and_names_its_stage(
    tmp_path: Path, replace: dict[str, Any], refused_at: str, calls: list[str]
) -> None:
    stand_in = StandIn(replace)
    outcome = await _run(tmp_path, "face.yaml", stand_in, "refused")

    assert outcome.ok, outcome.failures
    assert stand_in.calls == calls
    result = _result(outcome)
    assert (result["status"], result["refused_at"]) == ("refused", refused_at)
    assert result["accepted_features"] == []
    assert not (outcome.run_dir / "outputs/patches").exists()


async def test_an_answer_outside_the_schema_fails_its_call(tmp_path: Path) -> None:
    stand_in = StandIn({"admission": {"schema_version": 1, "features": []}})
    outcome = await _run(tmp_path, "face.yaml", stand_in, "malformed")

    assert not outcome.ok
    assert stand_in.calls.count("admission") == 1
    assert outcome.failures["draw.admission#1"].code == "call_failed"


async def test_an_incoherent_decision_is_drawn_again(tmp_path: Path) -> None:
    stand_in = StandIn({"admission": {**MAKE["admission"](), "subject_count": 2}})
    outcome = await _run(tmp_path, "face.yaml", stand_in, "incoherent")

    assert not outcome.ok
    assert stand_in.calls.count("admission") == 6


async def test_an_accepted_face_imports_as_an_example(tmp_path: Path) -> None:
    outcome = await _run(tmp_path, "face.yaml", StandIn(), "example")
    assert outcome.ok, outcome.failures

    code = load_code("portrait-motion")
    assert code.import_example is not None and code.owns_run(outcome.run_dir)
    request = ImportRequest(
        example_id="face",
        made_by=MadeBy(kind="workflow", id="portrait-motion"),
        base=tmp_path,
        runs=(outcome.run_dir,),
        out=tmp_path / "store/portrait-motion/face",
    )
    example = code.import_example(request)

    assert example.importer == "fx_run"
    assert example.outputs["rig"]["combinations_verified"] == 9
    assert example.outputs["face"]["kind"] == "animation"
    assert example.metrics["features_accepted"] == 3
    assert currency(example, code.type_ids()) == "current"
    pin = write_example(request.out, example, request.figures(example))
    assert verify(request.out, pin) == []
