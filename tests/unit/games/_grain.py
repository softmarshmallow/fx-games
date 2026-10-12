"""The Grain's FX project in a scratch folder, and stand-ins for every paid call it makes.

A package's references are project files, so each test copies the game's project
(``fx.yaml``, the lock, ``pipeline/nodes`` and the builders) and puts the package it
builds inside it. Paid calls are answered offline with what the game's judges admit,
recognised by what they were asked for: an interface sheet by the template among its
pictures, a cut-out or a face by its transparent background, a chroma face by its canvas,
and a structured answer by the fields its schema declares.
"""

from __future__ import annotations

import hashlib
import io
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from grida.fx import Answer, InputFile, Plan, RunResult, StandInCall
from grida.fx import plan as plan_fx
from grida.fx import run as run_fx
from PIL import Image

from demo_game_collection.resources import bundled_music_path
from demo_game_tools.kits.ui_art.nodes import UI_SHEET_ROLES, sheet_family
from tests.unit._fx import game_project, schema_of
from tests.unit._ui_atlas_fixture import ui_sheet

REPOSITORY = Path(__file__).resolve().parents[3]
GAME = REPOSITORY / "godot/games/the_grain"
ROOM = "pipeline/workflow.py:room"
SCENE = "pipeline/workflow.py:scene"
STYLE_MODE = "cel_shaded_anime_2d"
_NARRATION_ID = re.compile(r'- id "([a-z0-9_-]+)"')


def grain_project(tmp_path: Path) -> Path:
    """The game's FX project in a scratch folder, with no package in it yet."""

    return game_project("the_grain", tmp_path)


def plan(project: Path, builder: str, package: str) -> Plan:
    return plan_fx(builder, cwd=project, arguments={"package": package})


def cover_digest(path: Path) -> str:
    """A package file's digest, as a request names a picture."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------------------- pictures


def png(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False)
    return stream.getvalue()


def _size(value: str) -> tuple[int, int]:
    width, height = (int(side) for side in value.split("x"))
    return width, height


def opaque(size: str) -> bytes:
    return png(Image.new("RGB", _size(size), (20, 30, 80)))


def cutout(size: str) -> bytes:
    """One isolated opaque subject on transparent ground."""

    width, height = _size(size)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((180, 140, 60, 255), (width // 4, height // 4, width - width // 4, height * 3 // 4))
    return png(image)


def keyed(size: str) -> bytes:
    """One subject on the chroma key, opaque everywhere."""

    width, height = _size(size)
    image = Image.new("RGB", (width, height), (255, 0, 255))
    image.paste((20, 30, 80), (width // 4, height // 6, width - width // 4, height * 5 // 6))
    return png(image)


def haze(size: str) -> bytes:
    """Half transparent everywhere, with no clear pixel. FX's check takes it, since it is not
    all opaque; a cut-out or face judge, which wants clear ground, does not."""

    return png(Image.new("RGBA", _size(size), (180, 140, 60, 128)))


# ------------------------------------------------------------------------------- stand-ins


class StandIns:
    """Every paid call a room or scene build makes, answered offline.

    ``refuse`` names kinds of answer (``cutout``, ``face``, ``narration``) and how many times
    each is answered wrongly before it is answered right, so a test can watch a judge send a
    take back. A wrong picture passes FX's own checks (the asked size, an alpha channel that is
    not all opaque) and is refused by the game's judge: a cut-out, or a native face, with no
    clear pixel.
    """

    def __init__(self, *, refuse: Mapping[str, int] | None = None) -> None:
        self.calls: Counter[str] = Counter()
        self.requests: dict[str, list[Mapping[str, Any]]] = {}
        self.refuse: Counter[str] = Counter(refuse or {})
        self._templates = {
            hashlib.sha256(sheet_family(role).template(role)).hexdigest(): name
            for name, role in UI_SHEET_ROLES.items()
        }

    def __call__(self, call: StandInCall) -> Answer:
        if call.capability in ("image.generate", "image.edit"):
            return self._image(call.request)
        if call.capability == "structured.generate":
            return self._structured(call)
        if call.capability == "music.generate":
            self._note("track", call.request)
            return Answer(files={"audio": bundled_music_path().read_bytes()})
        raise AssertionError(f"unexpected call: {call!r}")

    def _note(self, kind: str, request: Mapping[str, Any]) -> bool:
        """Count the call; true when this one is to be answered wrongly."""

        self.calls[kind] += 1
        self.requests.setdefault(kind, []).append(request)
        if self.refuse[kind] > 0:
            self.refuse[kind] -= 1
            return True
        return False

    def pictures(self, request: Mapping[str, Any]) -> list[str]:
        values = [request.get("image"), *(request.get("references") or [])]
        return [value.digest for value in values if isinstance(value, InputFile)]

    def _paint(self, request: Mapping[str, Any]) -> tuple[str, bytes]:
        size = str(request["size"])
        transparent = request.get("background") == "transparent"
        roles = {self._templates.get(digest) for digest in self.pictures(request)} - {None}
        if roles:
            return "ui", ui_sheet(str(roles.pop()))
        width, height = _size(size)
        if width == height:
            return "cutout", cutout(size)
        if width > height:
            return "backdrop", opaque(size)
        return "face", cutout(size) if transparent else keyed(size)

    def _image(self, request: Mapping[str, Any]) -> Answer:
        kind, data = self._paint(request)
        if self._note(kind, request):
            if request.get("background") != "transparent" or kind not in ("cutout", "face"):
                raise AssertionError(f"a {kind} cannot be answered wrongly past FX's checks")
            data = haze(str(request["size"]))
        return Answer(files={"image": data})

    def _structured(self, call: StandInCall) -> Answer:
        request = call.request
        fields = set(schema_of(call).get("properties") or {})
        prompt = str(request["prompt"])
        answer: dict[str, Any]
        if "style_mode" in fields:
            self._note("style", request)
            answer = {
                "schema_version": 1,
                "kind": "image_style_selection_v1",
                "style_mode": STYLE_MODE,
            }
        elif "narrations" in fields:
            wrong = self._note("narration", request)
            ids = _NARRATION_ID.findall(prompt)[: -1 if wrong else None]
            answer = {
                "narrations": [{"id": found, "text": f"A line for {found}."} for found in ids]
            }
        elif "shared_locks" in fields:
            self._note("plan", request)
            answer = {
                "shared_locks": {
                    key: f"Stand-in {key} lock."
                    for key in ("identity", "wardrobe", "pose", "lighting", "style")
                }
            }
        elif "verdict" in fields:
            self._note("review", request)
            answer = {
                "verdict": "accept",
                "confidence": 1.0,
                "checks": {},
                "issues": [],
                "evidence": "deterministic stand-in",
            }
        else:
            raise AssertionError(f"unexpected structured schema: {sorted(fields)}")
        return Answer.json(answer)


def run(
    project: Path, builder: str, package: str, stand_ins: StandIns, name: str = "run"
) -> RunResult:
    return run_fx(
        builder,
        cwd=project,
        arguments={"package": package},
        run_dir=project / name,
        stand_in=stand_ins,
    )
