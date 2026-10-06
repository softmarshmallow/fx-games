"""An FX run folder, read the way FX writes it: its plan, its record and where its files sit.

FX owns the folder (``spec/store.md`` section 8 of the FX engine). This module only reads it:
``plan.json`` (``fx-graph-v1``) and ``events.jsonl`` (``fx-run-events-v1``), the placed names
under ``files/``, and the store a file's bytes are kept in. The names are FX's, reimplemented
here so a view never has to start the engine; a test checks them against
``python -m grida.fx inspect --json``. Nothing here writes into a run folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import yaml

FX_GRAPH_KIND = "fx-graph-v1"
PLAN_FILE = "plan.json"
EVENTS_FILE = "events.jsonl"
PROJECT_FILE = "fx.yaml"
#: The store of a project whose ``fx.yaml`` sets no ``cache``.
DEFAULT_CACHE = ".fx/cache"
#: The store a stand-in run keeps its files in, under the project's store.
STAND_IN_STORE = "stand-in"
#: The most bytes one name may hold on the file systems FX writes to.
NAME_BYTES = 255

#: The suffix a run folder gives a file of each kind: the first suffix FX's kind table lists.
SUFFIXES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "json": ".json",
    "annotations": ".json",
    "text/yaml": ".yaml",
    "text/toml": ".toml",
    "text/html": ".html",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
    "model/gltf-binary": ".glb",
    "model/gltf+json": ".gltf",
    "model/fbx": ".fbx",
    "file/zip": ".zip",
}

_FINISHED_RUN = frozenset({"run_finished", "run_cancelled"})


class RunFolderError(ValueError):
    """A folder that is not an FX run: no ``plan.json`` of kind ``fx-graph-v1``."""


def _plan_document(run_dir: Path) -> dict[str, Any] | None:
    try:
        document = json.loads((run_dir / PLAN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return document if isinstance(document, dict) else None


def is_fx_run(run_dir: Path) -> bool:
    document = _plan_document(run_dir)
    return document is not None and document.get("kind") == FX_GRAPH_KIND


def read_plan(run_dir: Path) -> dict[str, Any]:
    document = _plan_document(run_dir)
    if document is None or document.get("kind") != FX_GRAPH_KIND:
        raise RunFolderError(f"{run_dir} is not an FX run")
    return document


def is_stand_in(run_dir: Path) -> bool:
    """Whether the folder holds a stand-in run: its plan says ``"stand_in": true``."""

    return read_plan(run_dir).get("stand_in") is True


def read_events(run_dir: Path) -> list[dict[str, Any]]:
    """Every whole event in the record, in order.

    A last line without its line feed is one an invocation began and never finished, and is
    left out; reading stops at the first line that is not JSON.
    """

    path = run_dir / EVENTS_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    lines = text.split("\n")
    events: list[dict[str, Any]] = []
    for line in lines[:-1]:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            break
        if isinstance(event, dict):
            events.append(event)
    return events


def ending(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The last ``run_finished`` or ``run_cancelled``, whichever came last."""

    return next((event for event in reversed(events) if event.get("event") in _FINISHED_RUN), None)


def route_id(value: Any) -> str | None:
    """A route as its id: the plan records ``{route, fingerprint}``, the record the id."""

    if isinstance(value, Mapping):
        value = value.get("route")
    return value if isinstance(value, str) and value else None


# ---------------------------------------------------------------- placed names


def suffix_of_kind(kind: str) -> str:
    return SUFFIXES.get(kind, "")


def safe_name(text: str) -> str:
    """A step path as one folder name: anything but a letter or a digit (Unicode L or N), ``.``,
    ``_`` and ``-`` becomes ``_``; ``_`` is trimmed; empty is ``step``."""

    out = "".join(
        char if unicodedata.category(char)[0] in "LN" or char in "._-" else "_" for char in text
    )
    return out.strip("_") or "step"


def keyed_path(key: str) -> str:
    """A key as a relative path: its ``/`` make folders, and no segment leaves them."""

    return "/".join(
        "_" if segment in {"", ".", ".."} else safe_name(segment) for segment in key.split("/")
    )


def named(label: str, kind: str) -> str:
    """``label`` with its kind's suffix, unless it already ends with it."""

    ending_ = suffix_of_kind(kind)
    return label if not ending_ or label.endswith(ending_) else f"{label}{ending_}"


def takes_of_id(instance_id: str) -> tuple[int, ...]:
    """The takes an instance id carries (``draw#1.2``); ``(1,)`` when it carries none."""

    _, mark, tail = instance_id.rpartition("#")
    if not mark:
        return (1,)
    takes: list[int] = []
    for take in tail.split("."):
        if not take.isascii() or not take.isdigit():
            return (1,)
        takes.append(int(take))
    return tuple(takes)


def step_folder(path: str, takes: tuple[int, ...]) -> str:
    """A step's folder under ``files/``: its path as one name, with ``#<takes>`` unless the
    takes are ``(1,)``, so two takes never share a folder."""

    step = safe_name(path)
    return step if takes == (1,) else f"{step}#{'.'.join(str(take) for take in takes)}"


def cap_segment(segment: str, suffix: str) -> str:
    """One name cut to 255 bytes: its first whole characters, ``~`` and 16 hex characters of
    the whole name's SHA-256, then ``suffix`` when it ended with it."""

    data = segment.encode("utf-8")
    if len(data) <= NAME_BYTES:
        return segment
    kept = suffix if suffix and segment.endswith(suffix) else ""
    stem = data[: len(data) - len(kept.encode("utf-8"))]
    room = NAME_BYTES - 1 - 16 - len(kept.encode("utf-8"))
    cut = stem[:room].decode("utf-8", errors="ignore")
    return f"{cut}~{hashlib.sha256(data).hexdigest()[:16]}{kept}"


def capped(relative: str, kind: str) -> str:
    """A relative path with every segment cut to fit one name; the last keeps its suffix."""

    suffix = suffix_of_kind(kind)
    segments = relative.split("/")
    last = len(segments) - 1
    return "/".join(
        cap_segment(segment, suffix if index == last else "")
        for index, segment in enumerate(segments)
    )


def _label(key: Any, index: int) -> str:
    return keyed_path(key) if isinstance(key, str) and key else str(index)


def placed_path(
    instance_id: str, path: str, port: str, file: Mapping[str, Any], index: int, count: int
) -> str:
    """Where a run folder keeps one output file of an instance: ``files/<step>/<port><suffix>``
    for a port's only file, else ``files/<step>/<port>/<key or index><suffix>``."""

    kind = str(file["kind"])
    label = port if count == 1 else f"{port}/{_label(file.get('key'), index)}"
    folder = step_folder(path, takes_of_id(instance_id))
    return capped(f"files/{folder}/{named(label, kind)}", kind)


def output_path(name: str, file: Mapping[str, Any], index: int, single: bool) -> str:
    """Where a run folder keeps one file of a declared output: ``outputs/<name><suffix>`` for
    an output that is one file, else ``outputs/<name>/<key or index><suffix>``."""

    kind = str(file["kind"])
    label = name if single else f"{name}/{_label(file.get('key'), index)}"
    return capped(f"outputs/{named(label, kind)}", kind)


def files_of(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Every file an encoded value holds, in order, each with its key: its own, else the key
    of the collection item it is."""

    def collect(item: Any, key: str | None) -> Iterator[dict[str, Any]]:
        if not isinstance(item, Mapping):
            return
        if isinstance(item.get("file"), Mapping):
            file = dict(item["file"])
            if not file.get("key") and key:
                file["key"] = key
            yield file
        elif isinstance(item.get("collection"), list):
            for pair in item["collection"]:
                yield from collect(pair[1], str(pair[0]))
        elif isinstance(item.get("list"), list):
            for element in item["list"]:
                yield from collect(element, None)

    return list(collect(value, None))


def placed_files(run_dir: Path, events: list[dict[str, Any]]) -> dict[str, list[Path]]:
    """Every file the record says the folder holds, by digest: step files and outputs."""

    found: dict[str, list[Path]] = {}
    for event in events:
        name = event.get("event")
        outputs = event.get("outputs")
        if not isinstance(outputs, Mapping):
            continue
        if name == "node_finished":
            identifier, path = str(event.get("id", "")), str(event.get("path", ""))
            for port, value in outputs.items():
                files = files_of(value)
                for index, file in enumerate(files):
                    relative = placed_path(identifier, path, port, file, index, len(files))
                    found.setdefault(str(file["digest"]), []).append(run_dir / relative)
        elif name == "run_finished":
            for output, value in outputs.items():
                files = files_of(value)
                single = isinstance(value, Mapping) and "file" in value
                for index, file in enumerate(files):
                    relative = output_path(output, file, index, single)
                    found.setdefault(str(file["digest"]), []).append(run_dir / relative)
    return found


# ---------------------------------------------------------------- the project and its store


def project_file(start: Path) -> Path | None:
    """The nearest ``fx.yaml`` at or above ``start``."""

    here = start.resolve()
    if here.is_file():
        here = here.parent
    for folder in (here, *here.parents):
        candidate = folder / PROJECT_FILE
        if candidate.is_file():
            return candidate
    return None


def setting(file: Path | None, name: str, default: str) -> str:
    """A top-level text setting of a project file, or ``default``."""

    if file is None:
        return default
    try:
        document = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return default
    value = document.get(name) if isinstance(document, dict) else None
    return value if isinstance(value, str) and value else default


def store_of(run_dir: Path, plan: Mapping[str, Any]) -> Path:
    """The store a run's files are kept in: the ``cache`` of the nearest ``fx.yaml`` at or
    above the run folder, and its stand-in store for a stand-in run."""

    project = project_file(run_dir)
    base = project.parent if project is not None else run_dir.resolve()
    store = base / setting(project, "cache", DEFAULT_CACHE)
    return store / STAND_IN_STORE if plan.get("stand_in") is True else store


_DIGESTS: dict[tuple[str, int, int], str] = {}


def _digest_of(path: Path) -> str | None:
    try:
        status = path.stat()
    except OSError:
        return None
    marker = (str(path), status.st_size, status.st_mtime_ns)
    known = _DIGESTS.get(marker)
    if known is None:
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1 << 20), b""):
                    hasher.update(chunk)
        except OSError:
            return None
        known = _DIGESTS[marker] = hasher.hexdigest()
    return known


def find_file(
    run_dir: Path,
    digest: str,
    plan: Mapping[str, Any],
    *,
    placed: Mapping[str, list[Path]] | None = None,
) -> Path:
    """A file the run read or made, by digest: where the folder placed it, else in its store.
    The bytes are checked against the digest; ``FileNotFoundError`` when none match.
    ``placed`` is :func:`placed_files` of the run, when the caller has it already."""

    if placed is None:
        placed = placed_files(run_dir, read_events(run_dir))
    stored = store_of(run_dir, plan) / "files" / digest[:2] / digest
    for path in [*placed.get(digest, []), stored]:
        if path.is_file() and not path.is_symlink() and _digest_of(path) == digest:
            return path
    raise FileNotFoundError(f"{run_dir.name} read {digest[:12]}, whose bytes are gone")


def relative_within(root: Path, path: Path) -> bool:
    """Whether ``path`` resolves inside ``root`` without passing through a symbolic link."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        if part in {"", ".", ".."}:
            return False
        current = current / part
        if current.is_symlink():
            return False
    return os.path.realpath(path).startswith(os.path.realpath(root) + os.sep)


__all__ = [
    "DEFAULT_CACHE",
    "EVENTS_FILE",
    "FX_GRAPH_KIND",
    "PLAN_FILE",
    "PROJECT_FILE",
    "STAND_IN_STORE",
    "SUFFIXES",
    "RunFolderError",
    "cap_segment",
    "capped",
    "ending",
    "files_of",
    "find_file",
    "is_fx_run",
    "is_stand_in",
    "keyed_path",
    "named",
    "output_path",
    "placed_files",
    "placed_path",
    "project_file",
    "read_events",
    "read_plan",
    "relative_within",
    "route_id",
    "safe_name",
    "setting",
    "step_folder",
    "store_of",
    "suffix_of_kind",
    "takes_of_id",
]
