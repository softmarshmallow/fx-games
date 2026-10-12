"""V0 universe ontology vocabulary as closed literal sets.

This is the checked-in taxonomy (docs/spec/universe/taxonomy-v0.md) as the values the
contracts accept. It is medium-free.
"""

from __future__ import annotations

from typing import Final, Literal

EntityClass = Literal["actor", "collective", "place", "thing", "kind", "system", "event", "idea"]

RelationshipFamily = Literal[
    "spatial",
    "social_political",
    "material_functional",
    "taxonomic",
    "causal_historical",
    "symbolic",
]

LineageKind = Literal[
    "explicit_source",
    "visual_observation",
    "conservative_inference",
    "generated_extension",
]

ConceptPurpose = Literal[
    "orient",
    "identify",
    "differentiate",
    "manifest",
    "connect",
    "historicize",
    "humanize",
    "immerse",
    "invite",
]
CONCEPT_PURPOSES: Final[tuple[str, ...]] = (
    "orient",
    "identify",
    "differentiate",
    "manifest",
    "connect",
    "historicize",
    "humanize",
    "immerse",
    "invite",
)

ConceptMode = Literal[
    "environmental_identity_portrait",
    "in_world_action",
    "representative_public_manifestation",
    "establishing_environment",
    "inhabited_environment",
    "hero_object_in_use",
    "representative_specimen_in_context",
    "visible_system_instance",
    "witnessed_event_moment",
    "practiced_or_contested_idea",
]

#: Which concept modes a primary class may use. Facets add context, not modes.
MODES_BY_CLASS: Final[dict[str, tuple[str, ...]]] = {
    "actor": ("environmental_identity_portrait", "in_world_action"),
    "collective": (
        "representative_public_manifestation",
        "in_world_action",
        "inhabited_environment",
    ),
    "place": (
        "establishing_environment",
        "inhabited_environment",
        "environmental_identity_portrait",
    ),
    "thing": ("hero_object_in_use",),
    "kind": ("representative_specimen_in_context",),
    "system": ("visible_system_instance",),
    "event": ("witnessed_event_moment",),
    "idea": ("practiced_or_contested_idea",),
}

# Scene register: the set-level vocabulary the gallery plan must spread across.
Scale = Literal["intimate", "human", "architectural", "landscape"]
TimeOfDay = Literal["dawn", "day", "dusk", "night"]
Weather = Literal["clear", "overcast", "wind", "fog", "rain", "storm", "snow"]
Setting = Literal["interior", "exterior", "threshold"]
Population = Literal["solitary", "few", "crowd"]
Energy = Literal["still", "working", "urgent"]
Vantage = Literal["eye_level", "low_angle", "high_angle", "aerial", "over_shoulder", "from_within"]

WET_WEATHER: Final[frozenset[str]] = frozenset({"rain", "storm"})
DRY_WEATHER: Final[frozenset[str]] = frozenset({"clear", "overcast", "wind"})
