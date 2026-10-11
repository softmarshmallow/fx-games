"""Atomic file writes, path confinement, and secret redaction."""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]

_DATA_URL = re.compile(r"data:([^\s;,\"')]+)(?:;[^,\s]*)?;base64,[A-Za-z0-9+/_=-]+", re.IGNORECASE)
_BASE64_FIELD = re.compile(
    r"((?:b64_json|base64|audio_data|image_data)[\"']?\s*[:=]\s*[\"'])"
    r"[A-Za-z0-9+/_=-]+([\"'])",
    re.IGNORECASE,
)
_AUTHORIZATION = re.compile(r"(authorization\s*[:=]\s*)(?:bearer|key)\s+[^\s,\"'}]+", re.IGNORECASE)
_CREDENTIAL_FIELD = re.compile(
    r"([\"']?(?:api[_-]?key|token|secret|credential)[\"']?\s*[:=]\s*[\"'])"
    r"[^\"']+([\"'])",
    re.IGNORECASE,
)
_OPENAI_KEY = re.compile(r"\bsk-(?:or-)?[A-Za-z0-9_-]{8,}\b")
_LONG_BASE64 = re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|authorization|token|secret|credential)", re.I)
_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


class FileOperations(Protocol):
    def mkdir(self, path: Path) -> None: ...

    def exists(self, path: Path) -> bool: ...

    def read_bytes(self, path: Path) -> bytes: ...

    def write_exclusive(self, path: Path, data: bytes, mode: int = 0o600) -> None: ...

    def replace(self, source: Path, destination: Path) -> None: ...

    def remove(self, path: Path) -> None: ...

    def sync_directory(self, path: Path) -> None: ...


class LocalFileOperations:
    """Durable local filesystem operations; injectable for rollback tests."""

    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def exists(self, path: Path) -> bool:
        return os.path.lexists(path)

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_exclusive(self, path: Path, data: bytes, mode: int = 0o600) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(descriptor)

    def replace(self, source: Path, destination: Path) -> None:
        os.replace(source, destination)

    def remove(self, path: Path) -> None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    def sync_directory(self, path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


_LOCAL_FILES = LocalFileOperations()


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    mode: int = 0o600,
    operations: FileOperations | None = None,
) -> Path:
    """Atomically replace one file from an exclusive, fsynced sibling temp."""

    target = Path(path)
    files = operations or _LOCAL_FILES
    files.mkdir(target.parent)
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        files.write_exclusive(temporary, data, mode)
        files.replace(temporary, target)
        files.sync_directory(target.parent)
    except Exception:
        _safe_remove(files, temporary)
        raise
    return target


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    mode: int = 0o600,
    operations: FileOperations | None = None,
) -> Path:
    return atomic_write_bytes(path, text.encode(), mode=mode, operations=operations)


def atomic_write_json(
    path: str | os.PathLike[str],
    value: Mapping[str, Any],
    *,
    mode: int = 0o600,
    operations: FileOperations | None = None,
) -> Path:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    return atomic_write_bytes(path, payload, mode=mode, operations=operations)


def resolve_relative_path_within_root(
    root_path: str | os.PathLike[str],
    requested_path: str,
    label: str,
) -> Path:
    if (
        not requested_path
        or "\x00" in requested_path
        or Path(requested_path).is_absolute()
        or _WINDOWS_ABSOLUTE.match(requested_path)
    ):
        raise ValueError(f"{label} must be relative")
    if "\\" in requested_path:
        raise ValueError(f"{label} contains an invalid path separator")
    segments = requested_path.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise ValueError(f"{label} contains an unsafe path segment")
    root = Path(root_path).absolute()
    output = root.joinpath(*segments).absolute()
    try:
        output.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes its root") from error
    return output


def redact_secrets(value: str, secrets: Sequence[str] = ()) -> str:
    """Remove known and structurally recognizable credentials/media payloads."""

    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _DATA_URL.sub(r"data:\1;base64,[REDACTED]", redacted)
    redacted = _BASE64_FIELD.sub(r"\1[REDACTED]\2", redacted)
    redacted = _AUTHORIZATION.sub(r"\1[REDACTED]", redacted)
    redacted = _CREDENTIAL_FIELD.sub(r"\1[REDACTED]\2", redacted)
    redacted = _OPENAI_KEY.sub("[REDACTED]", redacted)
    return _LONG_BASE64.sub("[REDACTED_BASE64]", redacted)


def sanitize_for_persistence(
    value: object,
    secrets: Sequence[str] = (),
    *,
    key: str = "",
) -> JsonValue:
    """Convert JSON-like input to a redacted, serialization-safe value."""

    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        if _SENSITIVE_KEY.search(key):
            return "[REDACTED]"
        if value.lower().startswith("data:") and "," in value:
            media_type = value[5:].split(",", 1)[0].split(";", 1)[0].lower()
            return f"data:{media_type};base64,[REDACTED]"
        return redact_secrets(value, secrets)
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for child_key, child_value in value.items():
            if not isinstance(child_key, str):
                raise TypeError("provenance object keys must be strings")
            safe_key = redact_secrets(child_key, secrets)
            if safe_key in result:
                raise ValueError("provenance keys collide after secret redaction")
            result[safe_key] = sanitize_for_persistence(child_value, secrets, key=child_key)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | memoryview):
        return [sanitize_for_persistence(item, secrets, key=key) for item in value]
    safe_key = redact_secrets(key, secrets) if key else "root"
    raise TypeError(f"provenance contains unsupported value at {safe_key}")


def _safe_remove(files: FileOperations, path: Path) -> None:
    with contextlib.suppress(Exception):
        files.remove(path)
