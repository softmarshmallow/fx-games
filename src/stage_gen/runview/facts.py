"""Intrinsic file facts a view shows beside a file: size and alpha for images, length for sound
and video.

Facts are measurements of the bytes, never judgements: ``width``, ``height``, ``has_alpha`` and
``opaque`` for an image; ``duration`` (seconds) for a WAV file; and ``width``, ``height``,
``duration``, ``fps``, ``frames`` and ``has_alpha`` for a video, read by ``ffprobe`` when it is
installed.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import wave
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from typing import Any

from PIL import Image

#: What reads a file's facts: its path, its kind and its digest.
FactsReader = Callable[[Path, str, str], dict[str, Any]]

_CACHE: dict[str, dict[str, Any]] = {}


def file_facts(path: Path, kind: str, digest: str) -> dict[str, Any]:
    """What can be measured from the file's bytes; empty when its kind has no facts."""

    cached = _CACHE.get(digest)
    if cached is not None:
        return dict(cached)
    facts: dict[str, Any] = {}
    if kind.startswith("image"):
        try:
            with Image.open(path) as picture:
                facts["width"], facts["height"] = picture.size
                bands = picture.getbands()
                facts["has_alpha"] = "A" in bands or "transparency" in picture.info
                try:
                    if facts["has_alpha"]:
                        alpha = picture.convert("RGBA").getchannel("A")
                        facts["opaque"] = alpha.getextrema() == (255, 255)
                    else:
                        facts["opaque"] = True
                except OSError:
                    pass  # the header reads but the pixels do not: only what was measured
        except OSError:
            facts = {}
    elif kind.startswith("video"):
        facts.update(_video_facts(path))
    elif kind in {"audio/wav", "audio/x-wav", "audio"}:
        try:
            with wave.open(str(path)) as clip:
                facts["duration"] = round(clip.getnframes() / clip.getframerate(), 6)
        except (OSError, EOFError, wave.Error):
            pass
    _CACHE[digest] = facts
    return dict(facts)


#: Pixel formats that carry an alpha channel.
_ALPHA_FORMATS = frozenset(
    {"rgba", "bgra", "argb", "abgr", "yuva420p", "yuva422p", "yuva444p", "gbrap", "ya8"}
)


def _video_facts(path: Path) -> dict[str, Any]:
    """The first video stream's size, length, rate and frame count; empty without ffprobe."""

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return {}
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-count_packets",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration,nb_read_packets,pix_fmt:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120, check=True)
        probe = json.loads(result.stdout)
        stream = probe["streams"][0]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError):
        return {}
    facts: dict[str, Any] = {}
    if isinstance(stream.get("width"), int) and isinstance(stream.get("height"), int):
        facts["width"], facts["height"] = stream["width"], stream["height"]
    try:
        rate = Fraction(str(stream["r_frame_rate"]))
        if rate > 0:
            facts["fps"] = round(float(rate), 6)
    except (KeyError, ValueError, ZeroDivisionError):
        pass
    duration = stream.get("duration") or probe.get("format", {}).get("duration")
    with contextlib.suppress(TypeError, ValueError):
        facts["duration"] = round(float(duration), 6)
    if str(stream.get("nb_read_packets", "")).isdigit():
        facts["frames"] = int(stream["nb_read_packets"])
    if isinstance(stream.get("pix_fmt"), str):
        facts["has_alpha"] = stream["pix_fmt"] in _ALPHA_FORMATS
    return facts


__all__ = ["FactsReader", "file_facts"]
