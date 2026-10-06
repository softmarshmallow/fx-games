"""The designer's judge and feedback over canned compositions. Nothing here touches a network."""

from __future__ import annotations

from demo_game_tools.kits.sideview_map_design import (
    MAX_QUOTED_PROBLEMS,
    expand_design,
    rejection_feedback,
)

from ._profiles import GROUND_FOOTED_PROFILE

_SOUND_SENTENCE: dict[str, object] = {
    "design_notes": "a breather, a climb, a dip, and a jump chain",
    "start_height_tiles": 3,
    "chunks": [
        {"kind": "run", "len": 10},
        {"kind": "stairs", "steps": 2, "step_h": 1, "tread": 4, "dir": "up"},
        {"kind": "perch", "platform_width": 6, "climb_rise": 4, "variant": "root_ladder"},
        {"kind": "hollow", "width": 8, "depth": 2},
        {"kind": "perch", "platform_width": 5, "climb_rise": 4, "variant": "rope_climb"},
        {
            "kind": "hop_chain",
            "count": 3,
            "jump_rise": 1,
            "gap": 4,
            "platform_width": 4,
            "dir": "up",
        },
        {"kind": "perch", "platform_width": 7, "climb_rise": 4, "variant": "shrine_rope_ladder"},
        {"kind": "run", "len": 20},
    ],
}

#: More faults than the feedback budget quotes: eight unknown words, then a map with no
#: climbables at all. Nine problems against a budget of six.
_MANY_PROBLEM_SENTENCE: dict[str, object] = {
    "design_notes": "eight words this game does not have",
    "start_height_tiles": 3,
    "chunks": [
        *({"kind": f"spiral_{turn}", "turns": turn} for turn in range(1, 9)),
        {"kind": "run", "len": 40},
    ],
}

#: Schema-clean and expandable, but the floor it lays is deeper than this game can carry. The
#: complaint names a column, which is what the chunk translator re-anchors.
_TOO_DEEP_SENTENCE: dict[str, object] = {
    "design_notes": "a floor deeper than this game can carry",
    "start_height_tiles": 10,
    "chunks": [
        {"kind": "run", "len": 10},
        {"kind": "run", "len": 30},
        {"kind": "run", "len": 40},
    ],
}


def _problems(sentence: dict[str, object]) -> list[str]:
    return expand_design(sentence, GROUND_FOOTED_PROFILE, GROUND_FOOTED_PROFILE.geometry.columns)[1]


def test_a_sound_sentence_expands_with_no_problems() -> None:
    assert _problems(_SOUND_SENTENCE) == []


def test_the_feedback_quotes_no_more_problems_than_its_budget_allows() -> None:
    """Past the budget the feedback stops reading as a fix list, so the surplus is dropped."""

    problems = _problems(_MANY_PROBLEM_SENTENCE)
    feedback = rejection_feedback(problems)

    assert len(problems) > MAX_QUOTED_PROBLEMS
    assert "rejected by the game's own validator" in feedback
    for problem in problems[:MAX_QUOTED_PROBLEMS]:
        assert f"  - {problem}" in feedback
    surplus = problems[MAX_QUOTED_PROBLEMS]
    assert surplus == "chunk #7 (spiral_7) is not a word in this game's grammar"
    assert surplus not in feedback
    assert feedback.count("  - ") == MAX_QUOTED_PROBLEMS


def test_the_feedback_hands_back_a_column_complaint_re_anchored_on_its_own_chunk() -> None:
    """The translation is what the composer is actually shown.

    ``translate`` is exercised in isolation elsewhere. Here the whole path runs -- expand, check,
    translate, quote -- so the chunk suffix has to survive into the feedback verbatim, in the
    vocabulary the composer itself wrote rather than the validator's grid coordinates.
    """

    problems = _problems(_TOO_DEEP_SENTENCE)

    assert problems[0] == (
        "column 0 floor is 10 tiles, outside the profile's 1..8 [inside chunk #1: run(len=10)]"
    )
    assert f"  - {problems[0]}" in rejection_feedback(problems)
