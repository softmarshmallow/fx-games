# Verified single-axis image repeat

`image_repeat` is the provider-neutral Python component for the contract:

> one image in, one image proven to repeat on a declared axis out

It owns deterministic seam measurement and the three-repeat preview. It does
not know whether the image will be used as a game background, foreground,
material, UI strip, or another repeating surface. Callers declare the axis and
the alpha and coverage policies; consumers decide how to render an admitted
repeat unit.

```python
validate_image_repeat(
    png,
    axis="x",
    alpha_policy=...,
    coverage_policy=...,
    validation_policy=ImageRepeatValidationPolicy(),
    stitches=...,
)
build_three_repeat_preview(png, axis="x")
```

## Admission

Admission reads the unit's bytes unchanged and evaluates only the declared
`x` or `y` wrap, plus every stitch a construction cut into the unit:

1. Measure the direct edge join, and hold it to the picture it sits in. The
   same colour, local-gradient and alpha steps are measured at evenly spaced
   interior lines, which are continuous by definition, and the join fails when
   its mean step on any of the three exceeds the policy's interior quantile of
   those by more than its margin (`single-axis-continuity-v3`: the 95th
   percentile, by more than 1.5×, never below a small floor that keeps a flat
   picture from failing on noise). Coverage is checked against a fixed ratio
   when the policy requires continuous coverage. Per-line p95 and maxima are
   recorded but do not decide the verdict: one line is not a seam, and
   detailed cut-out art has silhouette edges in almost every column, so any
   fixed per-pixel limit refuses the art's own interior. Version 2 refused 38
   to 42 of 43 cuts through an untouched village drawing that way; version 3
   refuses 7 of 396 such cuts across eleven Bellweather layers, and still
   refuses every visibly broken wrap among them.

   A construction that writes provider pixels into the unit also passes its
   **stitches**, the paths along which it cut them in. Each is judged like
   the wrap, on the step across it, and also on how far the two stitched
   pictures disagreed where they were blended, which only the construction
   can measure. A blend of two different pictures reads as a ghost even when
   no single step across it is large, so a stitch whose disagreement exceeds
   the colour or alpha limit fails as `clipped_or_disconnected_form`.
2. Build exactly three unmarked, pixel-identical copies on the declared axis
   and alpha-composite them over a versioned neutral checkerboard. The preview
   is opaque, so hidden RGB under zero alpha cannot show through, while
   partial alpha remains visible.

An edge alpha or an empty border is only one measured fact; it is never proof
that the image loops in the intended way.

## Scope and future challenge

The component supports one declared axis per operation: horizontal **or**
vertical. It intentionally does not claim or evaluate the other axis.

Two-axis tileability is a non-goal for this version. It is recorded as a future
challenge because satisfying four edges is not enough: all four corner
transitions, combined X/Y phase behavior, semantic cadence, and repair ordering
must also be proven without one axis invalidating the other. Do not represent a
single-axis result as a material tile that is safe on both axes.

## Verification

Credential-free gates:

```sh
uv run pytest tests/unit/components/image_repeat -q
```

Generated repeat units remain `unreviewed` for rights and publication unless a
separate authorized review records otherwise.
