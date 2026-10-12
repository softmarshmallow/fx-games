"""Make a movie-sprite example from the FX run that drew or adopted a clip and finished it."""

from __future__ import annotations

from fx_games.examples import (
    Delivered,
    FxRun,
    ImportRequest,
    WorkflowExample,
    import_fx_run,
    sha256,
    video_frames,
)
from fx_games.workflows._fx import FxWorkflow


def deliver(run: FxRun) -> Delivered:
    """The character picture a take was drawn from, if any, and the finished loop.

    A run that finished supplied footage has no character picture among its inputs.
    """
    reader, media = run.request.reader, run.request.media
    character = run.input_file("character")
    inputs = (
        {}
        if character is None
        else {
            "character": {
                "kind": "image",
                "picture": media.still_alpha("input.webp", character[0], 720),
                "file": character[1],
            }
        }
    )
    loop = run.output("loop")
    manifest = reader.json(run.output("manifest"))
    poster = media.sequence(
        "output-loop.webp",
        video_frames(reader.path(loop), alpha=True),
        round(1000 / manifest["playback_fps"]),
        [loop],
        "every frame of the loop at its playback rate",
        max_height=640,
        quality=72,
    )
    return Delivered(
        inputs=inputs,
        outputs={
            "loop": {
                "kind": "animation",
                "file": loop.name,
                "bytes": loop.stat().st_size,
                "sha256": sha256(loop),
                "poster": poster,
            }
        },
        metrics={
            "loop_seconds": manifest["playback_seconds"],
            "frames": manifest["frame_count"],
        },
    )


def import_example(request: ImportRequest) -> WorkflowExample:
    workflow = FxWorkflow.read(__package__ or "fx_games.workflows.movie_sprite")
    return import_fx_run(
        request, type_of=lambda step: workflow.types[step].type_id, deliver=deliver
    )
