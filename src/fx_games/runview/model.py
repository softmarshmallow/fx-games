"""The run view: one derived, read-only document the examples store reads a run from.

FX Games projects it from an FX run folder's plan and record (:mod:`fx_games.runview.project`).
It is derived state, which is why it carries a hard-drop versioning policy: a consumer refuses
an unknown ``kind`` or ``schema_version`` and asks for the view again instead of migrating. The
``gaps`` list is the projection's admission of everything it could not represent faithfully
from the run's own documents.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from fx_games.contracts import SHA256_PATTERN, PersistedContractModel

#: The run view's kind and version.
RUN_VIEW_KIND = "fx-games-run-view-v1"
RUN_VIEW_SCHEMA_VERSION = 4

NODE_ID_PATTERN = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"
PORT_ID_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
PAYLOAD_KIND_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

NodeState = Literal["pending", "running", "succeeded", "failed", "skipped"]

#: What a run's own records say became of it. Deliberately not "running": a
#: finished run says so in its trace, and a run whose records simply stop cannot
#: tell you from disk whether it is still going or was abandoned. That is a
#: liveness question, answered by ``trace_modified_at`` against the wall clock,
#: and it belongs to whoever is reading — not to a document written once.
RunState = Literal["planned", "unfinished", "canceled", "succeeded", "failed"]
ArtifactDisplay = str

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".ogv": "video/ogg",
    ".webm": "video/webm",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
    ".obj": "model/obj",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


class RetryOwner(StrEnum):
    NONE = "none"
    COMPONENT = "component"


class CacheDisposition(StrEnum):
    HIT = "hit"
    MISS = "miss"
    BYPASS = "bypass"


class Resource(PersistedContractModel):
    resource_id: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    max_in_flight: int | None = Field(default=None, ge=1, le=1_024)
    requests_per_minute: int | None = Field(default=None, ge=1)
    rate_limit_owner: Literal["scheduler", "provider_adapter", "none"]

    @model_validator(mode="after")
    def validate_rate_owner(self) -> Resource:
        if self.requests_per_minute is None and self.rate_limit_owner != "none":
            raise ValueError("rate-limited resources require requests_per_minute")
        if self.requests_per_minute is not None and self.rate_limit_owner == "none":
            raise ValueError("requests_per_minute requires a rate-limit owner")
        return self


class Port(PersistedContractModel):
    """One declared output: an artifact address plus the typed record it carries.

    ``kind`` names the payload contract (an application-owned persisted vocabulary such as
    ``map-terrain-v1``); ``sidecar_ref`` keeps the provenance sidecar visibly paired with its
    artifact instead of appearing as a second undifferentiated output.
    """

    port_id: str = Field(pattern=PORT_ID_PATTERN, max_length=64)
    artifact_ref: str = Field(min_length=1, max_length=512)
    kind: str = Field(pattern=PAYLOAD_KIND_PATTERN, max_length=96)
    sidecar_ref: str | None = Field(default=None, max_length=512)


class PortRef(PersistedContractModel):
    """An edge endpoint: one named port on one node."""

    node_id: str = Field(pattern=NODE_ID_PATTERN, max_length=192)
    port_id: str = Field(pattern=PORT_ID_PATTERN, max_length=64)


class AuthoredInput(PersistedContractModel):
    """One input a node consumes that no upstream node produced.

    An authored input comes from the package the run was asked to build — a reference image, a
    template, a document the author put there. It carries the digest that binds it, so the plan
    states which exact bytes the node will be handed instead of leaving them implicit in an
    opaque cache key.
    """

    label: str = Field(pattern=NODE_ID_PATTERN, max_length=96)
    ref: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=SHA256_PATTERN)


class NodeCard(PersistedContractModel):
    """A node's definition: what it is told, statically.

    ``prompt`` is the instruction text as known at plan time; ``template_ref`` names a packaged
    template resource when composition is runtime-bound; ``reference_inputs`` point at the
    derived inputs (upstream ports) the node consumes at run time; ``authored_inputs`` name the
    package members it is handed that nothing upstream produced.
    """

    prompt: str | None = Field(default=None, min_length=1, max_length=20_000)
    template_ref: str | None = Field(default=None, max_length=192)
    schema_name: str | None = Field(default=None, max_length=96)
    reference_inputs: tuple[PortRef, ...] = ()
    authored_inputs: tuple[AuthoredInput, ...] = ()


#: A plan node declared a ``type_id`` the exporter's registry does not carry, so
#: its title could not be joined.
class RunViewGap(PersistedContractModel):
    gap_id: str = Field(min_length=1, max_length=96)
    detail: str = Field(min_length=1, max_length=512)


class RunViewArtifact(PersistedContractModel):
    artifact_ref: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    bytes: int = Field(ge=0)
    media_type: str
    present: bool
    display: ArtifactDisplay
    # Historical view payload, interpreted only by the consuming application.
    motion: dict[str, JsonValue] | None = None
    # Hints are opaque JSON to the projection; consumers own each kind.
    preview: dict[str, JsonValue] | None = None


class RunViewNode(PersistedContractModel):
    node_id: str
    type_id: str
    #: Joined from the exporter's type registry; absent when the type is
    #: unregistered (recorded as a gap) so a reader falls back generically.
    title: str | None = None
    domain: str
    description: str
    params: dict[str, str] = Field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    barrier_only: tuple[str, ...] = ()
    operation: str
    resource_id: str
    provider: str | None = None
    model: str | None = None
    retry_owner: RetryOwner
    max_attempts: int = Field(ge=1, le=6)
    input_sha256: tuple[str, ...] = ()
    cache_key: str = Field(pattern=SHA256_PATTERN)
    ports: tuple[Port, ...] = ()
    card: NodeCard | None = None
    template_id: str | None = None
    estimated_duration_seconds: float = Field(ge=0.0)
    estimated_cost_low_usd: float = Field(ge=0.0)
    estimated_cost_high_usd: float = Field(ge=0.0)
    state: NodeState
    started_offset_ms: int | None = Field(default=None, ge=0)
    ended_offset_ms: int | None = Field(default=None, ge=0)
    queue_ms: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    cache: CacheDisposition | None = None
    attempts: int | None = Field(default=None, ge=0, le=6)
    provider_operations: int | None = Field(default=None, ge=0)
    known_cost_usd: float | None = Field(default=None, ge=0.0)
    error: str | None = None
    blocked_by: tuple[str, ...] = ()
    artifacts: tuple[RunViewArtifact, ...] = ()


class RunView(PersistedContractModel):
    """One derived, hard-drop-versioned document the examples store reads a run from."""

    schema_version: int = Field(ge=1)
    kind: str = Field(min_length=1, max_length=96)
    graph_sha256: str = Field(pattern=SHA256_PATTERN)
    topology_sha256: str = Field(pattern=SHA256_PATTERN)
    invocation_id: str | None = None
    run_state: RunState
    #: When this run's trace was last appended to, in UTC. Absent when the run
    #: has no trace at all. A reader compares it against now to tell an
    #: ``unfinished`` run that is still going from one that was abandoned.
    trace_modified_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    known_cost_usd: float | None = Field(default=None, ge=0.0)
    state_counts: dict[str, int]
    resources: tuple[Resource, ...]
    nodes: tuple[RunViewNode, ...]
    gaps: tuple[RunViewGap, ...] = ()


def artifact_media_type(artifact_ref: str) -> str:
    suffix = Path(artifact_ref).suffix.lower()
    return _MEDIA_TYPES.get(suffix, "application/octet-stream")


__all__ = [
    "NODE_ID_PATTERN",
    "PAYLOAD_KIND_PATTERN",
    "PORT_ID_PATTERN",
    "RUN_VIEW_KIND",
    "RUN_VIEW_SCHEMA_VERSION",
    "ArtifactDisplay",
    "AuthoredInput",
    "CacheDisposition",
    "NodeCard",
    "NodeState",
    "Port",
    "PortRef",
    "Resource",
    "RetryOwner",
    "RunState",
    "RunView",
    "RunViewArtifact",
    "RunViewGap",
    "RunViewNode",
    "artifact_media_type",
]
