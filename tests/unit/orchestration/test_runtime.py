from __future__ import annotations

import pytest

from gnode import (
    BackgroundRemovalRequest,
    ImageGenerationRequest,
    MusicGenerationRequest,
    StructuredGenerationRequest,
    StructuredOutputSchema,
)


def test_component_requests_reject_invalid_runtime_values() -> None:
    with pytest.raises(ValueError, match="temperature"):
        StructuredGenerationRequest(
            prompt="audit",
            artifact_path="x.json",
            schema=StructuredOutputSchema(name="x", json_schema={}),
            parse=lambda value: value,
            temperature=True,
        )
    with pytest.raises(ValueError, match="positive finite"):
        ImageGenerationRequest(
            prompt="audit",
            artifact_path="x.png",
            timeout_seconds=float("nan"),
        )
    with pytest.raises(ValueError, match="output_format"):
        BackgroundRemovalRequest(
            image_url="https://example.test/x.png",
            artifact_path="x.png",
            output_format="jpeg",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="top_p"):
        MusicGenerationRequest(
            prompt="audit",
            artifact_path="x.mp3",
            top_p=True,
        )
