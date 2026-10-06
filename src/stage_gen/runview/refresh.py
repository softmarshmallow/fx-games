"""The run views the viewer reads, kept fresh in the user cache while it serves them.

Each FX run under the given roots has its run view (``execution-view.json``), its view
contexts (``view-contexts.json``) and the templates and files those name (``views/``) written
into the user cache, under a key made from the run's real path, and written again whenever the
run's plan or record changes. Nothing is ever written into a run.
"""

from __future__ import annotations

import os
import shutil
import threading
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Literal, TextIO

from stage_gen.fs import atomic_write_bytes, atomic_write_json
from stage_gen.runview.contexts import view_contexts
from stage_gen.runview.folder import EVENTS_FILE, PLAN_FILE, read_plan
from stage_gen.runview.project import project_run

VIEW_FILE = "execution-view.json"
VIEW_CONTEXTS_FILE = "view-contexts.json"
VIEW_CONTEXTS_KIND = "stage-gen-view-contexts-v1"
VIEW_KEY_LENGTH = 16
#: How many folders below a root a run may sit (``out/runs/<workflow>/<run>`` is three).
SEARCH_DEPTH = 4
REFRESH_SECONDS = 3.0


def cache_home(env: Mapping[str, str] = os.environ) -> Path:
    """``$XDG_CACHE_HOME/stage-gen`` when that is an absolute path, else ``~/.cache/stage-gen``."""

    configured = env.get("XDG_CACHE_HOME", "")
    base = Path(configured) if configured and Path(configured).is_absolute() else None
    return (base or Path.home() / ".cache") / "stage-gen"


def view_key(run_dir: Path) -> str:
    """The cache folder name of a run: its real path, hashed."""

    return sha256(str(run_dir.resolve()).encode()).hexdigest()[:VIEW_KEY_LENGTH]


def _file_names(directory: Path) -> set[str]:
    try:
        with os.scandir(directory) as entries:
            return {entry.name for entry in entries if entry.is_file()}
    except OSError:
        return set()


def is_run(directory: Path) -> Literal["run", "foreign"] | None:
    """``run`` for an FX run, which keeps its plan beside its record from the moment it
    starts; ``foreign`` for a plan and record of another kind; None for any other folder."""

    names = _file_names(directory)
    if PLAN_FILE not in names or EVENTS_FILE not in names:
        return None
    try:
        read_plan(directory)
    except ValueError:
        return "foreign"
    return "run"


def discover(roots: Iterable[Path], *, depth: int = SEARCH_DEPTH) -> list[Path]:
    """Every FX run under each root, at most ``depth`` folders down, in root then path order.
    A run's own folders are not searched, nor a foreign run's; hidden folders,
    ``node_modules`` and symlinked folders (which could lead outside the root) are skipped."""

    found: list[Path] = []
    for given in roots:
        root = given.resolve()
        runs: list[Path] = []
        pending: list[tuple[Path, int]] = [(root, 0)]
        while pending:
            directory, level = pending.pop()
            if level:
                kind = is_run(directory)
                if kind == "run":
                    runs.append(directory)
                if kind is not None:
                    continue
            if level == depth:
                continue
            try:
                with os.scandir(directory) as entries:
                    children = [
                        Path(entry.path)
                        for entry in entries
                        if not entry.name.startswith(".")
                        and entry.name != "node_modules"
                        and entry.is_dir(follow_symlinks=False)
                    ]
            except OSError:
                continue
            pending.extend((child, level + 1) for child in children)
        found.extend(sorted(runs, key=lambda run: run.relative_to(root).as_posix()))
    return found


def _place(source: Path, target: Path) -> None:
    """Put ``source``'s bytes at ``target``: a hard link, or a copy where linking fails, made
    under a temporary name and renamed over it; never a symbolic link. A name the cache keeps
    is a digest, so one that exists already holds these bytes and is left alone."""

    if target.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        try:
            os.link(source, temporary)
        except OSError:
            shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def write_view(run_dir: Path, out_dir: Path) -> None:
    """Write the run's view into ``out_dir``: first the templates and files its views show,
    then its view contexts, then the run view itself."""

    views = view_contexts(run_dir)
    for ref, source in views.templates.items():
        target = out_dir / ref
        if not target.is_file():
            atomic_write_bytes(target, source.read_bytes(), mode=0o644)
    for ref, source in views.files.items():
        _place(source, out_dir / ref)
    atomic_write_json(
        out_dir / VIEW_CONTEXTS_FILE,
        {
            "kind": VIEW_CONTEXTS_KIND,
            "view_origins": list(read_plan(run_dir).get("view_origins", [])),
            "views": views.contexts,
        },
    )
    atomic_write_json(out_dir / VIEW_FILE, project_run(run_dir).model_dump(mode="json"))


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def source_mtime(run_dir: Path) -> float | None:
    """When the run's plan or record last changed; None when it has neither."""

    stamps = [_mtime(run_dir / name) for name in (PLAN_FILE, EVENTS_FILE)]
    present = [stamp for stamp in stamps if stamp is not None]
    return max(present) if present else None


@dataclass(slots=True)
class ViewRefresher:
    """Writes the views of runs whose plan or record changed, once per change.

    A run whose view cannot be written is tried again only after it changes, and the reason
    is kept in ``failures``.
    """

    roots: tuple[Path, ...]
    cache_dir: Path
    attempted: dict[Path, float] = field(default_factory=dict)
    failures: dict[Path, str] = field(default_factory=dict)

    def refresh(self) -> list[Path]:
        written: list[Path] = []
        for run_dir in discover(self.roots):
            source = source_mtime(run_dir)
            if source is None or self.attempted.get(run_dir) == source:
                continue
            out_dir = self.cache_dir / view_key(run_dir)
            view = _mtime(out_dir / VIEW_FILE)
            self.attempted[run_dir] = source
            if view is not None and view >= source:
                continue
            try:
                write_view(run_dir, out_dir)
            except Exception as error:  # a broken run must not stop the others
                self.failures[run_dir] = f"{type(error).__name__}: {error}"
                continue
            written.append(out_dir / VIEW_FILE)
            self.failures.pop(run_dir, None)
        return written


def keep_fresh(refresher: ViewRefresher, stop: threading.Event, errors: TextIO) -> None:
    """Refresh until ``stop`` is set, reporting each run whose view could not be written once."""

    reported: set[Path] = set()
    while True:
        try:
            refresher.refresh()
        except OSError as error:
            errors.write(f"view: could not refresh the run views: {error}\n")
        for run_dir, failure in refresher.failures.items():
            if run_dir not in reported:
                reported.add(run_dir)
                errors.write(f"view: no view for {run_dir}: {failure}\n")
        if stop.wait(REFRESH_SECONDS):
            return


__all__ = [
    "REFRESH_SECONDS",
    "SEARCH_DEPTH",
    "VIEW_CONTEXTS_FILE",
    "VIEW_CONTEXTS_KIND",
    "VIEW_FILE",
    "ViewRefresher",
    "cache_home",
    "discover",
    "is_run",
    "keep_fresh",
    "source_mtime",
    "view_key",
    "write_view",
]
