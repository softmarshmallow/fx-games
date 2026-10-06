from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from stage_gen.image_prompting import (
    image_style_question,
    load_image_style_resources,
    materialize_style_anchor,
)
from stage_gen.image_style import StyleModeSelection
from stage_gen.resources import image_style_resource_digests


def test_resources_cover_every_recognized_mode_and_exact_asset_treatments() -> None:
    resources = load_image_style_resources()
    modes = {mode.style_mode: mode for mode in resources.vocabulary.modes}
    assert set(modes) == {
        "cel_shaded_anime_2d",
        "photorealistic_natural",
        "gouache_illustration_2d",
        "flat_graphic_2d",
    }
    assert modes["cel_shaded_anime_2d"].medium_keyword == ("clean 2D Japanese anime illustration")
    assert modes["photorealistic_natural"].medium_keyword == ("photorealistic natural photography")
    assert modes["gouache_illustration_2d"].medium_keyword == ("editorial gouache illustration")
    assert modes["flat_graphic_2d"].medium_keyword == ("flat graphic vector illustration")
    assert (
        "overlap and value steps"
        in modes["flat_graphic_2d"].asset_treatments["environment_background"]
    )
    assert (
        "visual novel character sprite"
        in modes["cel_shaded_anime_2d"].asset_treatments["character_sprite"]
    )
    assert (
        "visual novel background art"
        in modes["cel_shaded_anime_2d"].asset_treatments["environment_background"]
    )
    assert image_style_resource_digests() == {
        "skill_sha256": resources.skill.sha256,
        "vocabulary_sha256": resources.vocabulary_sha256,
    }


def test_the_style_question_offers_only_the_vocabulary_and_binds_its_resources(
    tmp_path: Path,
) -> None:
    resources = load_image_style_resources()
    prompt, system = image_style_question(
        "adult character in a lantern-lit plaza",
        ("environment_background", "character_sprite"),
        resources=resources,
    )
    assert set(StyleModeSelection.model_json_schema()["properties"]) == {
        "schema_version",
        "kind",
        "style_mode",
    }
    assert resources.skill.body.rstrip() in system
    assert "APPROVED_IMAGE_STYLE_VOCABULARY_JSON:\n" in system
    assert resources.vocabulary_document.rstrip() in system
    assert 'ASSET_KINDS_JSON: ["character_sprite","environment_background"]' in prompt
    assert 'CREATIVE_BRIEF_JSON_STRING: "adult character in a lantern-lit plaza"' in prompt
    with pytest.raises(ValueError, match="non-empty"):
        image_style_question("  ", ("character_sprite",), resources=resources)
    with pytest.raises(ValueError, match="unique"):
        image_style_question("brief", ("character_sprite", "character_sprite"))
    mutated_document = json.loads(resources.vocabulary_document)
    mutated_document["modes"][2]["observable_traits"][3] = "subtle paper grain"
    mutated_path = tmp_path / "mutated-vocabulary.json"
    mutated_path.write_text(json.dumps(mutated_document), encoding="utf-8")
    mutated = load_image_style_resources(vocabulary_path=mutated_path)
    assert mutated.resource_sha256 != resources.resource_sha256
    _, mutated_system = image_style_question("brief", ("character_sprite",), resources=mutated)
    assert "subtle paper grain" in mutated_system
    assert "subtle paper grain" not in system
    with pytest.raises(ValidationError):
        StyleModeSelection.model_validate(
            {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "cel_shaded_anime_2d",
                "medium_keyword": "invented edge text",
            }
        )
    anchor = materialize_style_anchor(
        StyleModeSelection.model_validate(
            {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": "cel_shaded_anime_2d",
            }
        ),
        resources,
    )
    assert anchor.resource_sha256 == resources.resource_sha256
    assert anchor.compiler_sha256 == resources.compiler_sha256
