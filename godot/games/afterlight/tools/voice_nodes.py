"""The node types of Afterlight's voice preparation (``tools/voice.yaml``); never imported by Godot.

``voiced_lines`` reads the exported inventory while planning: each line's preparation identity,
the lines the installed manifest already holds at the same revisions whose installed clips
still hash and decode as recorded (kept, never spoken again), and the lines to speak.
``admit_line`` judges a read: a playable, unclipped MP3, or it is read again. ``layout`` names
each new clip by its game path and writes the manifest, its records in the shape the game reads.
See AFTERLIGHT_VOICE_PREPARATION.md.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any

from grida.fx import Ctx, node

from stage_gen.components.speech import speech_admission_facts
from stage_gen.media import measure_level_and_duration

LINE_ID = re.compile(r"^[a-z][a-z0-9_.]*$")
DIGEST = re.compile(r"^[a-f0-9]{64}$")
LANGUAGES = ("en", "ko")
#: Where the clips live in the game, and where a pass's candidate manifest goes.
CLIPS = "voice/clips"
MANIFEST = "art/voiceovers-p95/manifest.json"
_TIMEOUT_SECONDS = 120
#: An installed clip that is absent: its line is spoken again.
_MISSING = "missing"


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def validate_inventory(value: dict[str, Any]) -> list[dict[str, Any]]:
    if value.get("schema_version") != 1 or not isinstance(value.get("lines"), list):
        raise ValueError("expected a version 1 exported voice inventory")
    lines, seen = [], set()
    for raw in value["lines"]:
        line = dict(raw)
        for key in (
            "line_id",
            "language",
            "speaker_id",
            "display_text",
            "speech_text",
            "voice_policy",
            "source_revision",
        ):
            if not isinstance(line.get(key), str):
                raise ValueError(f"inventory {key} must be a string")
        if not LINE_ID.fullmatch(line["line_id"]) or not LINE_ID.fullmatch(line["speaker_id"]):
            raise ValueError("line and speaker IDs must be stable lowercase identifiers")
        if line["language"] not in ("en", "ko"):
            raise ValueError("this local pass supports English and Korean")
        language_line = (line["language"], line["line_id"])
        if language_line in seen:
            raise ValueError("duplicate language/line ID")
        seen.add(language_line)
        if not DIGEST.fullmatch(line["source_revision"]):
            raise ValueError("source_revision must be a SHA-256 digest from the host")
        if line["voice_policy"] not in ("none", "generated"):
            raise ValueError("voice_policy must explicitly be none or generated")
        if line["speaker_id"] == "protagonist" and line["voice_policy"] != "none":
            raise ValueError("the protagonist is unvoiced in this pass")
        if line["voice_policy"] == "generated":
            if (
                not line["display_text"].strip()
                or not line["speech_text"].strip()
                or len(line["speech_text"]) > 5000
            ):
                raise ValueError("generated lines need display and nonempty speech text")
            profile = line.get("voice_profile")
            if not isinstance(profile, dict):
                raise ValueError("generated lines need a resolved voice_profile")
            if profile.get("provider") != "elevenlabs" or profile.get("model") != "eleven_v3":
                raise ValueError("this pass uses the existing ElevenLabs v3 speech route")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", str(profile.get("provider_voice", ""))):
                raise ValueError("provider_voice must be an explicit provider ID")
            if profile.get("language_code") != line["language"]:
                raise ValueError("profile language_code must match the line language")
            if profile.get("output_format", "mp3_44100_192") != "mp3_44100_192":
                raise ValueError("this existing speech route output is mp3_44100_192")
            stability = profile.get("stability", 0.5)
            if isinstance(stability, bool) or stability not in (0.0, 0.5, 1.0):
                raise ValueError("ElevenLabs v3 stability must be 0, 0.5 or 1")
        line["preparation_revision"] = digest(
            {
                key: line.get(key)
                for key in (
                    "line_id",
                    "language",
                    "speaker_id",
                    "display_text",
                    "speech_text",
                    "voice_policy",
                    "source_revision",
                    "voice_profile",
                )
            }
        )
        lines.append(line)
    if not lines:
        raise ValueError("inventory is empty")
    return lines


def clip_path(line: dict[str, Any]) -> str:
    """A line's clip, relative to the game: its language, its id and its preparation."""
    return f"{CLIPS}/{line['language']}/{line['line_id']}-{line['preparation_revision'][:16]}.mp3"


def _kept(prepared: dict[str, Any] | None, line: dict[str, Any]) -> dict[str, Any] | None:
    """The installed record of a line, when it says it is ready at the line's revisions."""
    if prepared is None:
        return None
    record = prepared.get("lines", {}).get(line["language"], {}).get(line["line_id"])
    if (
        isinstance(record, dict)
        and record.get("status") == "ready"
        and record.get("preparation_revision") == line["preparation_revision"]
        and record.get("source_revision") == line["source_revision"]
    ):
        return record
    return None


def _installed_by_stem(value: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    """The installed clips by file stem (``<line_id>-<revision16>``), as a files glob keys them."""
    files = list(value.values()) if isinstance(value, dict) else list(value or [])
    by_stem: dict[str, Any] = {}
    for file in files:
        stem = file.key or PurePosixPath(file.name).stem
        if stem in by_stem:
            raise ValueError(f"two installed clips share the name {stem}")
        by_stem[stem] = file
    return by_stem


async def _installed_problem(
    ctx: Ctx, record: dict[str, Any], line: dict[str, Any], installed: dict[str, Any]
) -> str | None:
    """Why the installed clip does not back ``record``; ``None`` when it does.

    The clip must sit at the line's path, hash to the record's ``audio_sha256`` and decode as a
    playable, unclipped read. A missing clip is ``_MISSING``: the line is spoken again."""
    path = clip_path(line)
    if record.get("path") != f"res://{path}":
        return f"the manifest names {record.get('path')}, not res://{path}"
    clip = installed.get(PurePosixPath(path).stem)
    if clip is None:
        return _MISSING
    data = clip.read_bytes()
    if hashlib.sha256(data).hexdigest() != record.get("audio_sha256"):
        return f"{path} does not hash to the manifest's audio_sha256"
    try:
        await _read_facts(ctx, data)
    except ValueError as error:
        return f"{path} does not decode as a playable read: {error}"
    return None


@node(
    "voiced_lines",
    inputs={"inventory": "json", "prepared": "json?", "installed": "audio{}?"},
    outputs={"lines": "json"},
    tools=["ffmpeg"],
    version=2,
)
async def voiced_lines(ctx: Ctx) -> dict[str, Any]:
    """The lines to speak, and the installed lines kept at the same revisions.

    A line is kept only when its installed clip backs the manifest record: at its path, with its
    digest, and decoding again. A line whose clip is missing is spoken again; a clip that is
    present but disagrees fails the plan for reconciliation, never re-spoken automatically."""

    try:
        lines = validate_inventory(ctx.read.json("inventory"))
    except ValueError as error:
        raise ctx.fail(f"voice inventory: {error}") from None
    prepared = ctx.read.json("prepared") if ctx.inputs.get("prepared") is not None else None
    if prepared is not None and ctx.inputs.get("installed") is None:
        raise ctx.fail(
            "a prepared manifest is kept only against its clips: pass the installed clips too "
            "(--installed 'voice/clips/*/*.mp3')"
        )
    try:
        installed = _installed_by_stem(ctx.inputs.get("installed"))
    except ValueError as error:
        raise ctx.fail(f"installed clips: {error}") from None
    generate: list[dict[str, Any]] = []
    kept: dict[str, dict[str, Any]] = {language: {} for language in LANGUAGES}
    blocked: list[str] = []
    for line in lines:
        if line["voice_policy"] == "none":
            continue
        record = _kept(prepared, line)
        if record is not None:
            problem = await _installed_problem(ctx, record, line, installed)
            if problem is None:
                kept[line["language"]][line["line_id"]] = record
                continue
            if problem != _MISSING:
                blocked.append(f"{line['language']}/{line['line_id']}: {problem}")
                continue
        profile = line["voice_profile"]
        path = clip_path(line)
        generate.append(
            {
                "key": path.removeprefix(f"{CLIPS}/").removesuffix(".mp3"),
                "text": line["speech_text"],
                "voice": profile["provider_voice"],
                "stability": profile.get("stability", 0.5),
                "language_code": profile["language_code"],
                "record": {
                    "line_id": line["line_id"],
                    "language": line["language"],
                    "speaker_id": line["speaker_id"],
                    "source_revision": line["source_revision"],
                    "preparation_revision": line["preparation_revision"],
                    "voice_profile": profile,
                    "path": path,
                },
            }
        )
    if blocked:
        raise ctx.fail(
            "installed clips disagree with the manifest; reconcile them before a pass "
            "(no line is spoken again automatically): " + "; ".join(blocked)
        )
    skipped = sum(line["voice_policy"] == "none" for line in lines)
    return {
        "lines": ctx.out.json(
            {"generate": generate, "kept": kept, "skipped_none": skipped, "order": _order(lines)}
        )
    }


def _order(lines: list[dict[str, Any]]) -> list[list[str]]:
    """Every voiced line as ``[language, line_id]``, in inventory order."""
    return [[line["language"], line["line_id"]] for line in lines if line["voice_policy"] != "none"]


async def _read_facts(ctx: Ctx, data: bytes) -> dict[str, object]:
    measured = await measure_level_and_duration(
        data, ffmpeg=str(ctx.tool("ffmpeg").executable), timeout_seconds=_TIMEOUT_SECONDS
    )
    return speech_admission_facts(data, measured, max_seconds=None)


@node("admit_line", inputs={"audio": "audio"}, tools=["ffmpeg"], judge=True, version=1)
async def admit_line(ctx: Ctx) -> dict[str, Any]:
    """A playable, unclipped read, or it is read again."""

    try:
        facts = await _read_facts(ctx, ctx.read.bytes("audio"))
    except ValueError as error:
        ctx.fact("errors", [str(error)])
        ctx.fact("verdict", "reject")
        return {}
    ctx.fact("admission", facts)
    ctx.fact("verdict", "accept")
    return {}


@node(
    "layout",
    inputs={"lines": "json", "clips": "audio{}"},
    outputs={"files": "file{}", "manifest": "json"},
    tools=["ffmpeg"],
    version=1,
)
async def layout(ctx: Ctx) -> dict[str, Any]:
    """Each new clip at its game path, and the manifest of every voiced line."""

    lines = ctx.read.json("lines")
    clips = ctx.inputs.get("clips", {})
    records: dict[str, dict[str, Any]] = {language: {} for language in LANGUAGES}
    files: dict[str, Any] = {}
    for item in lines["generate"]:
        clip = clips.get(item["key"])
        if clip is None:
            raise ctx.fail(f"{item['key']} has no admitted read")
        line = item["record"]
        facts = await _read_facts(ctx, clip.read_bytes())
        profile = line["voice_profile"]
        records[line["language"]][line["line_id"]] = {
            "status": "ready",
            "path": f"res://{line['path']}",
            "source_revision": line["source_revision"],
            "preparation_revision": line["preparation_revision"],
            "audio_sha256": hashlib.sha256(clip.read_bytes()).hexdigest(),
            "duration_seconds": facts["duration_seconds"],
            "speaker_id": line["speaker_id"],
            "provider": profile["provider"],
            "model": profile["model"],
            "voice_profile": profile,
            "listening_verdict": "not_reviewed",
        }
        files[line["path"]] = clip
    for language, kept in lines["kept"].items():
        records[language].update(kept)
    ordered: dict[str, dict[str, Any]] = {language: {} for language in LANGUAGES}
    for language, line_id in lines["order"]:
        ordered[language][line_id] = records[language][line_id]
    generated = len(lines["generate"])
    kept_count = sum(len(kept) for kept in lines["kept"].values())
    manifest = {
        "schema_version": 1,
        "lines": ordered,
        "preparation": {
            "skipped_none": lines["skipped_none"],
            "ready": generated + kept_count,
            "kept": kept_count,
            "generated": generated,
        },
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    written = ctx.out.bytes(text.encode("utf-8"), "json")
    files[MANIFEST] = written
    return {"files": files, "manifest": written}


__all__ = ["admit_line", "clip_path", "digest", "layout", "validate_inventory", "voiced_lines"]
