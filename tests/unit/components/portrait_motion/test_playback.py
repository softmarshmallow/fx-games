"""Lossless timing and independent feature-selection checks using synthetic pixels."""

from __future__ import annotations

import io
from typing import cast

import numpy as np
import pytest
from PIL import Image

from fx_games.components.portrait_motion.models import (
    MotionState,
    PlaybackSegment,
    PortraitMotionSpec,
)
from fx_games.components.portrait_motion.playback import build_combinations, encode_preview
from fx_games.components.portrait_motion.processing import FloatArray, geometry_masks


def fixture() -> tuple[Image.Image, dict[str, FloatArray]]:
    source = Image.new("RGB", (128, 192), (90, 120, 160))
    masks, _ = geometry_masks(
        [
            {"feature_id": "canvas_right_eye", "points": [[30, 20], [38, 20], [38, 28], [30, 28]]},
            {"feature_id": "mouth", "points": [[24, 60], [32, 60], [32, 68], [24, 68]]},
        ],
        source.size,
        (64, 96),
        3,
    )
    return source, masks


def segment(eyes: str = "rest", mouth: str = "rest", duration: int = 100) -> PlaybackSegment:
    return PlaybackSegment(eyes=eyes, mouth=mouth, duration_ms=duration)


def specification() -> PortraitMotionSpec:
    return PortraitMotionSpec(
        width=128,
        height=192,
        columns=2,
        rows=2,
        states=[
            MotionState(state_id="half", feature_group="eyes", instruction="Half blink"),
            MotionState(state_id="closed", feature_group="eyes", instruction="Close eyes"),
            MotionState(state_id="smile", feature_group="mouth", instruction="Small smile"),
            MotionState(state_id="a", feature_group="mouth", instruction="Open mouth"),
        ],
        requested_features=["canvas_right_eye", "mouth"],
        playback=[segment(), segment("half"), segment("closed", "a"), segment()],
    )


def panel_donors() -> dict[str, Image.Image]:
    return {
        state: Image.new("RGB", (64, 96), color)
        for state, color in zip(
            ("half", "closed", "smile", "a"),
            ((130, 30, 70), (220, 60, 80), (140, 40, 20), (40, 210, 80)),
            strict=True,
        )
    }


def test_graph_wrappers_build_all_combinations_and_verified_preview() -> None:
    source, masks = fixture()
    spec = specification()
    donors = panel_donors()
    combinations, facts = build_combinations(source, donors, masks, spec)
    assert len(combinations) == 9
    assert np.array_equal(np.asarray(combinations[("rest", "rest")]), np.asarray(source))
    assert facts["native_source_outside_active_alpha_exact"] is True
    assert facts["native_donor_opaque_cores_exact"] is True
    assert facts["composition_order_pixel_identical"] is True
    for (eyes, mouth), image in combinations.items():
        pixels = np.asarray(image)
        active = np.zeros((source.height, source.width), dtype=bool)
        for state, mask in ((eyes, masks["canvas_right_eye"]), (mouth, masks["mouth"])):
            if state != "rest":
                active |= mask > 0
                expected = np.asarray(donors[state].resize(source.size, Image.Resampling.LANCZOS))
                assert np.array_equal(pixels[mask == 1], expected[mask == 1])
        assert np.array_equal(pixels[~active], np.asarray(source)[~active])
    data, report = encode_preview(combinations, spec)
    assert report["size"] == [64, 96]
    assert report["total_duration_ms"] == 400
    with Image.open(io.BytesIO(data)) as decoded:
        assert getattr(decoded, "is_animated", False) and getattr(decoded, "n_frames", 0) == 4
        assert decoded.size == (64, 96)


def test_graph_wrapper_retains_inactive_group_combinations_without_painting() -> None:
    source, masks = fixture()
    combinations, facts = build_combinations(
        source, panel_donors(), {"canvas_right_eye": masks["canvas_right_eye"]}, specification()
    )
    assert len(combinations) == 9
    assert facts["inactive_groups"] == ["mouth"]
    assert np.array_equal(np.asarray(combinations[("rest", "a")]), np.asarray(source))
    assert np.array_equal(
        np.asarray(combinations[("closed", "a")]), np.asarray(combinations[("closed", "rest")])
    )


def test_graph_wrapper_rejects_missing_states_and_wrong_donor_dimensions() -> None:
    source, masks = fixture()
    spec = specification()
    with pytest.raises(ValueError, match="complete declared state set"):
        build_combinations(source, {}, masks, spec)
    donors = panel_donors()
    donors["half"] = donors["half"].resize(source.size)
    with pytest.raises(ValueError, match="declared panel size"):
        build_combinations(source, donors, masks, spec)
    combinations, _ = build_combinations(source, panel_donors(), masks, spec)
    del combinations[("half", "smile")]
    with pytest.raises(ValueError, match="complete declared Cartesian"):
        encode_preview(combinations, spec)


def test_preview_coalesces_equal_segments_and_keeps_their_timing() -> None:
    source, masks = fixture()
    playback = [
        segment(),
        segment("half", duration=50),
        segment("half", duration=50),
        segment("closed", "a", 80),
        segment(),
    ]
    spec = specification().model_copy(update={"playback": playback})
    combinations, _ = build_combinations(source, panel_donors(), masks, spec)
    data, report = encode_preview(combinations, spec)
    assert (report["encoded_frame_count"], report["logical_segment_count"]) == (4, 5)
    assert report["total_duration_ms"] == 380
    records = cast(list[dict[str, object]], report["encoded_segments"])
    assert [(row["segment_start"], row["segment_end_exclusive"]) for row in records] == [
        (0, 1),
        (1, 3),
        (3, 4),
        (4, 5),
    ]
    with Image.open(io.BytesIO(data)) as decoded:
        durations = []
        for index in range(getattr(decoded, "n_frames", 0)):
            decoded.seek(index)
            decoded.load()
            durations.append(decoded.info["duration"])
        assert durations == [100, 100, 80, 100]


def test_preview_refuses_a_timeline_with_no_visible_motion() -> None:
    source, masks = fixture()
    spec = specification().model_copy(update={"playback": [segment(), segment()]})
    combinations, _ = build_combinations(source, panel_donors(), masks, spec)
    with pytest.raises(ValueError, match="no visible motion"):
        encode_preview(combinations, spec)


@pytest.mark.parametrize(
    "playback",
    [
        [],
        [segment("closed"), segment()],
        [segment(), segment("closed")],
        [segment(), segment("a"), segment()],
        [segment(), segment("unknown"), segment()],
        [segment(duration=10000)] * 7,
    ],
)
def test_preview_rejects_an_invalid_timeline(playback: list[PlaybackSegment]) -> None:
    source, masks = fixture()
    combinations, _ = build_combinations(source, panel_donors(), masks, specification())
    with pytest.raises(ValueError):
        encode_preview(combinations, specification().model_copy(update={"playback": playback}))
