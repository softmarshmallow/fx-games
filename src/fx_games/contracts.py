"""Pydantic contract bases and the in-memory artifact value."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

#: Lowercase hexadecimal SHA-256, the only digest form persisted anywhere.
SHA256_PATTERN = r"^[a-f0-9]{64}$"


class ContractModel(BaseModel):
    """Application-boundary base that accepts Python names and aliases."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PersistedContractModel(ContractModel):
    """Strict base for values written to disk or returned as artifact contracts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


@dataclass(frozen=True, slots=True)
class BinaryArtifact:
    """In-memory bytes and their declared media type.

    Construction performs no media validation or persistence. The producing
    service or caller must validate the payload before accepting it as an artifact.
    """

    data: bytes
    media_type: str
