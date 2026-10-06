"""Repeat previews and deterministic single-axis validation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, cast

from PIL import Image

from stage_gen.media import inspect_image
from stage_gen.media.codec import decode_rgba, encode_png

from .models import (
    MAX_IMAGE_REPEAT_DIMENSION,
    MAX_IMAGE_REPEAT_PIXELS,
    ImageRepeatAlphaPolicy,
    ImageRepeatAxis,
    ImageRepeatCoveragePolicy,
    ImageRepeatDeterministicReport,
    ImageRepeatFailureCode,
    ImageRepeatJoinReport,
    ImageRepeatScaleMetrics,
    ImageRepeatStitch,
    ImageRepeatValidationPolicy,
)

_PREVIEW_REPEAT_COUNT = 3
_PREVIEW_CHECKER_TARGET_TILE_PX = 32
_PREVIEW_CHECKER_MAX_PRIMARY_TILES = 64
_PREVIEW_CHECKER_LIGHT: _Rgba = (224, 224, 224, 255)
_PREVIEW_CHECKER_DARK: _Rgba = (192, 192, 192, 255)
_MAX_BASELINE_PRIMARY_SAMPLES = 32
_MAX_CROSS_AXIS_SAMPLES = 2048

type _Rgba = tuple[int, int, int, int]
type _JoinName = Literal["wrap", "stitch"]


def validate_image_repeat(
    repeat_unit_data: bytes,
    *,
    axis: ImageRepeatAxis,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    validation_policy: ImageRepeatValidationPolicy,
    stitches: Sequence[ImageRepeatStitch] = (),
) -> ImageRepeatDeterministicReport:
    """Evaluate the declared-axis wrap, and every stitch a construction cut into the unit.

    The other axis is intentionally ignored. A construction that writes provider pixels into the
    source leaves joins inside the unit as well as at its wrap, and a verdict that measured only
    the wrap would pass whatever those inner joins look like.
    """

    facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    _validate_dimensions(facts.width, facts.height, "image-repeat candidate")
    primary = facts.width if axis == "x" else facts.height
    if primary < 2:
        raise ValueError("image-repeat candidate must span at least two pixels on its repeat axis")
    if len(stitches) > 2:
        raise ValueError("image-repeat validation measures at most two stitches")
    image = _decode_rgba(repeat_unit_data)
    join = _join_report(
        image,
        image,
        axis=axis,
        name="wrap",
        coverage_policy=coverage_policy,
        policy=validation_policy,
    )
    joins = [join]
    joins.extend(
        _join_report(
            image,
            image,
            axis=axis,
            name="stitch",
            coverage_policy=coverage_policy,
            policy=validation_policy,
            stitch=stitch,
        )
        for stitch in stitches
    )
    if alpha_policy == "require_opaque" and _has_nonopaque_pixels(image):
        joins[0] = _add_join_failure(join, "alpha_halo_or_matte_contamination")
    return _deterministic_report(
        axis=axis,
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        source_immutable=True,
        joins=joins,
    )


def build_three_repeat_preview(
    repeat_unit_data: bytes,
    *,
    axis: ImageRepeatAxis,
) -> bytes:
    """Return three repeats composited over a deterministic neutral checkerboard.

    The opaque preview is a semantic-review visualization, not candidate media. Compositing
    makes partial alpha visible and guarantees that RGB hidden by zero alpha cannot influence
    the reviewer. The checker unit has an even number of tiles on the declared axis, so it is
    itself continuous when copied and cannot introduce a false join at a repeat boundary.
    """

    facts = inspect_image(repeat_unit_data, expected_media_type="image/png")
    _validate_dimensions(facts.width, facts.height, "image-repeat preview source")
    primary_extent = facts.width if axis == "x" else facts.height
    if primary_extent < 2:
        raise ValueError("image-repeat preview source must span two pixels on its repeat axis")
    image = _decode_rgba(repeat_unit_data)
    width = facts.width * _PREVIEW_REPEAT_COUNT if axis == "x" else facts.width
    height = facts.height if axis == "x" else facts.height * _PREVIEW_REPEAT_COUNT
    if width * height > MAX_IMAGE_REPEAT_PIXELS * _PREVIEW_REPEAT_COUNT:
        raise ValueError("three-repeat preview exceeds the bounded image-repeat pixel budget")
    checker = _neutral_checkerboard_unit(image.size, axis=axis)
    visualized_unit = Image.alpha_composite(checker, image).convert("RGB")
    preview = Image.new("RGB", (width, height))
    for index in range(_PREVIEW_REPEAT_COUNT):
        position = (index * facts.width, 0) if axis == "x" else (0, index * facts.height)
        preview.paste(visualized_unit, position)
    return _encode_png(preview)


def _neutral_checkerboard_unit(
    size: tuple[int, int],
    *,
    axis: ImageRepeatAxis,
) -> Image.Image:
    width, height = size
    primary_extent = width if axis == "x" else height
    approximate_tiles = max(
        2,
        (primary_extent + _PREVIEW_CHECKER_TARGET_TILE_PX - 1) // _PREVIEW_CHECKER_TARGET_TILE_PX,
    )
    primary_tiles = min(
        _PREVIEW_CHECKER_MAX_PRIMARY_TILES,
        approximate_tiles + approximate_tiles % 2,
    )
    approximate_tile_px = max(
        1,
        (primary_extent + primary_tiles // 2) // primary_tiles,
    )
    checker = Image.new("RGBA", size, _PREVIEW_CHECKER_LIGHT)
    cross_extent = height if axis == "x" else width
    for primary_tile in range(primary_tiles):
        primary_start = (primary_tile * primary_extent + primary_tiles - 1) // primary_tiles
        primary_end = ((primary_tile + 1) * primary_extent + primary_tiles - 1) // primary_tiles
        for cross_start in range(0, cross_extent, approximate_tile_px):
            cross_tile = cross_start // approximate_tile_px
            if (primary_tile + cross_tile) % 2 == 0:
                continue
            cross_end = min(cross_extent, cross_start + approximate_tile_px)
            box = (
                (primary_start, cross_start, primary_end, cross_end)
                if axis == "x"
                else (cross_start, primary_start, cross_end, primary_end)
            )
            checker.paste(_PREVIEW_CHECKER_DARK, box)
    return checker


def _join_report(
    before: Image.Image,
    after: Image.Image,
    *,
    axis: ImageRepeatAxis,
    name: _JoinName,
    coverage_policy: ImageRepeatCoveragePolicy,
    policy: ImageRepeatValidationPolicy,
    stitch: ImageRepeatStitch | None = None,
) -> ImageRepeatJoinReport:
    """Judge one join against the interior of the picture it sits in.

    A straight join compares the last line of ``before`` with the first line of ``after``. A
    ``stitch`` is a path through a single image (``before is after``), judged on the step across it
    like any join, and also on how far the two stitched pictures disagreed where they were blended.
    """

    _assert_cross_extent(before, after, axis)
    if stitch is not None:
        if before is not after:
            raise ValueError("a stitched join is measured inside a single image")
        if len(stitch.positions) != _cross_extent(before, axis):
            raise ValueError("a stitch must name one position per cross-axis line")
    metrics: list[ImageRepeatScaleMetrics] = []
    failures: list[ImageRepeatFailureCode] = []
    seen_sizes: set[tuple[int, int, int, int]] = set()
    for scale in policy.scales:
        scaled_before = _scale_image(before, scale)
        scaled_after = scaled_before if after is before else _scale_image(after, scale)
        if _primary_extent(scaled_before, axis) < 2 or _primary_extent(scaled_after, axis) < 2:
            continue
        size_key = (*scaled_before.size, *scaled_after.size)
        if size_key in seen_sizes:
            continue
        seen_sizes.add(size_key)
        lines: tuple[Sequence[_Rgba], Sequence[_Rgba], Sequence[_Rgba], Sequence[_Rgba]]
        if stitch is None:
            lines = (
                _edge_line(scaled_before, axis, -2),
                _edge_line(scaled_before, axis, -1),
                _edge_line(scaled_after, axis, 0),
                _edge_line(scaled_after, axis, 1),
            )
        else:
            scaled_stitch = _scaled_stitch(stitch.positions, scale, scaled_before, axis)
            lines = _stitch_lines(scaled_before, axis, scaled_stitch)
        sample = _step_sample(*lines, policy=policy)
        interior = _interior_means(scaled_before, axis, policy)
        if scaled_after is not scaled_before:
            interior += _interior_means(scaled_after, axis, policy)
        color_limit, gradient_limit, alpha_limit = (
            min(
                1.0,
                max(
                    floor,
                    _percentile([means[index] for means in interior], policy.interior_quantile)
                    * policy.interior_margin,
                ),
            )
            for index, floor in enumerate(
                (policy.color_mae_floor, policy.gradient_mae_floor, policy.alpha_mae_floor)
            )
        )
        measured = ImageRepeatScaleMetrics(
            scale=float(scale),
            boundary_width_px=max(1, round(1.0 / scale)),
            color_mae=float(_mean(sample.color)),
            color_p95=float(_percentile(sample.color, 0.95)),
            color_max=float(max(sample.color, default=0.0)),
            gradient_mae=float(_mean(sample.gradient)),
            gradient_p95=float(_percentile(sample.gradient, 0.95)),
            gradient_max=float(max(sample.gradient, default=0.0)),
            alpha_mae=float(_mean(sample.alpha)),
            alpha_p95=float(_percentile(sample.alpha, 0.95)),
            alpha_max=float(max(sample.alpha, default=0.0)),
            coverage_mismatch_ratio=float(sample.coverage_mismatches / max(1, len(sample.color))),
            interior_samples=max(1, len(interior)),
            color_limit=float(color_limit),
            gradient_limit=float(gradient_limit),
            alpha_limit=float(alpha_limit),
            coverage_limit=float(
                policy.coverage_mismatch_ratio if coverage_policy == "continuous" else 1.0
            ),
            color_disagreement=(
                stitch.color_disagreement if stitch is not None and scale == 1.0 else None
            ),
            alpha_disagreement=(
                stitch.alpha_disagreement if stitch is not None and scale == 1.0 else None
            ),
        )
        metrics.append(measured)
        if measured.color_mae > measured.color_limit:
            _append_unique(failures, "visible_boundary_pop")
        if measured.gradient_mae > measured.gradient_limit:
            _append_unique(failures, "lighting_or_texture_reset")
        if measured.alpha_mae > measured.alpha_limit:
            _append_unique(failures, "alpha_halo_or_matte_contamination")
        if measured.coverage_mismatch_ratio > measured.coverage_limit:
            _append_unique(failures, "unintended_transparent_gap")
        if (
            measured.color_disagreement is not None
            and measured.color_disagreement > measured.color_limit
        ) or (
            measured.alpha_disagreement is not None
            and measured.alpha_disagreement > measured.alpha_limit
        ):
            _append_unique(failures, "clipped_or_disconnected_form")
    if not metrics:
        raise ValueError("image-repeat validation could not evaluate any configured scale")
    return ImageRepeatJoinReport(
        name=name,
        verdict="reject" if failures else "pass",
        scales=metrics,
        failure_codes=failures,
    )


@dataclass(frozen=True, slots=True)
class _StepSample:
    """Per-line steps across one join, sampled along its cross axis."""

    color: list[float]
    gradient: list[float]
    alpha: list[float]
    coverage_mismatches: int


def _step_sample(
    previous_line: Sequence[_Rgba],
    before_line: Sequence[_Rgba],
    after_line: Sequence[_Rgba],
    following_line: Sequence[_Rgba],
    *,
    policy: ImageRepeatValidationPolicy,
) -> _StepSample:
    color_values: list[float] = []
    gradient_values: list[float] = []
    alpha_values: list[float] = []
    coverage_mismatches = 0
    for index in _sample_indices(len(before_line), _MAX_CROSS_AXIS_SAMPLES):
        boundary_before = before_line[index]
        boundary_after = after_line[index]
        previous_visual = _visual_rgb(previous_line[index])
        before_visual = _visual_rgb(boundary_before)
        after_visual = _visual_rgb(boundary_after)
        following_visual = _visual_rgb(following_line[index])
        color_values.append(
            sum(abs(left - right) for left, right in zip(before_visual, after_visual, strict=True))
            / 3.0
        )
        gradient_values.append(
            sum(
                abs(
                    (after_visual[channel] - before_visual[channel])
                    - (
                        (before_visual[channel] - previous_visual[channel])
                        + (following_visual[channel] - after_visual[channel])
                    )
                    / 2.0
                )
                / 2.0
                for channel in range(3)
            )
            / 3.0
        )
        alpha_before = boundary_before[3] / 255.0
        alpha_after = boundary_after[3] / 255.0
        alpha_values.append(abs(alpha_before - alpha_after))
        before_covered = alpha_before > policy.coverage_alpha_threshold
        after_covered = alpha_after > policy.coverage_alpha_threshold
        if before_covered != after_covered:
            coverage_mismatches += 1
    return _StepSample(
        color=color_values,
        gradient=gradient_values,
        alpha=alpha_values,
        coverage_mismatches=coverage_mismatches,
    )


def _interior_means(
    image: Image.Image, axis: ImageRepeatAxis, policy: ImageRepeatValidationPolicy
) -> list[tuple[float, float, float]]:
    """Mean colour, gradient and alpha steps at evenly spaced interior lines of one image.

    Interior lines are continuous by definition, so their steps are what an unremarkable column of
    this particular picture looks like: the baseline a join is held to.
    """

    rgba = image.convert("RGBA")
    primary = _primary_extent(rgba, axis)
    if primary < 4:
        return []
    pixels = rgba.load()
    if pixels is None:
        raise ValueError("image-repeat pixels are unavailable")
    cross = _cross_extent(rgba, axis)

    def line(index: int) -> tuple[_Rgba, ...]:
        if axis == "x":
            return tuple(cast(_Rgba, pixels[index, y]) for y in range(cross))
        return tuple(cast(_Rgba, pixels[x, index]) for x in range(cross))

    means: list[tuple[float, float, float]] = []
    for position in _sample_indices(primary - 3, _MAX_BASELINE_PRIMARY_SAMPLES, offset=2):
        sample = _step_sample(
            line(position - 2),
            line(position - 1),
            line(position),
            line(position + 1),
            policy=policy,
        )
        means.append((_mean(sample.color), _mean(sample.gradient), _mean(sample.alpha)))
    return means


def _scaled_stitch(
    stitch: Sequence[int], scale: float, scaled: Image.Image, axis: ImageRepeatAxis
) -> list[int]:
    """Carry a full-resolution stitch onto a scaled copy, one position per scaled line."""

    primary = _primary_extent(scaled, axis)
    positions: list[int] = []
    for index in range(_cross_extent(scaled, axis)):
        source = stitch[min(len(stitch) - 1, math.floor(index / scale))]
        positions.append(min(max(2, round(source * scale)), primary - 2))
    return positions


def _stitch_lines(
    image: Image.Image, axis: ImageRepeatAxis, stitch: Sequence[int]
) -> tuple[list[_Rgba], list[_Rgba], list[_Rgba], list[_Rgba]]:
    """The two pixels either side of a stitch on every line, as four join lines."""

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    if pixels is None:
        raise ValueError("image-repeat pixels are unavailable")
    lines: tuple[list[_Rgba], ...] = ([], [], [], [])
    for index, position in enumerate(stitch):
        for offset, target in zip((-2, -1, 0, 1), lines, strict=True):
            at = position + offset
            pixel = pixels[at, index] if axis == "x" else pixels[index, at]
            target.append(cast(_Rgba, pixel))
    return lines[0], lines[1], lines[2], lines[3]


def _deterministic_report(
    *,
    axis: ImageRepeatAxis,
    alpha_policy: ImageRepeatAlphaPolicy,
    coverage_policy: ImageRepeatCoveragePolicy,
    source_immutable: bool,
    joins: list[ImageRepeatJoinReport],
) -> ImageRepeatDeterministicReport:
    failure_codes: list[ImageRepeatFailureCode] = []
    for join in joins:
        for code in join.failure_codes:
            _append_unique(failure_codes, code)
    return ImageRepeatDeterministicReport(
        axis=axis,
        verdict="reject" if failure_codes else "pass",
        alpha_policy=alpha_policy,
        coverage_policy=coverage_policy,
        source_immutable=source_immutable,
        joins=joins,
        failure_codes=failure_codes,
    )


def _add_join_failure(
    report: ImageRepeatJoinReport,
    code: ImageRepeatFailureCode,
) -> ImageRepeatJoinReport:
    codes = list(report.failure_codes)
    _append_unique(codes, code)
    return report.model_copy(update={"verdict": "reject", "failure_codes": codes})


def _assert_cross_extent(before: Image.Image, after: Image.Image, axis: ImageRepeatAxis) -> None:
    before_cross = before.height if axis == "x" else before.width
    after_cross = after.height if axis == "x" else after.width
    if before_cross != after_cross:
        raise ValueError("image-repeat join segments must share their cross-axis extent")
    if _primary_extent(before, axis) < 2 or _primary_extent(after, axis) < 2:
        raise ValueError(
            "image-repeat join segments must each span at least two repeat-axis pixels"
        )


def _primary_extent(image: Image.Image, axis: ImageRepeatAxis) -> int:
    return image.width if axis == "x" else image.height


def _cross_extent(image: Image.Image, axis: ImageRepeatAxis) -> int:
    return image.height if axis == "x" else image.width


def _edge_line(image: Image.Image, axis: ImageRepeatAxis, index: int) -> tuple[_Rgba, ...]:
    rgba = image.convert("RGBA")
    primary = _primary_extent(rgba, axis)
    resolved = index if index >= 0 else primary + index
    if not 0 <= resolved < primary:
        raise ValueError("image-repeat edge line is outside the image")
    pixels = rgba.load()
    if pixels is None:
        raise ValueError("image-repeat pixels are unavailable")
    if axis == "x":
        return tuple(cast(_Rgba, pixels[resolved, y]) for y in range(rgba.height))
    return tuple(cast(_Rgba, pixels[x, resolved]) for x in range(rgba.width))


def _sample_indices(length: int, maximum: int, *, offset: int = 0) -> list[int]:
    if length <= 0:
        return []
    if length <= maximum:
        return [offset + index for index in range(length)]
    return sorted(
        {offset + min(length - 1, math.floor(index * length / maximum)) for index in range(maximum)}
    )


def _scale_image(image: Image.Image, scale: float) -> Image.Image:
    if scale == 1.0:
        return image.convert("RGBA")
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    return image.convert("RGBA").resize((width, height), resample=Image.Resampling.LANCZOS)


def _visual_rgb(pixel: _Rgba) -> tuple[float, float, float]:
    alpha = pixel[3] / 255.0
    return (
        (pixel[0] / 255.0) * alpha,
        (pixel[1] / 255.0) * alpha,
        (pixel[2] / 255.0) * alpha,
    )


def _has_nonopaque_pixels(image: Image.Image) -> bool:
    alpha = image.convert("RGBA").getchannel("A")
    minimum, _maximum = alpha.getextrema()
    return minimum != 255


def _validate_dimensions(width: int, height: int, label: str) -> None:
    if width < 1 or height < 1:
        raise ValueError(f"{label} dimensions must be positive")
    if width > MAX_IMAGE_REPEAT_DIMENSION or height > MAX_IMAGE_REPEAT_DIMENSION:
        raise ValueError(f"{label} dimensions must not exceed {MAX_IMAGE_REPEAT_DIMENSION}px")
    if width * height > MAX_IMAGE_REPEAT_PIXELS:
        raise ValueError(f"{label} must not exceed {MAX_IMAGE_REPEAT_PIXELS} pixels")


def _append_unique(
    values: list[ImageRepeatFailureCode],
    value: ImageRepeatFailureCode,
) -> None:
    if value not in values:
        values.append(value)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def _decode_rgba(data: bytes) -> Image.Image:
    return decode_rgba(data, label="image-repeat PNG")


def _encode_png(image: Image.Image) -> bytes:
    return encode_png(image, compress_level=9)
