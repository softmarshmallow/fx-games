"""The credential names Grida FX reads (FX providers.md §3).

A launcher strips them from a child's environment; nothing in Stage Gen reads their values.
"""

from __future__ import annotations

from typing import Final

PROVIDER_ENV_KEYS: Final[tuple[str, ...]] = (
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
    "TRIPO_API_KEY",
)
