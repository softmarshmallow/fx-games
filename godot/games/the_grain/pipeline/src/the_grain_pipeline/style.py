"""The style anchor: one approved style mode a model picks for a whole room or scene.

A structured call picks one mode from the packaged vocabulary for a creative brief; the
mode is materialized locally into a canonical anchor, and every image prompt ends with the
anchor's clause for its asset kind. The question, the schema and the materialization are
the shared style compiler's; this module only states them as a build's steps need them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fx_games.image_prompting import (
    image_style_question,
    load_image_style_resources,
    materialize_style_anchor,
)
from fx_games.image_style import (
    CanonicalStyleAnchor,
    ImageAssetKind,
    StyleModeSelection,
    render_style_anchor,
)


def style_question(brief: str, asset_kinds: Sequence[ImageAssetKind]) -> tuple[str, str]:
    """The prompt and the system prompt the style selection is asked with."""

    return image_style_question(brief, asset_kinds)


def style_schema() -> dict[str, Any]:
    """The selection's answer shape: one approved style mode."""

    return StyleModeSelection.model_json_schema()


def style_anchor(selection: object, asset_kinds: Sequence[ImageAssetKind]) -> CanonicalStyleAnchor:
    """The selected mode materialized into the canonical anchor, refused when it lacks a kind."""

    anchor = materialize_style_anchor(
        StyleModeSelection.model_validate(selection), load_image_style_resources()
    )
    for asset_kind in asset_kinds:
        if asset_kind not in anchor.asset_treatments:
            raise ValueError(f"selected style lacks treatment for {asset_kind!r}")
    return anchor


def style_clauses(
    anchor: CanonicalStyleAnchor, asset_kinds: Sequence[ImageAssetKind]
) -> dict[str, str]:
    """The clause each asset kind's prompts end with."""

    return {kind: render_style_anchor(anchor, kind) for kind in asset_kinds}


__all__ = ["style_anchor", "style_clauses", "style_question", "style_schema"]
