"""The judge-and-feedback half of a composition loop over the chunk grammar.

:func:`expand_design` expands one composition and checks it against the
:class:`PlatformerProfile` it was handed; :func:`rejection_feedback` quotes the validator's
complaints back to the next composition. Both are pure: there is no service and no provider here.
The caller owns the loop (Bellweather's terrain steps compose, judge and re-compose).
"""

from __future__ import annotations

from collections.abc import Mapping

from demo_game_tools.kits.sideview_map_design.capabilities import PlatformerProfile
from demo_game_tools.kits.sideview_map_design.design import DesignedMap, check
from demo_game_tools.kits.sideview_map_design.grammar import expand_chunks, translate

#: How many validator problems are quoted back to the model. More than this and the feedback
#: stops reading as a fix list.
MAX_QUOTED_PROBLEMS = 6


def expand_design(
    value: Mapping[str, object], profile: PlatformerProfile, columns: int
) -> tuple[DesignedMap, list[str]]:
    """Compile one composition and judge it. Pure and deterministic, so it is safe to repeat."""

    designed, chunk_errors, spans = expand_chunks(value, profile, columns)
    return designed, chunk_errors + translate(check(designed, profile), spans)


def rejection_feedback(problems: list[str]) -> str:
    """What the next composition is told about the last one the validator rejected.

    The validator's messages are already written for a reader; they are handed back verbatim
    rather than paraphrased, so the model is corrected by the same authority that judges.
    """

    listed = "\n".join(f"  - {problem}" for problem in problems[:MAX_QUOTED_PROBLEMS])
    return (
        "\n\nYour previous attempt was rejected by the game's own validator:\n"
        f"{listed}\n\nFix exactly these and keep everything that was already good."
    )


__all__ = ["MAX_QUOTED_PROBLEMS", "expand_design", "rejection_feedback"]
