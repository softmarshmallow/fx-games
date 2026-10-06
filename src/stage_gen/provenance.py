"""Provenance-v2 sidecar contracts and their atomic artifact-pair writer."""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import os
import re
import socket
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import SplitResult, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator

from stage_gen.canonical import content_sha256
from stage_gen.contracts import SHA256_PATTERN, BinaryArtifact, PersistedContractModel
from stage_gen.fs import (
    FileOperations,
    LocalFileOperations,
    redact_secrets,
    sanitize_for_persistence,
)

RightsStatus = Literal["unreviewed", "restricted", "redistribution-approved"]
InputSource = Literal["content", "reference"]
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+")
_DIGEST_REFERENCE = re.compile(r"^sha256:[a-f0-9]{64}$")
_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
_NUMERIC_IPV4_HOST = re.compile(r"^[0-9A-Fa-fxX.]+$")


def _non_empty_trimmed(value: str, label: str) -> str:
    if not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty trimmed string")
    return value


def _utc_iso_timestamp(value: str, label: str) -> str:
    if not _UTC_TIMESTAMP.fullmatch(value):
        raise ValueError(f"{label} must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{label} must be a valid UTC ISO-8601 timestamp") from error
    offset = parsed.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{label} must be a UTC ISO-8601 timestamp")
    return value


class SoftwareIdentity(PersistedContractModel):
    name: str
    version: str

    @field_validator("name", "version")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _non_empty_trimmed(value, str(info.field_name))


class InputProvenance(PersistedContractModel):
    ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    source: InputSource
    bytes: int | None = Field(default=None, ge=0)
    media_type: str | None = None

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        return _non_empty_trimmed(value, "input ref")


class ArtifactDigest(PersistedContractModel):
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)
    media_type: str


class ArtifactRights(PersistedContractModel):
    """Explicit rights decision; the model never infers approval."""

    status: RightsStatus
    attribution: list[str] = Field(default_factory=list)
    basis: list[str]
    reviewed_at: str | None

    @field_validator("attribution", "basis")
    @classmethod
    def validate_string_list(cls, value: list[str], info: Any) -> list[str]:
        return [_non_empty_trimmed(item, str(info.field_name)) for item in value]

    @field_validator("reviewed_at")
    @classmethod
    def validate_reviewed_at(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return _utc_iso_timestamp(value, "artifact rights reviewed_at")
        except ValueError as error:
            raise ValueError(
                "artifact rights reviewed_at must be a valid UTC ISO-8601 timestamp or null"
            ) from error

    @model_validator(mode="after")
    def validate_status_fields(self) -> ArtifactRights:
        if self.status == "unreviewed":
            if self.reviewed_at is not None:
                raise ValueError("unreviewed artifact rights must have reviewed_at=null")
            return self
        if not self.basis:
            raise ValueError(f"{self.status} artifact rights must record at least one basis")
        if self.reviewed_at is None:
            raise ValueError(f"{self.status} artifact rights must record reviewed_at")
        return self


class ArtifactProvenance(PersistedContractModel):
    """Persisted artifact sidecar using the exact current schema version."""

    schema_version: Literal[2]
    provider: str
    model: str
    seed: int | None
    prompt: str
    prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    references: list[str]
    refs: list[str]
    inputs: list[InputProvenance]
    params: dict[str, Any]
    validation: dict[str, Any]
    component: SoftwareIdentity
    tool: SoftwareIdentity
    artifact: ArtifactDigest | None = None
    rights: ArtifactRights | None = None
    ts: str
    attempts: int = Field(ge=1, le=6)
    retries: int = Field(ge=0, le=5)
    response: dict[str, Any] | None = None

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return _utc_iso_timestamp(value, "provenance ts")

    @model_validator(mode="after")
    def validate_attempt_count(self) -> ArtifactProvenance:
        if self.retries != self.attempts - 1:
            raise ValueError("retries must equal attempts - 1")
        if self.references != self.refs:
            raise ValueError("references and refs must contain the same values")
        return self


class ProvenanceInput(PersistedContractModel):
    """Caller input used to construct a sanitized provenance-v2 sidecar."""

    schema_version: Literal[2] = 2
    provider: str
    model: str
    seed: int | None = None
    prompt: str
    refs: list[str] = Field(default_factory=list)
    inputs: list[InputProvenance] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
    component: SoftwareIdentity
    tool: SoftwareIdentity
    timestamp: str | None = None
    attempts: int = Field(ge=1, le=6)
    response: dict[str, Any] | None = None
    rights: ArtifactRights | None = None

    @field_validator("provider", "model", "prompt")
    @classmethod
    def validate_required_text(cls, value: str, info: Any) -> str:
        if not value or not value.strip():
            raise ValueError(f"{info.field_name} must be a non-empty string")
        return value

    @field_validator("timestamp")
    @classmethod
    def validate_optional_timestamp(cls, value: str | None) -> str | None:
        return None if value is None else _utc_iso_timestamp(value, "provenance timestamp")


class AtomicWriteError(OSError):
    """An atomic commit or its rollback failed."""

    def __init__(self, message: str, *, provider_operations: int | None = None) -> None:
        super().__init__(message)
        if provider_operations is None:
            return
        if (
            isinstance(provider_operations, bool)
            or not isinstance(provider_operations, int)
            or provider_operations < 0
        ):
            raise ValueError("provider_operations must be a non-negative integer")
        self.attempts = max(1, provider_operations)
        self.provider_operations = provider_operations


_LOCAL_FILES = LocalFileOperations()


def build_artifact_provenance(
    artifact: BinaryArtifact | None,
    provenance: ProvenanceInput,
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
) -> ArtifactProvenance:
    """Build sanitized provenance-v2 without writing files.

    An artifact requires non-empty bytes, a supported media type, and valid text
    when applicable. Other media validation belongs to the caller. ``None`` omits
    the artifact digest; ``now`` supplies a missing timestamp; ``secrets`` is redacted.
    """

    references = [sanitize_reference(reference) for reference in provenance.refs]
    inputs = [
        InputProvenance(
            ref=sanitize_reference(item.ref),
            sha256=item.sha256,
            source=item.source,
            bytes=item.bytes,
            media_type=item.media_type,
        )
        for item in provenance.inputs
    ]
    rights = _sanitize_rights(provenance.rights, secrets) if provenance.rights is not None else None
    timestamp = provenance.timestamp or (now or datetime.now(UTC)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    digest = None
    if artifact is not None:
        if not artifact.data:
            raise ValueError("artifact bytes must be non-empty")
        media_type = normalize_artifact_media_type(artifact.media_type)
        if media_type.startswith("text/"):
            assert_text_payload(artifact.data, media_type)
        digest = ArtifactDigest(
            sha256=content_sha256(artifact.data), bytes=len(artifact.data), media_type=media_type
        )
    raw: dict[str, Any] = {
        "schema_version": provenance.schema_version,
        "provider": provenance.provider,
        "model": provenance.model,
        "seed": provenance.seed,
        "prompt": provenance.prompt,
        "prompt_sha256": content_sha256(provenance.prompt.encode("utf-8")),
        "references": references,
        "refs": references,
        "inputs": [item.model_dump(mode="json") for item in inputs],
        "params": provenance.params,
        "validation": provenance.validation,
        "component": provenance.component.model_dump(mode="json"),
        "tool": provenance.tool.model_dump(mode="json"),
        "artifact": digest.model_dump(mode="json") if digest is not None else None,
        "rights": rights.model_dump(mode="json") if rights is not None else None,
        "ts": timestamp,
        "attempts": provenance.attempts,
        "retries": provenance.attempts - 1,
        "response": provenance.response,
    }
    sanitized = sanitize_for_persistence(raw, secrets)
    if not isinstance(sanitized, dict):
        raise TypeError("artifact provenance must be an object")
    record = ArtifactProvenance.model_validate(sanitized)
    if record.rights is not None and record.rights.status == "redistribution-approved":
        _assert_portable_references(record.references, record.inputs)
    return record


def serialize_provenance(provenance: ArtifactProvenance) -> bytes:
    """Serialize using persisted aliases while keeping required null seed."""

    payload = provenance.model_dump(mode="json", by_alias=True, exclude_none=False)
    for optional in ("artifact", "rights", "response"):
        if payload[optional] is None:
            payload.pop(optional)
    for item in payload["inputs"]:
        for optional in ("bytes", "media_type"):
            if item[optional] is None:
                item.pop(optional)
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()


def write_artifact_with_provenance(
    artifact_path: str | os.PathLike[str],
    artifact: BinaryArtifact,
    provenance: ProvenanceInput,
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
    operations: FileOperations | None = None,
) -> Path:
    """Write an artifact and adjacent ``.meta.json`` sidecar; return the sidecar path.

    Validate provenance, stage sibling files, then replace destinations. Caught
    commit failures trigger rollback; ``AtomicWriteError`` reports failures and
    backups remain if restoration fails. Replacements are atomic individually,
    not simultaneous. There is no writer coordination or process-crash recovery.
    Callers own path confinement and media validation beyond provenance checks.
    ``operations`` optionally replaces local filesystem operations.
    """

    raw_path = os.fspath(artifact_path)
    if not raw_path or not raw_path.strip():
        raise ValueError("artifact_path must be non-empty")
    path = Path(raw_path)
    sidecar_path = Path(f"{path}.meta.json")
    record = build_artifact_provenance(artifact, provenance, secrets=secrets, now=now)
    sidecar_bytes = serialize_provenance(record)
    files = operations or _LOCAL_FILES
    files.mkdir(path.parent)

    token = uuid.uuid4().hex
    artifact_temp = path.parent / f".{path.name}.{token}.tmp"
    sidecar_temp = sidecar_path.parent / f".{sidecar_path.name}.{token}.tmp"
    artifact_backup = Path(f"{artifact_temp}.backup")
    sidecar_backup = Path(f"{sidecar_temp}.backup")
    artifact_backed_up = False
    sidecar_backed_up = False
    artifact_installed = False
    sidecar_installed = False
    artifact_existed = files.exists(path)
    sidecar_existed = files.exists(sidecar_path)

    try:
        files.write_exclusive(artifact_temp, artifact.data)
        files.write_exclusive(sidecar_temp, sidecar_bytes)
        if artifact_existed:
            files.replace(path, artifact_backup)
            artifact_backed_up = True
        if sidecar_existed:
            files.replace(sidecar_path, sidecar_backup)
            sidecar_backed_up = True
        files.replace(artifact_temp, path)
        artifact_installed = True
        files.replace(sidecar_temp, sidecar_path)
        sidecar_installed = True
        files.sync_directory(path.parent)
    except Exception as error:
        rollback_errors = _rollback_artifact_pair(
            files,
            artifact_path=path,
            sidecar_path=sidecar_path,
            artifact_backup=artifact_backup,
            sidecar_backup=sidecar_backup,
            artifact_existed=artifact_existed,
            sidecar_existed=sidecar_existed,
            artifact_backed_up=artifact_backed_up,
            sidecar_backed_up=sidecar_backed_up,
            artifact_installed=artifact_installed,
            sidecar_installed=sidecar_installed,
        )
        _safe_remove(files, artifact_temp)
        _safe_remove(files, sidecar_temp)
        safe_message = redact_secrets(str(error), secrets)
        if rollback_errors:
            raise AtomicWriteError(
                "artifact pair persistence failed and rollback was incomplete; "
                f"recovery backups were retained: {safe_message}"
            ) from None
        raise AtomicWriteError(safe_message) from None

    _safe_remove(files, artifact_backup)
    _safe_remove(files, sidecar_backup)
    return sidecar_path


async def write_artifact_with_provenance_async(
    artifact_path: str | os.PathLike[str],
    artifact: BinaryArtifact,
    provenance: ProvenanceInput,
    *,
    secrets: Sequence[str] = (),
    now: datetime | None = None,
    operations: FileOperations | None = None,
) -> Path:
    """Write the pair in a worker thread, preserving spend on persistence failure.

    ``AtomicWriteError.provider_operations`` comes from ``provenance.attempts``.
    Cancellation propagates but does not stop work already running in the thread.
    """

    try:
        return await asyncio.to_thread(
            write_artifact_with_provenance,
            artifact_path,
            artifact,
            provenance,
            secrets=secrets,
            now=now,
            operations=operations,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        # The provider result already exists when a caller enters artifact
        # persistence. Preserve that completed spend even when provenance
        # serialization, publication, or rollback fails afterward.
        raise AtomicWriteError(
            redact_secrets(str(error).strip() or type(error).__name__, secrets),
            provider_operations=provenance.attempts,
        ) from None


def normalize_artifact_media_type(value: object) -> str:
    """Reduce a declared media type to the bare form an artifact digest records.

    Parameters (``charset`` included) are dropped rather than refused: they
    describe a transfer, not the bytes on disk, and the sidecar records one
    canonical ``type/subtype``. This validates syntax, not a list of known
    media families; callers own format-specific byte validation.
    """

    if not isinstance(value, str) or not value.strip():
        raise ValueError("artifact media type must be a non-empty string")
    media_type = value.split(";", 1)[0].strip().lower()
    if not _MEDIA_TYPE.fullmatch(media_type):
        raise ValueError(f"invalid media type: {media_type}")
    return media_type


def assert_text_payload(data: bytes, media_type: str) -> None:
    """The deterministic floor for ``text/*`` bytes: decodable, printable, present.

    Unlike the image and audio signature checks in ``stage_gen.media``, this
    floor is enforced by the artifact write itself. It stops at
    the envelope — that the bytes are the UTF-8 text they claim to be — and
    says nothing about Markdown structure, which belongs to the caller.
    """

    media_type = normalize_artifact_media_type(media_type)
    if not media_type.startswith("text/"):
        raise ValueError(f"expected text media type, received {media_type}")
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"text bytes are not valid UTF-8 for {media_type}") from error
    if "\x00" in decoded:
        raise ValueError(f"text bytes contain a NUL for {media_type}")
    if not decoded:
        raise ValueError(f"text bytes are empty for {media_type}")


def sanitize_reference(reference: str) -> str:
    trimmed = reference.strip()
    data_match = re.match(r"^data:([^;,]+)(?:;[^,]*)?,", trimmed, re.IGNORECASE)
    if data_match:
        return f"data:{data_match.group(1).lower()};base64,[REDACTED]"
    try:
        parsed = urlsplit(trimmed)
    except ValueError:
        return trimmed
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return trimmed
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit(SplitResult(parsed.scheme.lower(), netloc, parsed.path, "", ""))


def is_temporary_artifact_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().replace("\\", "/").lower()
    if normalized.startswith(("/tmp/", "/private/tmp/", "/var/folders/")):
        return True
    if "/appdata/local/temp/" in normalized:
        return True
    return any(
        segment in {"tmp", "temp"} or segment.endswith(".tmp") for segment in normalized.split("/")
    )


def is_portable_artifact_reference(value: object) -> bool:
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if _DIGEST_REFERENCE.fullmatch(value):
        return True
    if is_temporary_artifact_reference(value):
        return False
    if value.lower().startswith(("file:", "data:")) or value.startswith("/"):
        return False
    if _WINDOWS_ABSOLUTE.match(value):
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme:
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        return not _is_private_hostname(parsed.hostname)
    if any(character in value for character in (":", "?", "#", "\\")):
        return False
    segments = value.split("/")
    return all(
        segment not in {"", ".", ".."} and not segment.startswith(".") for segment in segments
    )


def _is_private_hostname(hostname: str) -> bool:
    host = hostname.lower().strip("[]")
    if host.endswith("."):
        host = host[:-1]
        if not host or host.endswith("."):
            return True
    if not host or host.startswith(".") or ".." in host:
        return True
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    if "%" in host:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        legacy_address = _parse_legacy_ipv4(host)
        if legacy_address is None:
            return False
        # URL clients accept legacy integer, hexadecimal, octal, and shortened
        # IPv4 spellings. Reject every such non-canonical spelling, even when it
        # happens to resolve to a globally routed address.
        if host != str(legacy_address):
            return True
        return not legacy_address.is_global
    return not address.is_global


def _parse_legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    if not _NUMERIC_IPV4_HOST.fullmatch(host):
        return None
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ipaddress.IPv4Address(packed)


def _assert_portable_references(
    references: Sequence[str], inputs: Sequence[InputProvenance]
) -> None:
    if any(not is_portable_artifact_reference(reference) for reference in references):
        raise ValueError("redistribution-approved provenance contains an unsafe reference")
    if any(not is_portable_artifact_reference(item.ref) for item in inputs):
        raise ValueError("redistribution-approved provenance contains an unsafe input reference")


def _sanitize_rights(rights: ArtifactRights, secrets: Sequence[str]) -> ArtifactRights:
    value = sanitize_for_persistence(rights.model_dump(mode="json"), secrets)
    if not isinstance(value, dict):
        raise TypeError("artifact rights must be an object")
    return ArtifactRights.model_validate(value)


def _safe_remove(files: FileOperations, path: Path) -> None:
    with contextlib.suppress(Exception):
        files.remove(path)


def _rollback_artifact_pair(
    files: FileOperations,
    *,
    artifact_path: Path,
    sidecar_path: Path,
    artifact_backup: Path,
    sidecar_backup: Path,
    artifact_existed: bool,
    sidecar_existed: bool,
    artifact_backed_up: bool,
    sidecar_backed_up: bool,
    artifact_installed: bool,
    sidecar_installed: bool,
) -> list[Exception]:
    """Restore each old output independently, retaining any failed backup."""

    errors: list[Exception] = []
    pairs = (
        (
            artifact_path,
            artifact_backup,
            artifact_existed,
            artifact_backed_up,
            artifact_installed,
        ),
        (
            sidecar_path,
            sidecar_backup,
            sidecar_existed,
            sidecar_backed_up,
            sidecar_installed,
        ),
    )
    for destination, backup, existed, backed_up, installed in pairs:
        backup_exists = backed_up or _safe_exists(files, backup)
        if backup_exists:
            restore_error: Exception | None = None
            # A local rename can fail transiently (for example, interruption or
            # an injected fault). One immediate retry keeps the pair recoverable
            # without introducing AI-style backoff into filesystem recovery.
            for _attempt in range(2):
                try:
                    files.replace(backup, destination)
                except Exception as error:
                    restore_error = error
                else:
                    restore_error = None
                    break
            if restore_error is not None:
                errors.append(restore_error)
                if installed:
                    try:
                        files.remove(destination)
                    except Exception as error:
                        errors.append(error)
            continue
        if not existed and (installed or _safe_exists(files, destination)):
            try:
                files.remove(destination)
            except Exception as error:
                errors.append(error)
    try:
        files.sync_directory(artifact_path.parent)
    except Exception as error:
        errors.append(error)
    return errors


def _safe_exists(files: FileOperations, path: Path) -> bool:
    try:
        return files.exists(path)
    except Exception:
        return False
