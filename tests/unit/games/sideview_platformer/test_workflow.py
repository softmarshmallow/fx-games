"""Bellweather's builder through FX, offline: the plan, its parts, a whole run, the package.

Each run test copies the game's FX project (``fx.yaml``, the lock, ``pipeline/nodes`` and
the builder) and the default package into a scratch folder, because a package's references are
project files. Paid calls are stand-ins that answer what the game's judges admit, recognised
by the brief they were sent: cut-outs, one figure per motion or portrait cell, a climbing
roster of narrow subjects, a portal pair, layers that already loop, the packed atlas restated
in one material, the interface sheets the gates promise, a stored terrain composition the
map's validator accepts, and an accepting review.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from grida.fx import Answer, FxError, InputFile, Plan, RunResult, StandInCall
from grida.fx import plan as plan_fx
from grida.fx import run as run_fx
from PIL import Image, ImageDraw

from bellweather_pipeline.briefs import EDITABLE_SPAN
from bellweather_pipeline.input import resolve_game_package
from bellweather_pipeline.motion_contract import motion_atlas_geometry
from bellweather_pipeline.prepared_manifest import runtime_artifact_paths, verify_prepared_runtime
from demo_game_collection.resources import bundled_music_path
from demo_game_tools.kits.sideview_terrain import PAINT_CANVAS_SIZE, terrain_atlas_paint_target
from demo_game_tools.kits.ui_art.nodes import UI_SHEET_ROLES, sheet_family
from demo_game_tools.media.ui import (
    INVENTORY_PANEL_HEIGHT,
    INVENTORY_PANEL_LEFT,
    INVENTORY_PANEL_TOP,
    INVENTORY_PANEL_WIDTH,
)
from tests.unit._fx import (
    ceiling,
    deliver,
    failures,
    first_takes,
    game_project,
    instances,
    schema_of,
)
from tests.unit._ui_atlas_fixture import ui_sheet

REPOSITORY = Path(__file__).resolve().parents[4]
GAME = REPOSITORY / "godot/games/bellweather"
BUILDER = "pipeline/workflow.py:build"
FFPROBE = shutil.which("ffprobe")
needs_ffprobe = pytest.mark.skipif(FFPROBE is None, reason="the track record measures with it")

#: Compositions each shipped map's validator accepts: the ones the last accepted world drew.
DESIGNS: dict[str, dict[str, object]] = {
    "sunpetal-crossing": {
        "design_notes": "A village lane with one hollow and a gentle rise.",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 6},
            {"kind": "hollow", "width": 10, "depth": 1},
            {"kind": "run", "len": 14},
            {
                "kind": "hop_chain",
                "count": 1,
                "jump_rise": 1,
                "gap": 2,
                "platform_width": 4,
                "dir": "up",
            },
            {
                "kind": "hop_chain",
                "count": 1,
                "jump_rise": 1,
                "gap": 2,
                "platform_width": 4,
                "dir": "down",
            },
            {"kind": "run", "len": 8},
            {"kind": "slope", "rise": 1, "grade": "gentle", "dir": "up"},
            {"kind": "run", "len": 8},
        ],
    },
    "crowncrag-road": {
        "design_notes": "Three climbs around a stack of shelves.",
        "start_height_tiles": 3,
        "chunks": [
            {"kind": "run", "len": 3},
            {"kind": "perch", "platform_width": 2, "climb_rise": 4, "variant": "bellroot_ladder"},
            {
                "kind": "shelves",
                "tiers": 3,
                "decks": 3,
                "platform_width": 6,
                "gap": 5,
                "lean": "right",
            },
            {
                "kind": "perch",
                "platform_width": 3,
                "climb_rise": 4,
                "variant": "shrine_rope_ladder",
            },
            {"kind": "run", "len": 1},
            {"kind": "perch", "platform_width": 3, "climb_rise": 4, "variant": "bellrope_climb"},
        ],
    },
}


def bellweather_project(tmp_path: Path) -> Path:
    """The game's FX project in a scratch folder, with the default package in ``inputs``."""

    project = game_project("bellweather", tmp_path)
    shutil.copytree(GAME / "inputs/default", project / "inputs/default")
    return project


def plan(project: Path, package: str = "inputs/default", **arguments: str) -> Plan:
    return plan_fx(BUILDER, cwd=project, arguments={"package": package, **arguments})


def steps_of(planned: Plan) -> set[str]:
    return {row["step"] for row in first_takes(planned)}


# ------------------------------------------------------------------------------- stand-ins


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _canvas(size: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    width, height = (int(side) for side in size.split("x"))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _cells(size: str, columns: int, rows: int, required: int) -> bytes:
    """One figure in each required cell of a row-major grid."""

    image, draw = _canvas(size)
    cell_width, cell_height = image.width / columns, image.height / rows
    for index in range(required):
        row, column = divmod(index, columns)
        draw.ellipse(
            (
                round(column * cell_width + cell_width * 0.2),
                round(row * cell_height + cell_height * 0.2),
                round((column + 1) * cell_width - cell_width * 0.2),
                round((row + 1) * cell_height - cell_height * 0.2),
            ),
            fill=(100, 170, 230, 255),
        )
    return _png(image)


def _cutout(size: str) -> bytes:
    return _cells(size, 1, 1, 1)


def _climbables(size: str, roles: list[str]) -> bytes:
    """A ladder four times taller than wide and a rope fifteen, at one height, in a row."""

    image, draw = _canvas(size)
    column = image.width / len(roles)
    height = image.height * 6 // 10
    top = (image.height - height) // 2
    for index, role in enumerate(roles):
        width = height // (4 if role == "ladder" else 15)
        centre = round(column * (index + 0.5))
        draw.rectangle(
            (centre - width // 2, top, centre + width // 2, top + height), fill=(120, 90, 60, 255)
        )
    return _png(image)


def _layer(size: str, *, transparent: bool) -> bytes:
    """A layer that already loops: every column is the same."""

    image, draw = _canvas(size)
    for y in range(image.height):
        if transparent and y < image.height * 6 // 10:
            continue
        shade = 90 + y * 120 // image.height
        draw.line((0, y, image.width, y), fill=(shade // 2, shade, shade // 3, 255))
    return _png(image)


def _atlas() -> bytes:
    """The packed atlas target restated in one material, shaded by its own luminance."""

    with Image.open(io.BytesIO(terrain_atlas_paint_target())) as opened:
        image = opened.convert("RGB")
    pixels = image.load()
    assert pixels is not None
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = cast(tuple[int, int, int], pixels[x, y])
            shade = 0.55 + 0.75 * (red * 0.299 + green * 0.587 + blue * 0.114) / 255.0
            variation = ((x // 19 + y // 23) % 9) - 4
            pixels[x, y] = cast(
                tuple[int, int, int],
                tuple(
                    max(0, min(255, round(channel * shade) + variation))
                    for channel in (132, 86, 50)
                ),
            )
    return _png(image)


def _inventory() -> bytes:
    image, draw = _canvas("1536x1024")
    draw.rectangle(
        (
            INVENTORY_PANEL_LEFT,
            INVENTORY_PANEL_TOP,
            INVENTORY_PANEL_LEFT + INVENTORY_PANEL_WIDTH - 1,
            INVENTORY_PANEL_TOP + INVENTORY_PANEL_HEIGHT - 1,
        ),
        fill=(100, 170, 230, 251),
    )
    return _png(image)


class StandIns:
    """Every paid call the default package makes, answered offline."""

    def __init__(self, project: Path, *, rejected_designs: int = 0) -> None:
        self.package = resolve_game_package(project / "inputs/default")
        self.calls: Counter[str] = Counter()
        self.prompts: dict[str, list[str]] = {}
        #: How many compositions of a map with climbables the validator refuses before the
        #: stored one is answered.
        self.rejected_designs = rejected_designs
        self._atlas: bytes | None = None
        self._templates = {
            hashlib.sha256(sheet_family(role).template(role)).hexdigest(): name
            for name, role in UI_SHEET_ROLES.items()
        }

    def __call__(self, call: StandInCall) -> Answer:
        if call.capability in ("image.generate", "image.edit"):
            kind, data = self._paint(call.request)
            self._note(kind, str(call.request["prompt"]))
            return Answer(files={"image": data})
        if call.capability == "structured.generate":
            return self._structured(call)
        if call.capability == "music.generate":
            self._note("track", str(call.request["prompt"]))
            return Answer(files={"audio": bundled_music_path().read_bytes()})
        raise AssertionError(f"unexpected call: {call!r}")

    def _note(self, kind: str, prompt: str) -> None:
        self.calls[kind] += 1
        self.prompts.setdefault(kind, []).append(prompt)

    def _paint(self, request: Mapping[str, Any]) -> tuple[str, bytes]:
        prompt = str(request["prompt"])
        size = str(request["size"])
        pictures = [request.get("image"), *(request.get("references") or [])]
        roles = {
            self._templates.get(picture.digest)
            for picture in pictures
            if isinstance(picture, InputFile)
        } - {None}
        if request.get("mask") is not None:
            return "loop", request["image"].read_bytes()
        if size == PAINT_CANVAS_SIZE:
            self._atlas = self._atlas or _atlas()
            return "atlas", self._atlas
        if roles:
            return "ui", ui_sheet(str(roles.pop()))
        if "inventory panel" in prompt:
            return "inventory", _inventory()
        if "dialogue portrait atlas" in prompt:
            grid = re.search(r"strict (\d+)-column by (\d+)-row", prompt)
            assert grid is not None
            cells = len(re.findall(r"cell \d+:", prompt))
            return "dialogue", _cells(size, int(grid[1]), int(grid[2]), cells)
        if "side-view motion atlas" in prompt:
            found = re.search(r"for (player|mob|npc) \S+, state (\w+)\.", prompt)
            assert found is not None
            geometry = motion_atlas_geometry(found[1], found[2])  # type: ignore[arg-type]
            return "strip", _cells(size, geometry.columns, geometry.rows, geometry.required_cells)
        if "climbing routes" in prompt:
            return "climbable", _climbables(size, re.findall(r"\d+\. (ladder|rope) —", prompt))
        if "portal structures" in prompt:
            return "portal", _cells(size, 2, 1, 2)
        if "horizontally seamless repeat unit" in prompt:
            transparent = request.get("background") == "transparent"
            return "layer", _layer(size, transparent=transparent)
        return "cutout", _cutout(size)

    def _structured(self, call: StandInCall) -> Answer:
        fields = set(schema_of(call).get("properties") or {})
        prompt = str(call.request["prompt"])
        if "chunks" in fields:
            self._note("design", prompt)
            game_map = next(m for m in self.package.maps if m.terrain.brief in prompt)
            answer: dict[str, Any] = dict(DESIGNS[game_map.map_id])
            if self.rejected_designs and game_map.climbable is not None:
                self.rejected_designs -= 1
                # A level that leaves a declared climbable unplaced breaks the map's own rules.
                answer = {**answer, "chunks": [{"kind": "run", "len": 4}] * 3}
        elif "verdict" in fields:
            self._note("review", prompt)
            answer = {"verdict": "accept", "confidence": 1.0, "checks": {}, "issues": []}
            answer["evidence"] = "deterministic stand-in"
        else:
            self._note("reading", prompt)
            states = [motion.state for motion in self.package.player.players[0].motions]
            answer = {
                "baseline_state": "idle",
                "states": [
                    {"state": state, "multiplier": 1.0, "evidence": "Drawn at idle's size."}
                    for state in states
                ],
            }
        return Answer.json(answer)


def run(project: Path, stand_ins: StandIns, name: str = "run", **arguments: str) -> RunResult:
    return run_fx(
        BUILDER,
        cwd=project,
        arguments={"package": "inputs/default", **arguments},
        run_dir=project / name,
        stand_in=stand_ins,
    )


# ------------------------------------------------------------------------------- the plan


@pytest.mark.parametrize("variant", ["default", "waves"])
def test_each_shipped_package_plans_inside_its_own_project(variant: str) -> None:
    planned = plan(GAME, f"inputs/{variant}")

    assert planned.ok, planned.problems
    assert planned.document["workflow"]["id"] == "bellweather"
    budget = ceiling(planned)
    assert budget is not None and planned.estimate()[1] <= budget


def test_the_plan_draws_what_the_package_declares_once_each() -> None:
    planned = plan(GAME)
    package = resolve_game_package(GAME / "inputs/default")
    calls = Counter(cap for row in first_takes(planned) for cap in row["routes"])
    strips = sum(len(player.motions) for player in package.player.players)
    strips += sum(len(mob.motions) for mob in package.mobs.mobs)
    actors = len(package.player.players) + len(package.mobs.mobs) + len(package.npcs.npcs)
    catalog = len(package.props.props) + len(package.items.items)
    catalog += 0 if package.projectiles is None else len(package.projectiles.projectiles)
    dialogue = len(package.player.players) + len(package.npcs.npcs)
    layers = sum(len(game_map.layers) for game_map in package.maps)
    presentations = sum(
        (game_map.portal is not None) + (game_map.climbable is not None)
        for game_map in package.maps
    )
    repaints = [i for i in first_takes(planned) if i["step"].endswith(".loop") and i["routes"]]
    # Every concept, strip, NPC world sprite, dialogue atlas, catalog subject, layer, ground
    # atlas, climbable and portal sheet, the inventory panel and each interface sheet; and a
    # seam repaint for each layer whose construction paints one.
    assert len(repaints) == layers
    assert calls["image.edit"] == len(repaints) + (
        actors
        + strips
        + len(package.npcs.npcs)
        + dialogue
        + catalog
        + layers
        + len(package.maps)
        + presentations
        + 1
        + 3
    )
    assert calls["music.generate"] == len(package.soundtrack.tracks)
    # A composition per map, two rebase readings, and a review per map, actor, catalog
    # family and interface sheet.
    families = 2 + (package.projectiles is not None)
    assert calls["structured.generate"] == len(package.maps) * 2 + 2 + actors + families + 4
    assert "package" in steps_of(planned)


def test_every_painting_is_judged_and_drawn_again_at_most_six_times() -> None:
    planned = plan(GAME)
    takes = Counter(row["step"] for row in instances(planned) if row["state"] != "absent")
    painted = [
        row for row in first_takes(planned) if set(row["routes"]) & {"image.edit", "music.generate"}
    ]

    assert painted
    for row in painted:
        if row["step"].endswith(".loop"):
            continue  # a seam repaint is one edit inside its step, refused into a fallback
        assert row["judged_by"], row["step"]
        assert takes[row["step"]] == 6, row["step"]
    designs = [row for row in first_takes(planned) if row["step"].endswith(".terrain.design")]
    assert len(designs) == 2 and {takes[row["step"]] for row in designs} == {3}


def test_a_seam_repaint_is_briefed_for_the_canvas_it_will_see() -> None:
    planned = plan(GAME)
    loops = [row for row in first_takes(planned) if row["step"].endswith(".loop")]

    assert loops
    for row in loops:
        assert EDITABLE_SPAN in row["with"]["prompt"], row["step"]


def test_each_part_builds_its_slice_and_reviews_can_be_left_out() -> None:
    world = steps_of(plan(GAME, part="world"))
    content = steps_of(plan(GAME, part="content"))
    quiet = steps_of(plan(GAME, part="content", reviews="no"))
    soundtrack = steps_of(plan(GAME, part="soundtrack"))

    assert all(step.startswith(("maps.", "files")) for step in world)
    assert not any(step.startswith(("maps.", "soundtrack.")) for step in content)
    assert all(step.startswith(("soundtrack.", "files")) for step in soundtrack)
    assert {step for step in content if step.endswith(".review")}
    assert not {step for step in quiet if step.endswith(".review")}
    assert "package" not in world | content | soundtrack


def test_a_part_that_does_not_exist_is_refused() -> None:
    with pytest.raises(FxError, match="part is one of all, world, content, soundtrack"):
        plan(GAME, part="maps")


def test_the_package_step_publishes_exactly_the_runtime_closure() -> None:
    planned = plan(GAME)
    (package_step,) = [row for row in first_takes(planned) if row["step"] == "package"]
    package = resolve_game_package(GAME / "inputs/default")

    assert set(package_step["with"]["published"]) == set(runtime_artifact_paths(package))


# ------------------------------------------------------------------------------- a whole run


@needs_ffprobe
def test_a_whole_build_runs_offline_into_a_runtime_the_manifest_verifies(tmp_path: Path) -> None:
    project = bellweather_project(tmp_path)
    stand_ins = StandIns(project)

    outcome = run(project, stand_ins)

    assert outcome.ok, failures(outcome)
    folder = tmp_path / "runtime"
    deliver(outcome, folder)
    verified = verify_prepared_runtime(folder)
    assert verified["valid"] is True and verified["game_id"] == "bellweather"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["player"]["calibration"]["baseline_state"] == "idle"
    # Nothing loops badly, so no seam was repainted; every other call ran once.
    assert "loop" not in stand_ins.calls
    assert stand_ins.calls["design"] == 2


@needs_ffprobe
def test_a_rejected_composition_is_composed_again_told_what_failed(tmp_path: Path) -> None:
    project = bellweather_project(tmp_path)
    stand_ins = StandIns(project, rejected_designs=1)

    outcome = run(project, stand_ins, part="world", reviews="no")

    assert outcome.ok, failures(outcome)
    first, *later = stand_ins.prompts["design"]
    told = [prompt for prompt in later if "rejected by the game's own validator" in prompt]
    assert "rejected by the game's own validator" not in first
    assert len(told) == 1 and told[0].endswith("\n\nCompose the map.")


@needs_ffprobe
def test_an_edit_no_drawing_depends_on_redraws_nothing(tmp_path: Path) -> None:
    """After one build, retune what a provider cannot draw: the next build paints nothing.

    The level's shape is composed from the map's brief alone, a loop construction is read by
    the loop alone, and playback and a projectile's magnitude by local steps and reviews.
    """

    project = bellweather_project(tmp_path)
    assert run(project, StandIns(project)).ok
    package = project / "inputs/default"
    for member, old, new in (
        (
            "maps/crowncrag-road.toml",
            "Keep the ground itself almost level",
            "Keep the ground itself perfectly level",
        ),
        (
            "maps/crowncrag-road.toml",
            'loop_construction = "seam_repaint"',
            'loop_construction = "fold_repaint"',
        ),
        ("content/mobs.toml", "frames_per_second = 6", "frames_per_second = 9"),
        ("content/projectiles.toml", "length_units = 0.50", "length_units = 0.60"),
    ):
        path = package / member
        text = path.read_text(encoding="utf-8")
        assert old in text, (member, old)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    again = StandIns(project)

    outcome = run(project, again, "again")

    assert outcome.ok, failures(outcome)
    # One composition of the reshaped level; reviews of what they are now told; nothing drawn.
    assert set(again.calls) <= {"design", "review"}, again.calls
    assert again.calls["design"] == 1
