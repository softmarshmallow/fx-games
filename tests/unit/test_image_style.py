from __future__ import annotations

import pytest
from pydantic import ValidationError

from stage_gen.image_prompting import load_image_style_resources, materialize_style_anchor
from stage_gen.image_style import (
    CanonicalStyleAnchor,
    StyleModeSelection,
    append_style_anchor_once,
    canonical_style_anchor_digest,
    render_style_anchor,
)


def _anchor(mode: str = "cel_shaded_anime_2d") -> CanonicalStyleAnchor:
    resources = load_image_style_resources()
    selection = StyleModeSelection.model_validate(
        {
            "schema_version": 1,
            "kind": "image_style_selection_v1",
            "style_mode": mode,
        }
    )
    return materialize_style_anchor(selection, resources)


def test_style_selection_is_strict_lower_snake_case() -> None:
    with pytest.raises(ValidationError):
        StyleModeSelection.model_validate(
            {
                "schemaVersion": 1,
                "kind": "image_style_selection_v1",
                "styleMode": "cel_shaded_anime_2d",
            }
        )
    with pytest.raises(ValidationError):
        StyleModeSelection.model_validate(
            {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "invented_mode",
            }
        )


def test_renderer_is_asset_aware_idempotent_and_digest_stable() -> None:
    anchor = _anchor()
    sprite = render_style_anchor(anchor, "character_sprite")
    background = render_style_anchor(anchor, "environment_background")
    assert "clean 2D Japanese anime illustration" in sprite
    assert "visual novel character sprite" in sprite
    assert "visual novel background art" in background
    assert sprite != background
    prompt = append_style_anchor_once(
        "Adult heroine at a summer festival.", anchor, "character_sprite"
    )
    assert prompt.count("Canonical style anchor — ") == 1
    assert append_style_anchor_once(prompt, anchor, "character_sprite") == prompt
    assert len(canonical_style_anchor_digest(anchor)) == 64


def test_renderer_rejects_missing_or_conflicting_treatment() -> None:
    anchor = _anchor()
    incomplete = anchor.model_copy(update={"asset_treatments": {"concept_art": "concept"}})
    with pytest.raises(ValueError, match="no asset treatment"):
        render_style_anchor(incomplete, "character_sprite")
    with pytest.raises(ValueError, match="already contains"):
        append_style_anchor_once(
            "Canonical style anchor — user-authored conflict",
            anchor,
            "character_sprite",
        )
