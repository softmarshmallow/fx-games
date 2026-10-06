"""Iron Petal Unit's builder through FX, offline: the plan, a whole run, resume, the package.

Each test copies the game's FX project (``fx.yaml``, the lock, ``pipeline/nodes`` and
the builder) into a scratch folder and authors a runner package inside it, because a package's
references are project files. Paid calls are stand-ins that paint what the game's judges
admit: a cut-out at the concept canvas, one figure per motion cell, a sky that already loops,
the packed atlas restated in one material, and MP3s ffmpeg makes at the asked length.
The steps they exercise are described in `godot/games/iron_petal_unit/docs/runner.md`.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from grida.fx import Answer, CallRefused, FxError, Plan, RunResult, StandInCall
from grida.fx import plan as plan_fx
from grida.fx import run as run_fx
from PIL import Image, ImageDraw

from demo_game_tools.kits.sideview_actor.motion_geometry import DEFAULT_MOTION_ATLAS_GEOMETRY
from demo_game_tools.kits.sideview_terrain import PAINT_CANVAS_SIZE, terrain_atlas_paint_target
from iron_petal_unit_pipeline.audio.realizations import (
    GeneratedClipRealization,
    SpokenLineRealization,
)
from iron_petal_unit_pipeline.content import declared_motion_states
from iron_petal_unit_pipeline.manifest import MANIFEST_KIND
from iron_petal_unit_pipeline.runner_request import resolve_runner_package

from ..._fx import (
    by_step,
    ceiling,
    deliver,
    failures,
    finished,
    first_takes,
    game_project,
    instances,
)
from ..._runner_fixture import (
    RUNNER_AVATAR,
    RUNNER_AVATAR_NO_SLIDE,
    RUNNER_GAMEPLAY_NO_DUCK,
    WIDE_FLAT_ROWS,
    chunk_toml,
    painted_over_guide,
    runner_only_package,
)

REPOSITORY = Path(__file__).resolve().parents[4]
GAME = REPOSITORY / "godot/games/iron_petal_unit"
BUILDER = "pipeline/workflow.py:build"
FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="the audio judges measure with ffmpeg")


def runner_project(tmp_path: Path, **options: Any) -> Path:
    """The game's FX project in a scratch folder, with a runner package in ``runner-only``."""

    project = game_project("iron_petal_unit", tmp_path)
    runner_only_package(project, **options)
    return project


def structural(project: Path) -> Path:
    """Select structural ground: one painted chunk per segment instead of the 47-mask atlas."""

    track = project / "runner-only/runner/track.toml"
    track.write_text(
        track.read_text(encoding="utf-8").replace(
            'mode = "terrain-atlas-3x3-minimal-v1"', 'mode = "runner-structural-ground-v1"', 1
        ),
        encoding="utf-8",
    )
    return project


def plan(project: Path, package: str = "runner-only") -> Plan:
    return plan_fx(BUILDER, cwd=project, arguments={"package": package})


def inputs_from(row: dict[str, Any]) -> list[str]:
    """The instances a row reads, needs or waits on."""

    return sorted({*row["reads"], *row["needs"], *row["waiting_on"]} - {row["id"]})


def file_value(path: Path) -> dict[str, str]:
    """A file as a plan's ``with`` names it: by its digest."""

    return {"file": hashlib.sha256(path.read_bytes()).hexdigest()}


# ------------------------------------------------------------------------------- stand-ins


def _png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _cutout(width: int, height: int) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse(
        (width // 4, height // 6, width * 3 // 4, height * 5 // 6), fill=(90, 140, 210, 255)
    )
    return _png(image)


def _strip() -> bytes:
    geometry = DEFAULT_MOTION_ATLAS_GEOMETRY
    image = Image.new("RGBA", (geometry.width, geometry.height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell = geometry.width // geometry.columns
    for column in range(geometry.required_cells):
        left = column * cell
        draw.rectangle(
            (
                left + cell // 4,
                geometry.height * 45 // 100,
                left + cell * 3 // 4,
                geometry.height * 3 // 4,
            ),
            fill=(80, 140, 220, 255),
        )
    return _png(image)


def _sky(width: int, height: int) -> bytes:
    image = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        shade = 120 + y * 100 // height
        draw.line((0, y, width, y), fill=(shade // 2, shade - 20, shade + 30, 255))
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


def _mp3(seconds: float, *, volume: float = 0.5) -> bytes:
    assert FFMPEG is not None
    made = subprocess.run(
        [
            FFMPEG,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-filter:a",
            f"volume={volume}",
            "-ac",
            "2",
            "-b:a",
            "128k",
            "-f",
            "mp3",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return made.stdout


class StandIns:
    """Every paid call the fixture makes, answered offline; ``refuse`` fails some on purpose."""

    def __init__(
        self,
        states: tuple[str, ...],
        *,
        refuse: str | None = None,
        script: Mapping[str, list[bytes]] | None = None,
    ) -> None:
        self.states = states
        self.refuse = refuse
        #: Payloads a capability answers with, in order, before its default.
        self.script = {name: list(payloads) for name, payloads in (script or {}).items()}
        self.calls: Counter[str] = Counter()
        self._atlas: bytes | None = None
        self._audio: dict[tuple[float, float], bytes] = {}

    def __call__(self, call: StandInCall) -> Answer:
        request = call.request
        if call.capability in ("image.generate", "image.edit"):
            return self._image(request)
        if call.capability == "structured.generate":
            return self._structured()
        if call.capability == "music.generate":
            self.calls["track"] += 1
            return Answer(files={"audio": self._clip(16.0)})
        if call.capability == "sound.generate":
            return self._sound(request)
        if call.capability == "speech.generate":
            self.calls["line"] += 1
            scripted = self.script.get("speech")
            return Answer(files={"audio": scripted.pop(0) if scripted else self._clip(1.0)})
        raise AssertionError(f"unexpected call: {call!r}")

    def _image(self, request: Mapping[str, Any]) -> Answer:
        size = str(request.get("size"))
        transparent = request.get("background") == "transparent"
        # Three pictures share the motion canvas: a chunk paints over its guide with the
        # material references, a strip redraws the concept alone, the cover layer is opaque.
        if transparent and size == DEFAULT_MOTION_ATLAS_GEOMETRY.provider_size:
            if request.get("references"):
                kind = "chunk"
                data = painted_over_guide(request["image"].read_bytes())
            else:
                kind = "strip"
                data = _strip()
        elif size == "1024x1536":
            kind = "concept"
            data = _cutout(1024, 1536)
        elif size == "1024x1024":
            kind = "catalog"
            data = _cutout(1024, 1024)
        elif size == PAINT_CANVAS_SIZE:
            kind = "atlas"
            self._atlas = self._atlas or _atlas()
            data = self._atlas
        else:
            kind = "layer"
            width, height = (int(side) for side in size.split("x"))
            data = _sky(width, height)
        self.calls[kind] += 1
        if kind == self.refuse:
            raise CallRefused(f"the stand-in refuses every {kind}")
        return Answer(files={"image": data})

    def _structured(self) -> Answer:
        self.calls["reading"] += 1
        answer = {
            "baseline_state": "run",
            "states": [
                {"state": state, "multiplier": 1.0, "evidence": "Drawn at the run's size."}
                for state in self.states
            ],
        }
        return Answer.json(answer)

    def _clip(self, seconds: float, volume: float = 0.5) -> bytes:
        key = (seconds, volume)
        if key not in self._audio:
            self._audio[key] = _mp3(seconds, volume=volume)
        return self._audio[key]

    def _sound(self, request: Mapping[str, Any]) -> Answer:
        self.calls["clip"] += 1
        scripted = self.script.get("sound")
        clip = (
            scripted.pop(0)
            if scripted
            else self._clip(float(request["duration"]), 0.0 if self.refuse == "silence" else 0.5)
        )
        return Answer(files={"audio": clip})


def scripted(**script: list[bytes]) -> Any:
    return lambda states: StandIns(states, script=script)


def run(project: Path, stand_ins_for: Any, run_dir: Path) -> tuple[RunResult, StandIns]:
    resolved = resolve_runner_package(project / "runner-only")
    stand_ins = stand_ins_for(declared_motion_states(resolved.runner.avatar.avatar))
    outcome = run_fx(
        BUILDER,
        cwd=project,
        arguments={"package": "runner-only"},
        run_dir=run_dir,
        stand_in=stand_ins,
    )
    return outcome, stand_ins


# ------------------------------------------------------------------------------- the plan


def test_the_shipped_package_plans_inside_its_own_project() -> None:
    planned = plan(GAME, "inputs")

    assert planned.ok, planned.problems
    assert planned.document["workflow"]["id"] == "iron-petal-unit"
    budget = ceiling(planned)
    assert budget is not None and planned.estimate()[1] <= budget


def test_the_plan_writes_one_group_of_steps_per_asset(tmp_path: Path) -> None:
    planned = plan(runner_project(tmp_path))

    assert planned.ok, planned.problems
    steps = by_step(planned)
    calls = Counter(cap for row in first_takes(planned) for cap in row["routes"])
    # One ground atlas, one layer, one concept, four strips (the duck profile obligates a
    # slide) and two catalog cut-outs; the two rebase readings; two tracks and one clip.
    assert calls == {
        "image.edit": 9,
        "structured.generate": 2,
        "music.generate": 2,
        "sound.generate": 1,
    }
    assert {"ground.paint_target", "ground.generate", "ground.admit", "ground.publish"} <= set(
        steps
    )
    assert {f"avatar.{state}.publish" for state in ("run", "jump", "slide", "death")} <= set(steps)
    assert "package" in steps


def test_every_painting_and_draw_is_judged_and_drawn_again_at_most_six_times(
    tmp_path: Path,
) -> None:
    planned = plan(runner_project(tmp_path))
    paid = [
        row
        for row in first_takes(planned)
        if set(row["routes"]) & {"image.edit", "music.generate", "sound.generate"}
    ]

    assert paid
    for row in paid:
        assert row["judged_by"], row["step"]
    takes = Counter(row["step"] for row in instances(planned) if row["state"] != "absent")
    assert {takes[row["step"]] for row in paid} == {6}


def test_a_transparent_painting_asks_for_a_route_that_paints_alpha(tmp_path: Path) -> None:
    project = runner_project(tmp_path)
    settings = project / "fx.yaml"
    settings.write_text(
        settings.read_text(encoding="utf-8").replace(
            "image.edit: gpt-image-2.5-sunburst@openai",
            "image.edit: openai/gpt-image-2.5-sunburst@openrouter",
        ),
        encoding="utf-8",
    )

    planned = plan(project)

    # The concept asks for alpha, which the OpenRouter route does not paint; the sky does not.
    assert not planned.ok
    found = "\n".join(f"{problem['where']}: {problem['message']}" for problem in planned.problems)
    assert "avatar.concept.generate" in found and "does not support alpha" in found
    assert "layers.meadow_sky.generate" not in found


def test_a_clip_is_drawn_from_its_authored_prompt_verbatim(tmp_path: Path) -> None:
    project = runner_project(tmp_path)
    resolved = resolve_runner_package(project / "runner-only")
    (effect,) = resolved.runner.audio.generated_effects()
    clip = effect.realization
    assert isinstance(clip, GeneratedClipRealization)

    draw = by_step(plan(project))[f"sounds.{effect.effect_id}.generate"]

    assert draw["with"]["prompt"] == clip.prompt
    assert draw["with"]["duration"] == clip.duration_seconds
    assert draw["with"]["loop"] is False


def test_a_spoken_line_is_read_by_its_cast_voice_and_keyed_on_it(tmp_path: Path) -> None:
    first = runner_project(tmp_path / "first", spoken=True)
    second = runner_project(tmp_path / "second", spoken=True)
    voices = second / "runner-only/voices.toml"
    resolved = resolve_runner_package(first / "runner-only")
    (line,) = resolved.runner.audio.spoken_lines()
    spoken = line.realization
    assert isinstance(spoken, SpokenLineRealization)
    assert resolved.runner.voices is not None
    voice = resolved.runner.voices.voice(spoken.voice_id)
    assert voice is not None
    voices.write_text(
        voices.read_text(encoding="utf-8").replace(voice.provider.voice, "RecastVoice01"),
        encoding="utf-8",
    )

    read = by_step(plan(first))[f"lines.{line.effect_id}.generate"]
    recast = by_step(plan(second))[f"lines.{line.effect_id}.generate"]

    assert read["with"]["text"] == spoken.text
    assert read["with"]["voice"] == voice.provider.voice
    assert recast["with"]["voice"] == "RecastVoice01"
    assert read["identity"] != recast["identity"]


def test_a_pinned_take_buys_nothing(tmp_path: Path) -> None:
    take = _mp3(0.8) if FFMPEG else b"ID3" + bytes(64)
    project = runner_project(tmp_path, spoken=True, pinned_take=take)
    planned = plan(project)

    assert planned.ok, planned.problems
    steps = by_step(planned)
    assert not any(step.startswith("lines.") and step.endswith(".generate") for step in steps)
    republish = next(row for step, row in steps.items() if step.endswith(".republish"))
    assert republish["with"]["audio"] == file_value(
        project / "runner-only/runner/audio/mira_go.mp3"
    )


def test_a_slide_free_avatar_plans_no_slide_strip(tmp_path: Path) -> None:
    planned = plan(
        runner_project(tmp_path, avatar=RUNNER_AVATAR_NO_SLIDE, gameplay=RUNNER_GAMEPLAY_NO_DUCK)
    )

    assert planned.ok, planned.problems
    assert not any(step.startswith("avatar.slide.") for step in by_step(planned))


def test_an_edit_to_one_layer_redraws_only_that_layer(tmp_path: Path) -> None:
    first = runner_project(tmp_path / "first")
    second = runner_project(tmp_path / "second")
    track = second / "runner-only/runner/track.toml"
    track.write_text(
        track.read_text(encoding="utf-8").replace(
            "A bright morning sky band", "A pale dawn sky band"
        ),
        encoding="utf-8",
    )

    before, after = by_step(plan(first)), by_step(plan(second))

    changed = sorted(
        step
        for step, row in after.items()
        if row["identity"] is not None and row["identity"] != before[step]["identity"]
    )
    assert changed == ["layers.meadow_sky.generate"]


def test_an_authored_display_scale_is_refused_while_planning(tmp_path: Path) -> None:
    project = runner_project(tmp_path)
    track = project / "runner-only/runner/track.toml"
    track.write_text(
        track.read_text(encoding="utf-8").replace(
            "\n[ground]\n",
            """
[[layers]]
layer_id = "meadow_hills"
reference_ids = ["cover_style"]
plane = "background"
order = 1
parallax = 0.3
alpha_mode = "transparent"
vertical_anchor = "screen_bottom"
display_scale = 1.3
prompt = "Low rolling meadow hills."

[layers.presentation]
contrast = 1.0
saturation = 1.0
atmosphere_color = "#9db8d9"
atmosphere_strength = 0.0
detail_blur_screen_pixels = 0.0

[ground]
""",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(FxError, match="runner does not draw display_scale yet"):
        plan(project)


def test_the_package_step_reads_the_whole_closure_and_each_reference_once(
    tmp_path: Path,
) -> None:
    project = runner_project(tmp_path)
    resolved = resolve_runner_package(project / "runner-only")

    package = by_step(plan(project))["package"]

    assert set(package["with"]["package"]) == {entry.path for entry in resolved.package.files}
    assert package["with"]["references"] == ["references/cover.png"]


def test_the_avatar_contract_facts_are_in_every_picture_of_it(tmp_path: Path) -> None:
    steps = by_step(plan(runner_project(tmp_path)))

    for step in ("avatar.concept.generate", "avatar.run.generate"):
        prompt = steps[step]["with"]["prompt"]
        assert "age 19" in prompt
        assert "body_kind human" in prompt
        assert "silhouette_mode single_character_v1" in prompt
        assert "proportion_basis character_head_v1" in prompt
        assert "whole character silhouette" in prompt
    death = steps["avatar.death.generate"]["with"]["prompt"]
    assert "fully disconnected" in death
    assert "zero-alpha transparent pixels" in death
    assert "no glow, aura" in death.lower()


def test_a_visible_rider_machine_slides_and_falls_as_one_secured_actor(tmp_path: Path) -> None:
    combined = (
        RUNNER_AVATAR.replace('body_kind = "human"', 'body_kind = "piloted_machine"')
        .replace(
            'silhouette_mode = "single_character_v1"',
            'silhouette_mode = "visible_rider_machine_v1"',
        )
        .replace(
            'proportion_basis = "character_head_v1"',
            'proportion_basis = "visible_rider_head_v1"',
        )
    )
    steps = by_step(plan(runner_project(tmp_path, avatar=combined, piloted_heads_tall=4.2)))

    slide = steps["avatar.slide.generate"]["with"]["prompt"]
    assert "fully-low held skid" in slide
    assert "held indefinitely while the player ducks" in slide
    assert "below 45 percent of standing run height" in slide
    assert "keeps both hands on the controls" in slide
    assert "baseball-style" not in slide
    death = steps["avatar.death.generate"]["with"]["prompt"]
    assert "height strictly descends" in death
    assert "lowest compact powered-down failure pose" in death
    assert "reactor and headlamp visibly dark" in death
    assert "Never recover, rise, reset, smile, celebrate" in death


def test_structural_ground_paints_each_segment_over_its_guide_and_shares_one_seam(
    tmp_path: Path,
) -> None:
    project = structural(runner_project(tmp_path))
    planned = plan(project)

    assert planned.ok, planned.problems
    steps = by_step(planned)
    assert "ground.paint_target" not in steps
    # A reader of a judged painting reads whichever take its judge accepts.
    bridge = set(inputs_from(steps["ground.seam_bridge"]))
    assert "ground.warmup_flat.guide#1" in bridge
    assert "ground.warmup_flat.generate#1" in bridge
    assert not any(read.startswith("ground.first_gap.") for read in bridge)
    for segment in ("warmup_flat", "first_gap"):
        painting = steps[f"ground.{segment}.generate"]
        assert inputs_from(painting) == [f"ground.{segment}.guide#1"]
        assert "fully transparent with true alpha" in painting["with"]["prompt"]
        assert painting["with"]["references"] == [
            file_value(project / "runner-only/references/cover.png")
        ]
        published = set(inputs_from(steps[f"ground.{segment}.publish"]))
        assert {f"ground.{segment}.guide#1", "ground.seam_bridge#1"} <= published
    assert "world/ground/first_gap.png" in steps["package"]["with"]["published"]


def test_an_edit_to_one_segment_repaints_only_that_segment(tmp_path: Path) -> None:
    wider = ["0" * 25] * 5 + ["1" * 25] * 3
    first = structural(
        runner_project(
            tmp_path / "first",
            chunks="\n".join(
                [chunk_toml("alpha", WIDE_FLAT_ROWS), chunk_toml("beta", WIDE_FLAT_ROWS)]
            ),
        )
    )
    second = structural(
        runner_project(
            tmp_path / "second",
            chunks="\n".join([chunk_toml("alpha", WIDE_FLAT_ROWS), chunk_toml("beta", wider)]),
        )
    )

    before, after = by_step(plan(first)), by_step(plan(second))

    # A painting is keyed on its guide's bytes and its prompt; the guide is keyed now.
    assert before["ground.alpha.guide"]["identity"] == after["ground.alpha.guide"]["identity"]
    assert before["ground.beta.guide"]["identity"] != after["ground.beta.guide"]["identity"]
    alpha, beta = "ground.alpha.generate", "ground.beta.generate"
    assert before[alpha]["with"]["prompt"] == after[alpha]["with"]["prompt"]
    assert before[beta]["with"]["prompt"] != after[beta]["with"]["prompt"]


def test_one_source_named_by_two_reference_ids_is_republished_once(tmp_path: Path) -> None:
    project = runner_project(tmp_path)
    items = project / "runner-only/runner/content/items.toml"
    source = items.read_text(encoding="utf-8")
    items.write_text(
        source.replace('reference_id = "cover_style"', 'reference_id = "item_cover"', 1).replace(
            'reference_ids = ["cover_style"]', 'reference_ids = ["item_cover"]', 1
        ),
        encoding="utf-8",
    )

    assert by_step(plan(project))["package"]["with"]["references"] == ["references/cover.png"]


# -------------------------------------------------------------------------------- a run


@needs_ffmpeg
def test_a_whole_run_lays_out_the_package_the_host_reads(tmp_path: Path) -> None:
    project = runner_project(tmp_path)

    outcome, stand_ins = run(project, StandIns, tmp_path / "run")

    assert outcome.ok, failures(outcome)
    assert stand_ins.calls == {
        "atlas": 1,
        "layer": 1,
        "concept": 1,
        "strip": 4,
        "catalog": 2,
        "reading": 2,
        "track": 2,
        "clip": 1,
    }
    delivered = tmp_path / "package"
    deliver(outcome, delivered)
    manifest = json.loads((delivered / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == MANIFEST_KIND
    referenced = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, str) and value.endswith((".png", ".mp3")):
            referenced.append(value)

    collect(manifest)
    assert referenced
    assert [path for path in referenced if not (delivered / path).is_file()] == []
    assert (delivered / "references/cover.png").is_file()


@needs_ffmpeg
def test_a_stopped_run_resumes_without_paying_twice(tmp_path: Path) -> None:
    project = runner_project(tmp_path)

    stopped, refusing = run(
        project, lambda states: StandIns(states, refuse="strip"), tmp_path / "run"
    )
    resumed, stand_ins = run(project, StandIns, tmp_path / "run")

    assert not stopped.ok
    assert refusing.calls["strip"] == 4
    assert resumed.ok, failures(resumed)
    # Everything paid for before the stop came from the cache; only the strips were drawn.
    assert stand_ins.calls == {"strip": 4, "reading": 2}


@needs_ffmpeg
def test_a_silent_clip_is_drawn_again_and_then_refused(tmp_path: Path) -> None:
    project = runner_project(tmp_path)

    outcome, stand_ins = run(
        project, lambda states: StandIns(states, refuse="silence"), tmp_path / "run"
    )

    assert not outcome.ok
    assert stand_ins.calls["clip"] == 6


@needs_ffmpeg
def test_a_clip_that_misses_its_authored_length_is_refused(tmp_path: Path) -> None:
    project = runner_project(tmp_path)

    outcome, stand_ins = run(project, scripted(sound=[_mp3(2.0)]), tmp_path / "run")

    assert not outcome.ok
    assert stand_ins.calls["clip"] == 1
    assert "runs 2.0" in outcome.failures["sounds.run_ended.record#1"].message


@needs_ffmpeg
def test_an_over_long_read_is_read_again_and_never_trimmed(tmp_path: Path) -> None:
    project = runner_project(tmp_path, spoken=True)
    fits = _mp3(1.5, volume=0.25)

    outcome, stand_ins = run(
        project, scripted(speech=[_mp3(4.0, volume=0.25), fits]), tmp_path / "run"
    )

    assert outcome.ok, failures(outcome)
    assert stand_ins.calls["line"] == 2
    assert "ceiling" in str(finished(outcome, "lines.mira_go.admit#1")["facts"]["errors"])
    delivered = tmp_path / "package"
    deliver(outcome, delivered)
    assert (delivered / "audio/mira_go.mp3").read_bytes() == fits


@needs_ffmpeg
def test_a_pinned_take_is_republished_verbatim_with_its_sidecar(tmp_path: Path) -> None:
    take = _mp3(1.0, volume=0.25)
    project = runner_project(tmp_path, spoken=True, pinned_take=take)

    outcome, stand_ins = run(project, StandIns, tmp_path / "run")

    assert outcome.ok, failures(outcome)
    assert stand_ins.calls["line"] == 0
    delivered = tmp_path / "package"
    deliver(outcome, delivered)
    assert (delivered / "audio/mira_go.mp3").read_bytes() == take
    sidecar = project / "runner-only/runner/audio/mira_go.mp3.meta.json"
    assert (delivered / "audio/mira_go.mp3.meta.json").read_bytes() == sidecar.read_bytes()
    record = json.loads((delivered / "audio/mira_go.validation.json").read_text(encoding="utf-8"))
    assert record["listening_verdict"] == "author_selected"


def test_a_silent_contract_plans_no_speech(tmp_path: Path) -> None:
    assert not any(step.startswith("lines.") for step in by_step(plan(runner_project(tmp_path))))


def test_a_portrait_of_an_actor_this_package_does_not_draw_is_refused(tmp_path: Path) -> None:
    project = runner_project(tmp_path)
    shutil.copytree(GAME / "inputs", project / "shipped")
    fx = project / "shipped/fx.toml"
    fx.write_text(
        fx.read_text(encoding="utf-8").replace(
            'actor_id = "canopy_pruner"', 'actor_id = "not_a_boss"'
        ),
        encoding="utf-8",
    )

    with pytest.raises(FxError, match="not_a_boss"):
        plan(project, "shipped")


@needs_ffmpeg
def test_structural_ground_publishes_every_chunk_with_the_shared_seam(tmp_path: Path) -> None:
    project = structural(runner_project(tmp_path))

    outcome, stand_ins = run(project, StandIns, tmp_path / "run")

    assert outcome.ok, failures(outcome)
    assert stand_ins.calls["chunk"] == 2
    delivered = tmp_path / "package"
    deliver(outcome, delivered)
    manifest = json.loads((delivered / "manifest.json").read_text(encoding="utf-8"))
    chunks = manifest["ground"]["chunks"]
    assert [chunk["image"] for chunk in chunks] == [
        "world/ground/warmup_flat.png",
        "world/ground/first_gap.png",
    ]
    for chunk in chunks:
        record = json.loads(
            (delivered / chunk["image"].replace(".png", ".validation.json")).read_text()
        )
        assert record["seam_bridge_ref"] == "world/ground/shared-seam-bridge.png"
