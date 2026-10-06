"""Afterlight's voice preparation on FX, offline: the inventory rules, and whole stand-in runs.

The speech calls are answered by a stand-in; a synthetic sine MP3 is the decoder fixture and
digital silence the read the judge refuses. Nothing reaches a provider.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from grida.fx import Answer, CallFailed, PlanRefused, RunResult, StandInCall, run

from stage_gen.workflows._fx import write_project

AFTERLIGHT = Path(__file__).resolve().parents[2]
NODES = AFTERLIGHT / "tools/voice_nodes.py"
SPEC = importlib.util.spec_from_file_location("afterlight_voice_nodes", NODES)
assert SPEC and SPEC.loader
voice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(voice)

PROFILE = {
    "provider": "elevenlabs",
    "model": "eleven_v3",
    "provider_voice": "voice_fixture",
    "language_code": "en",
    "stability": 0.5,
    "output_format": "mp3_44100_192",
}


def raw_line(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "line_id": "episode.fixture",
        "language": "en",
        "speaker_id": "nami",
        "display_text": "You found me.",
        "speech_text": "[warmly] You found me.",
        "voice_policy": "generated",
        "source_revision": "a" * 64,
        "voice_profile": dict(PROFILE),
    }
    raw.update(changes)
    return raw


def line(**changes: Any) -> dict[str, Any]:
    validated: dict[str, Any] = voice.validate_inventory(
        {"schema_version": 1, "lines": [raw_line(**changes)]}
    )[0]
    return validated


def _mp3(tmp_path: Path, source: str) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "the voice checks need ffmpeg"
    path = tmp_path / f"{source.split('=')[0]}.mp3"
    subprocess.run(
        [
            *(ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", source),
            *("-c:a", "libmp3lame", "-b:a", "192k", str(path)),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


@pytest.fixture(scope="module")
def tone(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return _mp3(tmp_path_factory.mktemp("tone"), "sine=frequency=440:duration=0.5")


@pytest.fixture(scope="module")
def silence(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    return _mp3(tmp_path_factory.mktemp("silence"), "anullsrc=r=44100:cl=mono:d=0.5")


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRIDA_FX_PYTHON", sys.executable)
    monkeypatch.setenv("GRIDA_FX_DISABLE_DOTENV", "1")
    monkeypatch.setenv("GRIDA_FX_NETWORK", "off")


class Speaker:
    """Answers every read with the next of ``reads`` (the last one repeats), or fails it."""

    def __init__(self, *reads: bytes, fail: bool = False) -> None:
        self.reads = list(reads)
        self.fail = fail
        self.calls: list[StandInCall] = []

    def __call__(self, call: StandInCall) -> Answer:
        assert call.capability == "speech.generate"
        self.calls.append(call)
        if self.fail:
            raise CallFailed("synthetic provider failure")
        read = self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]
        return Answer(files={"audio": read})


def _project(tmp_path: Path) -> Path:
    # A home's route tables apply only when it is the planning project, so this one names it.
    return write_project(
        tmp_path / "project",
        runs="runs",
        cache="cache",
        workflows=(AFTERLIGHT / "tools",),
        route_tables=(AFTERLIGHT / "tools/voice-routes.yaml",),
    )


def _write(path: Path, document: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _run(
    tmp_path: Path,
    speaker: Callable[[StandInCall], Answer],
    lines: list[dict[str, Any]],
    *,
    folder: str = "one",
    prepared: dict[str, Any] | None = None,
    installed: dict[str, bytes] | None = None,
) -> RunResult:
    """``installed`` maps game paths to clip bytes; it is given as the documented glob."""
    project = _project(tmp_path)
    inputs: dict[str, Any] = {
        "inventory": _write(tmp_path / "inventory.json", {"schema_version": 1, "lines": lines})
    }
    if prepared is not None:
        inputs["prepared"] = _write(tmp_path / "manifest.json", prepared)
    if installed is not None:
        for path, data in installed.items():
            (project / "game" / path).parent.mkdir(parents=True, exist_ok=True)
            (project / "game" / path).write_bytes(data)
        inputs["installed"] = f"game/{voice.CLIPS}/*/*.mp3"
    return run(
        "afterlight-voice",
        inputs=inputs,
        cwd=project,
        run_dir=project / "runs" / folder,
        stand_in=speaker,
    )


def test_explicit_none_languages_actual_speaker_and_stale_inputs() -> None:
    base = line()
    alternate = line(line_id="episode.reply.tea", speaker_id="yuzu")
    korean_profile = {**base["voice_profile"], "language_code": "ko"}
    korean = line(language="ko", voice_profile=korean_profile, speech_text="여기에 있었네요.")
    silent = line(speaker_id="protagonist", voice_policy="none", voice_profile={})
    rows = voice.validate_inventory({"schema_version": 1, "lines": [base, alternate, korean]})
    assert len(rows) == 3 and alternate["speaker_id"] == "yuzu"
    assert silent["voice_policy"] == "none"
    with pytest.raises(ValueError, match="protagonist"):
        line(speaker_id="protagonist")
    for change in (
        {"display_text": "Different display."},
        {"speech_text": "Different read."},
        {"speaker_id": "yuzu"},
        {"source_revision": "b" * 64},
        {"voice_profile": {**base["voice_profile"], "stability": 1.0}},
    ):
        assert line(**change)["preparation_revision"] != base["preparation_revision"]
    assert (
        line(status="ready", path="res://installed.mp3")["preparation_revision"]
        == base["preparation_revision"]
    )
    with pytest.raises(ValueError, match="output"):
        line(voice_profile={**base["voice_profile"], "output_format": "pcm_44100"})


def test_two_voiced_lines_are_spoken_once_and_laid_out_at_their_game_paths(
    tmp_path: Path, tone: bytes
) -> None:
    lines = [
        raw_line(),
        raw_line(line_id="episode.reply.tea", speaker_id="yuzu", speech_text="Tea, then."),
        raw_line(line_id="episode.choice", speaker_id="protagonist", voice_policy="none"),
    ]
    speaker = Speaker(tone)
    result = _run(tmp_path, speaker, lines)

    assert result.ok, result.failures
    assert sorted(call.request["text"] for call in speaker.calls) == [
        "Tea, then.",
        "[warmly] You found me.",
    ]
    assert {call.request["voice"] for call in speaker.calls} == {"voice_fixture"}
    assert {call.request["language_code"] for call in speaker.calls} == {"en"}
    game = tmp_path / "game"
    assert result.deliver({"files": "{key}"}, root=game) == []
    first = line()
    clip = game / voice.clip_path(first)
    assert clip.read_bytes() == tone
    manifest = json.loads((game / voice.MANIFEST).read_text(encoding="utf-8"))
    assert manifest["preparation"] == {"skipped_none": 1, "ready": 2, "kept": 0, "generated": 2}
    assert list(manifest["lines"]["en"]) == ["episode.fixture", "episode.reply.tea"]
    record = manifest["lines"]["en"]["episode.fixture"]
    assert record["path"] == f"res://{voice.clip_path(first)}"
    assert record["preparation_revision"] == first["preparation_revision"]
    assert record["audio_sha256"] == hashlib.sha256(tone).hexdigest()
    assert record["duration_seconds"] > 0.4 and record["listening_verdict"] == "not_reviewed"
    assert record["speaker_id"] == "nami" and record["voice_profile"] == PROFILE

    again = Speaker(tone)
    assert _run(tmp_path, again, lines, folder="two").ok
    assert again.calls == []


def test_a_silent_read_is_refused_and_read_again(
    tmp_path: Path, tone: bytes, silence: bytes
) -> None:
    speaker = Speaker(silence, tone)
    result = _run(tmp_path, speaker, [raw_line()])

    assert result.ok, result.failures
    assert [call.take for call in speaker.calls] == [1, 2]
    game = tmp_path / "game"
    result.deliver({"files": "{key}"}, root=game)
    assert (game / voice.clip_path(line())).read_bytes() == tone


def _installed(kept: dict[str, Any], audio: bytes) -> dict[str, Any]:
    """The manifest record of ``kept`` as a pass laid it out, for the clip ``audio``."""
    return {
        "status": "ready",
        "path": f"res://{voice.clip_path(kept)}",
        "source_revision": kept["source_revision"],
        "preparation_revision": kept["preparation_revision"],
        "audio_sha256": hashlib.sha256(audio).hexdigest(),
        "duration_seconds": 0.5,
        "speaker_id": "nami",
        "provider": "elevenlabs",
        "model": "eleven_v3",
        "voice_profile": PROFILE,
        "listening_verdict": "not_reviewed",
    }


def _prepared(**records: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, "lines": {"en": records, "ko": {}}}


TEA = {"line_id": "episode.reply.tea", "speech_text": "Tea, then."}


def test_a_line_whose_installed_clip_backs_its_record_is_kept_without_a_call(
    tmp_path: Path, tone: bytes
) -> None:
    kept = line()
    record = _installed(kept, tone)
    stale = {**_installed(line(**TEA), tone), "preparation_revision": "d" * 64}
    prepared = _prepared(**{"episode.fixture": record, "episode.reply.tea": stale})
    speaker = Speaker(tone)
    result = _run(
        tmp_path,
        speaker,
        [raw_line(), raw_line(**TEA)],
        prepared=prepared,
        installed={voice.clip_path(kept): tone},
    )

    assert result.ok, result.failures
    assert [call.request["text"] for call in speaker.calls] == ["Tea, then."]
    manifest = json.loads(result.outputs["manifest"].read_bytes())
    assert manifest["lines"]["en"]["episode.fixture"] == record
    assert manifest["preparation"] == {"skipped_none": 0, "ready": 2, "kept": 1, "generated": 1}
    assert sorted(result.outputs["files"]) == [voice.MANIFEST, voice.clip_path(line(**TEA))]


def test_a_ready_record_whose_clip_is_missing_is_spoken_again(tmp_path: Path, tone: bytes) -> None:
    # A fresh clone: the manifest is tracked, the clips are not, so the glob finds nothing.
    prepared = _prepared(**{"episode.fixture": _installed(line(), tone)})
    speaker = Speaker(tone)
    result = _run(tmp_path, speaker, [raw_line()], prepared=prepared, installed={})

    assert result.ok, result.failures
    assert [call.request["text"] for call in speaker.calls] == ["[warmly] You found me."]
    manifest = json.loads(result.outputs["manifest"].read_bytes())
    assert manifest["preparation"]["kept"] == 0 and manifest["preparation"]["generated"] == 1
    assert voice.clip_path(line()) in result.outputs["files"]


@pytest.mark.parametrize("case", ["tampered", "undecodable", "elsewhere"])
def test_an_installed_clip_that_disagrees_with_its_record_fails_the_plan(
    tmp_path: Path, tone: bytes, silence: bytes, case: str
) -> None:
    kept = line()
    record = _installed(kept, tone)
    clip = tone
    if case == "tampered":
        clip = silence  # a different file at the line's path
    elif case == "undecodable":
        record, clip = _installed(kept, silence), silence  # the digest agrees; the read is silent
    else:
        record = {**record, "path": "res://voice/clips/en/somewhere-else.mp3"}
    speaker = Speaker(tone)
    with pytest.raises(PlanRefused, match="reconcile") as refused:
        _run(
            tmp_path,
            speaker,
            [raw_line()],
            prepared=_prepared(**{"episode.fixture": record}),
            installed={voice.clip_path(kept): clip},
        )

    assert speaker.calls == []
    assert "en/episode.fixture" in str(refused.value)


def test_a_prepared_manifest_without_its_clips_is_refused(tmp_path: Path, tone: bytes) -> None:
    prepared = _prepared(**{"episode.fixture": _installed(line(), tone)})
    speaker = Speaker(tone)
    with pytest.raises(PlanRefused, match="--installed"):
        _run(tmp_path, speaker, [raw_line()], prepared=prepared)

    assert speaker.calls == []


def test_a_failed_call_fails_the_line_and_lays_out_nothing(tmp_path: Path) -> None:
    result = _run(tmp_path, Speaker(fail=True), [raw_line()])

    assert not result.ok
    speak = [failure for id_, failure in result.failures.items() if ".speak#" in id_]
    assert speak and "synthetic provider failure" in speak[0].message
    assert result.failures["layout#1"].skipped
