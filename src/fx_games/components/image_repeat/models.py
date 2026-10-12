"""Provider-neutral contracts for deterministic single-axis image repetition."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import Field, model_validator

from fx_games.contracts import PersistedContractModel

DETERMINISTIC_VALIDATOR_VERSION: Literal["single-axis-continuity-v3"] = "single-axis-continuity-v3"
MAX_IMAGE_REPEAT_DIMENSION = 8192
MAX_IMAGE_REPEAT_PIXELS = 24_000_000

type ImageRepeatAxis = Literal["x", "y"]
type ImageRepeatAlphaPolicy = Literal["preserve", "require_opaque"]
type ImageRepeatCoveragePolicy = Literal["continuous", "sparse_allowed"]
type ImageRepeatFailureCode = Literal[
    "visible_boundary_pop",
    "clipped_or_disconnected_form",
    "unintended_transparent_gap",
    "structure_or_horizon_reset",
    "lighting_or_texture_reset",
    "mirror_or_reverse_shortcut",
    "salient_periodic_cadence",
    "orientation_or_gravity_break",
    "alpha_halo_or_matte_contamination",
    "intended_behavior_mismatch",
    "insufficient_evidence",
]

IMAGE_REPEAT_FAILURE_CODES: tuple[ImageRepeatFailureCode, ...] = (
    "visible_boundary_pop",
    "clipped_or_disconnected_form",
    "unintended_transparent_gap",
    "structure_or_horizon_reset",
    "lighting_or_texture_reset",
    "mirror_or_reverse_shortcut",
    "salient_periodic_cadence",
    "orientation_or_gravity_break",
    "alpha_halo_or_matte_contamination",
    "intended_behavior_mismatch",
    "insufficient_evidence",
)


@dataclass(frozen=True, slots=True)
class ImageRepeatValidationPolicy:
    """Versioned deterministic thresholds in normalized visual-channel units.

    A join is judged against the picture it sits in, not against fixed numbers. The same step
    statistics are measured at evenly spaced interior columns, which are continuous by definition,
    and a join fails when its mean step exceeds ``interior_quantile`` of those by more than
    ``interior_margin``. Detailed cut-out art has silhouette edges in almost every column, so any
    fixed limit either passes a flat seam or rejects the art's own interior; version 2 did the
    second, refusing 38 to 42 of 43 cuts through an untouched village drawing on single-pixel
    maxima. The floors only stop a flat picture, whose interior steps are near zero, from failing
    on noise. Per-row p95 and max are still measured and recorded, but a single row is not a seam,
    so they do not decide the verdict.
    """

    scales: tuple[float, ...] = (1.0,)
    interior_quantile: float = 0.95
    interior_margin: float = 1.5
    color_mae_floor: float = 0.004
    gradient_mae_floor: float = 0.004
    alpha_mae_floor: float = 0.004
    coverage_mismatch_ratio: float = 0.10
    coverage_alpha_threshold: float = 0.05

    def __post_init__(self) -> None:
        if not self.scales or self.scales[0] != 1.0:
            raise ValueError("image-repeat validation scales must start with 1.0")
        if len(set(self.scales)) != len(self.scales):
            raise ValueError("image-repeat validation scales must be unique")
        for scale in self.scales:
            _bounded_finite(scale, "validation scale", minimum=0.01, maximum=1.0)
        for name in (
            "color_mae_floor",
            "gradient_mae_floor",
            "alpha_mae_floor",
            "coverage_mismatch_ratio",
            "coverage_alpha_threshold",
        ):
            _bounded_finite(getattr(self, name), name, minimum=0.0, maximum=1.0)
        _bounded_finite(self.interior_quantile, "interior_quantile", minimum=0.5, maximum=1.0)
        _bounded_finite(self.interior_margin, "interior_margin", minimum=1.0, maximum=10.0)


@dataclass(frozen=True, slots=True)
class ImageRepeatStitch:
    """Where a construction cut provider pixels into a unit, and how far the two pictures differed.

    ``positions`` names, on every cross-axis line, the first pixel on the far side of the cut. The
    disagreements are mean absolute differences between the two pictures across the blended zone,
    in premultiplied colour and in alpha. Only the construction can measure them, because the unit
    keeps one picture on each side; they matter because a blend of two different pictures reads as
    a ghost even when no single step across the stitch is large.
    """

    positions: tuple[int, ...]
    color_disagreement: float
    alpha_disagreement: float

    def __post_init__(self) -> None:
        if not self.positions:
            raise ValueError("an image-repeat stitch needs at least one position")
        _bounded_finite(self.color_disagreement, "color_disagreement", minimum=0.0, maximum=1.0)
        _bounded_finite(self.alpha_disagreement, "alpha_disagreement", minimum=0.0, maximum=1.0)


class ImageRepeatScaleMetrics(PersistedContractModel):
    """One join at one scale. The ``*_limit`` fields bound the matching ``*_mae``.

    Each limit is the policy's interior quantile of that mean over ``interior_samples`` interior
    columns, times the interior margin, never below the policy floor.
    """

    scale: float = Field(gt=0, le=1, allow_inf_nan=False)
    boundary_width_px: int = Field(ge=1)
    color_mae: float = Field(ge=0, le=1, allow_inf_nan=False)
    color_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    color_max: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_mae: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_max: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_mae: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_p95: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_max: float = Field(ge=0, le=1, allow_inf_nan=False)
    coverage_mismatch_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    interior_samples: int = Field(ge=1)
    color_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    gradient_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    alpha_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    coverage_limit: float = Field(ge=0, le=1, allow_inf_nan=False)
    #: Set on a stitch at full scale: how far the two stitched pictures differed where they were
    #: blended, judged against ``color_limit`` and ``alpha_limit``.
    color_disagreement: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    alpha_disagreement: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class ImageRepeatJoinReport(PersistedContractModel):
    # ``stitch`` is a curved join inside a constructed unit, where a provider's repaint was cut
    # into the source; ``wrap`` is the unit meeting its own next repeat.
    name: Literal["wrap", "stitch"]
    verdict: Literal["pass", "reject"]
    scales: list[ImageRepeatScaleMetrics] = Field(min_length=1)
    failure_codes: list[ImageRepeatFailureCode]

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        _validate_unique_codes(self.failure_codes)
        if self.verdict == "pass" and self.failure_codes:
            raise ValueError("passing join report must not contain failure codes")
        if self.verdict == "reject" and not self.failure_codes:
            raise ValueError("rejected join report must contain failure codes")
        return self


class ImageRepeatDeterministicReport(PersistedContractModel):
    validator_version: Literal["single-axis-continuity-v3"] = DETERMINISTIC_VALIDATOR_VERSION
    axis: ImageRepeatAxis
    verdict: Literal["pass", "reject"]
    alpha_policy: ImageRepeatAlphaPolicy
    coverage_policy: ImageRepeatCoveragePolicy
    source_immutable: bool
    joins: list[ImageRepeatJoinReport] = Field(min_length=1, max_length=3)
    failure_codes: list[ImageRepeatFailureCode]

    @model_validator(mode="after")
    def validate_verdict(self) -> Self:
        _validate_unique_codes(self.failure_codes)
        join_codes = _unique_codes(code for join in self.joins for code in join.failure_codes)
        if any(code not in self.failure_codes for code in join_codes):
            raise ValueError("deterministic report must include every join failure code")
        if self.verdict == "pass":
            if self.failure_codes or any(join.verdict != "pass" for join in self.joins):
                raise ValueError("passing deterministic report must contain only passing joins")
            if not self.source_immutable:
                raise ValueError("passing deterministic report must preserve the source")
        elif not self.failure_codes:
            raise ValueError("rejected deterministic report must contain failure codes")
        return self


def _validate_unique_codes(codes: list[ImageRepeatFailureCode]) -> None:
    if len(codes) != len(set(codes)):
        raise ValueError("image-repeat failure codes must be unique")
    if any(code not in IMAGE_REPEAT_FAILURE_CODES for code in codes):
        raise ValueError("image-repeat failure code is not recognized")


def _unique_codes(codes: Iterable[ImageRepeatFailureCode]) -> list[ImageRepeatFailureCode]:
    result: list[ImageRepeatFailureCode] = []
    for code in codes:
        if code not in result:
            result.append(code)
    return result


def _bounded_finite(
    value: object,
    label: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(f"{label} must be finite from {minimum:g} to {maximum:g}")
