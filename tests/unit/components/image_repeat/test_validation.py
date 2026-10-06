from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from typing import Literal, cast

import pytest
from PIL import Image

from stage_gen.components.image_repeat import (
    ImageRepeatDeterministicReport,
    ImageRepeatStitch,
    ImageRepeatValidationPolicy,
    build_three_repeat_preview,
    validate_image_repeat,
)

type Color = tuple[int, int, int, int]

_RED: Color = (200, 20, 20, 255)
_GREEN: Color = (30, 160, 70, 255)
_BLUE: Color = (20, 40, 210, 255)


def test_deterministic_alpha_and_coverage_policies_reject_transparent_discontinuity() -> None:
    # Fades to transparent across the strip and meets an opaque head at the wrap: one alpha step
    # five times any the picture takes inside itself.
    image = Image.new("RGBA", (6, 4))
    for x in range(image.width):
        for y in range(image.height):
            image.putpixel((x, y), (40, 50, 60, round(255 * (1 - x / 5))))
    data = _png(image)
    report = validate_image_repeat(
        data,
        axis="x",
        alpha_policy="preserve",
        coverage_policy="continuous",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    assert report.verdict == "reject"
    assert "unintended_transparent_gap" in report.failure_codes
    assert "alpha_halo_or_matte_contamination" in report.failure_codes

    opaque_report = validate_image_repeat(
        data,
        axis="x",
        alpha_policy="require_opaque",
        coverage_policy="sparse_allowed",
        validation_policy=ImageRepeatValidationPolicy(),
    )
    assert opaque_report.verdict == "reject"
    assert "alpha_halo_or_matte_contamination" in opaque_report.failure_codes


def _periodic_texture(width: int = 48, height: int = 24) -> Image.Image:
    """Hard-edged stripes of uneven widths: large steps everywhere, and a period that closes."""

    widths = [3, 5, 2, 6, 4, 7, 3, 5, 2, 6, 5]
    palette = [_RED, _GREEN, _BLUE, (230, 210, 60, 255), (20, 20, 20, 255)]
    image = Image.new("RGBA", (width, height))
    x = 0
    for index, span in enumerate(widths):
        for column in range(x, min(width, x + span)):
            for y in range(height):
                image.putpixel((column, y), palette[index % len(palette)])
        x += span
    return image


def _looping_ramp(width: int = 48, height: int = 24) -> Image.Image:
    """A smooth grey ramp that rises to the middle and falls back, so its wrap closes."""

    image = Image.new("RGBA", (width, height))
    for x in range(width):
        level = 60 + round(40 * abs(x - width // 2) / (width // 2))
        for y in range(height):
            image.putpixel((x, y), (level, level, level, 255))
    return image


def _validate(
    image: Image.Image, stitches: Sequence[ImageRepeatStitch] = ()
) -> ImageRepeatDeterministicReport:
    return validate_image_repeat(
        _png(image),
        axis="x",
        alpha_policy="preserve",
        coverage_policy="sparse_allowed",
        validation_policy=ImageRepeatValidationPolicy(),
        stitches=stitches,
    )


def test_a_hard_wrap_passes_when_the_picture_is_made_of_hard_steps() -> None:
    """A join is held to the picture it sits in; a fixed limit would refuse this whole strip."""

    assert _validate(_periodic_texture()).verdict == "pass"


def test_a_stitch_is_rejected_when_the_pictures_either_side_disagree() -> None:
    """A blend of two different pictures is a ghost even when every step across it is small."""

    image = _looping_ramp()
    positions = tuple([20] * image.height)

    agreeing = _validate(image, [ImageRepeatStitch(positions, 0.0, 0.0)])
    ghosted = _validate(image, [ImageRepeatStitch(positions, 0.3, 0.0)])

    assert agreeing.verdict == "pass"
    assert [join.name for join in agreeing.joins] == ["wrap", "stitch"]
    assert ghosted.verdict == "reject"
    assert ghosted.failure_codes == ["clipped_or_disconnected_form"]


def test_a_stitch_that_steps_is_rejected_like_any_join() -> None:
    # Everything right of a curved stitch is brightened: the step across it is unlike any column
    # inside the ramp.
    image = _looping_ramp()
    positions = tuple(20 + (y // 6) for y in range(image.height))
    for y, start in enumerate(positions):
        for x in range(start, image.width):
            level = cast(tuple[int, ...], image.getpixel((x, y)))[0]
            image.putpixel((x, y), (level + 120, level + 120, level + 120, 255))

    report = _validate(image, [ImageRepeatStitch(positions, 0.0, 0.0)])

    assert report.verdict == "reject"
    assert report.joins[1].verdict == "reject"
    assert "visible_boundary_pop" in report.joins[1].failure_codes


@pytest.mark.parametrize(
    ("axis", "size", "expected_size"),
    [
        ("x", (6, 4), (18, 4)),
        ("y", (4, 6), (4, 18)),
    ],
)
def test_three_repeat_preview_is_opaque_and_hidden_rgb_invariant(
    axis: Literal["x", "y"],
    size: tuple[int, int],
    expected_size: tuple[int, int],
) -> None:
    neutral_hidden_rgb = Image.new("RGBA", size, (0, 0, 0, 0))
    magenta_hidden_rgb = Image.new("RGBA", size, (255, 0, 255, 0))

    neutral_preview = build_three_repeat_preview(_png(neutral_hidden_rgb), axis=axis)
    magenta_preview = build_three_repeat_preview(_png(magenta_hidden_rgb), axis=axis)

    assert neutral_preview == magenta_preview
    decoded = _decode(neutral_preview)
    assert decoded.mode == "RGB"
    assert decoded.size == expected_size


@pytest.mark.parametrize("axis", ["x", "y"])
def test_three_repeat_preview_preserves_opaque_pixels_in_all_three_copies(
    axis: Literal["x", "y"],
) -> None:
    size = (6, 4) if axis == "x" else (4, 6)
    source = Image.new("RGBA", size)
    for y in range(source.height):
        for x in range(source.width):
            source.putpixel((x, y), (x * 30, y * 40, 120, 255))

    preview = _decode(build_three_repeat_preview(_png(source), axis=axis))
    expected = source.convert("RGB").tobytes()
    for index in range(3):
        box = (
            (index * source.width, 0, (index + 1) * source.width, source.height)
            if axis == "x"
            else (0, index * source.height, source.width, (index + 1) * source.height)
        )
        assert preview.crop(box).tobytes() == expected


def test_three_repeat_preview_makes_partial_alpha_visible_against_checkerboard() -> None:
    size = (4, 2)
    transparent = Image.new("RGBA", size, (30, 90, 210, 0))
    partial = Image.new("RGBA", size, (30, 90, 210, 128))
    opaque = Image.new("RGBA", size, (30, 90, 210, 255))

    background = _decode(build_three_repeat_preview(_png(transparent), axis="x"))
    blended = _decode(build_three_repeat_preview(_png(partial), axis="x"))
    foreground = _decode(build_three_repeat_preview(_png(opaque), axis="x"))

    for y in range(size[1]):
        for x in range(size[0]):
            background_pixel = cast(tuple[int, int, int], background.getpixel((x, y)))
            blended_pixel = cast(tuple[int, int, int], blended.getpixel((x, y)))
            foreground_pixel = cast(tuple[int, int, int], foreground.getpixel((x, y)))
            assert blended_pixel not in (background_pixel, foreground_pixel)
            assert all(
                min(background_channel, foreground_channel)
                < blended_channel
                < max(background_channel, foreground_channel)
                for background_channel, blended_channel, foreground_channel in zip(
                    background_pixel,
                    blended_pixel,
                    foreground_pixel,
                    strict=True,
                )
            )


def _png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", compress_level=9, optimize=False)
    return output.getvalue()


def _decode(data: bytes) -> Image.Image:
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.copy()
