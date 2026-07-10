"""v2 Canon domain models (Pydantic v2) — the single source of truth.

This module is owned by the §3–§6 / §9 implementation task.  Every model uses
``extra="forbid"`` so the generated JSON Schema (see ``schemas.py``) stays the
only contract.

It must NOT import any v1 runtime module (``novel_forge.models``, ``storage``,
``bible_manager``, ``scene_writer``, ``context_builder``, ``cli``, ``engine/*``).

§ cross-reference:
  §3.1 source identity / display order separation
  §3.3 stable ID prefixes (``creation_key``)
  §3.4 typed reference (``EntityRef`` id vs ``CreationRef`` creation_key)
  §4   Canon structure / normalization rules / status transitions
  §4.6 Location / Artifact / Knowledge / Chronology
  §5   Design Intent / ContextScope
  §6   CanonPatch
  §7   CanonEvent / replay

The names ``Canon``, ``CanonPatch``, ``CanonEvent``, ``SourceRef``,
``ContextScope``, ``EntityRef``, ``ReviewEvidence``, ``PATCH_CREATE_KIND``,
``PREFIX_BY_KIND``, ``parse_seq``, ``find_refs``, ``compute_canonical_digest``,
``canonical_json``, ``entity_size`` are imported by sibling modules
(``idgen.py``, ``store.py``, ``slice.py``) and are preserved.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from annotated_types import Ge
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# ---------------------------------------------------------------------------
# Primitive / enum aliases
# ---------------------------------------------------------------------------

SceneId = str  # §3.1 opaque, immutable source identity

EntityKind = Literal[
    "character",
    "collective",
    "location",
    "artifact",
    "knowledge",
    "relationship",
    "foreshadowing",
    "subplot",
    "deadline",
    "world_rule",
    "glossary",
    "series",
]

# Prefix used when minting stable IDs (§3.3).
PREFIX_BY_KIND: dict[str, str] = {
    "character": "char",
    "collective": "grp",
    "location": "loc",
    "artifact": "art",
    "knowledge": "know",
    "relationship": "rel",
    "foreshadowing": "fh",
    "subplot": "sp",
    "glossary": "term",
    "deadline": "deadline",
    "world_rule": "rule",
    "series": "series",
}

# Maps a CanonPatch ops field name to the entity kind it creates.
PATCH_CREATE_KIND: dict[str, str] = {
    "characters": "character",
    "collectives": "collective",
    "locations": "location",
    "artifacts": "artifact",
    "knowledge": "knowledge",
    "relationships": "relationship",
    "foreshadowing": "foreshadowing",
    "subplots": "subplot",
    "glossary": "glossary",
}


# Reverse map: stable-id prefix -> entity kind.
KIND_BY_PREFIX: dict[str, EntityKind] = {
    "char": "character",
    "grp": "collective",
    "loc": "location",
    "art": "artifact",
    "know": "knowledge",
    "rel": "relationship",
    "fh": "foreshadowing",
    "sp": "subplot",
    "term": "glossary",
    "deadline": "deadline",
    "rule": "world_rule",
    "series": "series",
}


def _forbid() -> ConfigDict:
    return ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# §3.4 typed references
# ---------------------------------------------------------------------------


class EntityRef(BaseModel):
    """Typed reference to an *existing* Canon entity (id form)."""

    model_config = ConfigDict(extra="forbid")

    kind: EntityKind
    id: str


class CreationRef(BaseModel):
    """Reference to an entity created within the *same* patch (§3.4)."""

    model_config = ConfigDict(extra="forbid")

    creation_key: str


# §3.4 typed reference: ``{id}`` (existing) or ``{creation_key}`` (new).
ChangeRef = EntityRef | CreationRef


# ---------------------------------------------------------------------------
# §3.1 source identity / §7 provenance
# ---------------------------------------------------------------------------


class EventRef(BaseModel):
    """Immutable provenance reference to the Canon Event that changed an entity."""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    event_digest: str


class SceneLocation(BaseModel):
    """Display/replay position.  It is deliberately distinct from opaque scene_id."""

    model_config = ConfigDict(extra="forbid")

    volume: Annotated[int, Ge(1)]
    chapter: Annotated[int, Ge(1)]
    ordinal: Annotated[int, Ge(1)]


class SourceRef(BaseModel):
    """Opaque, immutable scene source identity + display/replay order (§3.1)."""

    model_config = ConfigDict(extra="forbid")

    scene_id: SceneId
    location: SceneLocation
    revision: int = 1

    @property
    def ordinal(self) -> int:
        return self.location.ordinal


class ReviewEvidence(BaseModel):
    """§6.3 review gate attached to every CanonEvent."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["approved", "rejected"] = "approved"
    reviewed_artifact_digest: str
    review_digest: str
    review_contract_version: int = 1


# ---------------------------------------------------------------------------
# §4.4 status-transition table (used by the manager + model validators)
# ---------------------------------------------------------------------------

# Allowed forward transitions for each entity kind.  Reverse transitions
# (e.g. resolved -> planted) are intentionally absent — only a
# ``canon_correction`` workflow may perform them.
STATUS_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    "foreshadowing": {
        "planted": ["resolved", "abandoned"],
        "resolved": [],
        "abandoned": [],
    },
    "subplot": {
        "active": ["resolved", "abandoned"],
        "resolved": [],
        "abandoned": [],
    },
    "relationship": {
        "active": ["resolved"],
        "resolved": [],
    },
    "knowledge": {
        "confirmed": [],
        "contested": ["confirmed", "false_belief"],
        "false_belief": [],
    },
    "deadline": {
        "active": ["resolved", "missed"],
        "resolved": [],
        "missed": [],
    },
}


def assert_valid_transition(entity: str, old: str, new: str) -> None:
    """Raise ``ValueError`` if ``old -> new`` is not an allowed forward transition.

    Used by the replay manager when applying a CanonPatch.  Reverse
    transitions are only permitted through a human-approved ``canon_correction``
    workflow, never through a normal scene patch (§4.4).
    """
    allowed = STATUS_TRANSITIONS.get(entity, {}).get(old, None)
    if allowed is None:
        raise ValueError(f"unknown status '{old}' for entity '{entity}'")
    if new not in allowed:
        raise ValueError(
            f"illegal status transition for {entity}: {old} -> {new} "
            f"(allowed: {allowed or 'none'})"
        )


# ---------------------------------------------------------------------------
# §4 Canon sub-structures
# ---------------------------------------------------------------------------


class Constraint(BaseModel):
    model_config = _forbid()

    id: str
    statement: str
    scope: Literal["series", "world"] | str = "series"


class CharacterProfile(BaseModel):
    """Full character profile (Core / Supporting)."""

    model_config = _forbid()

    personality: str | None = None
    motivation: str | None = None
    appearance: str | None = None
    background: str | None = None
    arc: str | None = None
    flaw: str | None = None


class CharacterIdentity(BaseModel):
    """§4.1 named vs role_anchored separation."""

    model_config = _forbid()

    kind: Literal["named", "role_anchored"]
    display_name: str
    aliases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self):
        if not self.display_name or not self.display_name.strip():
            raise ValueError("identity.display_name must be non-empty")
        return self


class ContinuityCard(BaseModel):
    model_config = _forbid()

    current_state: str
    current_location: EntityRef | None = None
    distinguishing_traits: str = ""
    known_constraints: list[str] = Field(default_factory=list)


class Affiliation(BaseModel):
    model_config = _forbid()

    collective: EntityRef
    role: str
    status: Literal["active", "inactive"] = "active"


class Stance(BaseModel):
    """Collective stance toward a character (§4.1)."""

    model_config = _forbid()

    character: EntityRef
    stance: Literal["ally", "suspicious", "hostile", "neutral"]
    reason: str = ""


class Marker(BaseModel):
    """§4.6 story time marker."""

    model_config = _forbid()

    ordinal: Annotated[int, Ge(0)]
    label: str


class Deadline(BaseModel):
    model_config = _forbid()

    id: str
    statement: str
    due_marker: Marker
    status: Literal["active", "resolved", "missed"] = "active"


class StructuralBond(BaseModel):
    model_config = _forbid()

    kind: str
    label: str
    direction: Literal["symmetric", "asymmetric"] = "symmetric"


class SharedState(BaseModel):
    model_config = _forbid()

    cooperation: Literal["none", "conditional", "full"] = "none"
    openness: Literal["open", "guarded", "closed"] = "open"
    central_tension: str = ""
    current_arrangement: str = ""


class Perspective(BaseModel):
    """One participant's view inside a Relationship Arc (§4.2)."""

    model_config = _forbid()

    character_id: str
    attitude: str
    trust: str = "conditional"
    desire_from_other: str = ""
    boundary: str = ""


class HolderState(BaseModel):
    """One holder's knowledge state (§4.6)."""

    model_config = _forbid()

    holder: EntityRef
    state: Literal["knows", "suspects", "believes", "unaware"]
    basis: str | None = None


# ---------------------------------------------------------------------------
# §4 entity models
# ---------------------------------------------------------------------------


class Series(BaseModel):
    model_config = _forbid()

    id: str = "series"
    title: str
    logline: str = ""
    genres: list[str] = Field(default_factory=list)
    target_audience: str = ""
    themes: list[str] = Field(default_factory=list)
    tone: str = ""
    selling_points: list[str] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)


class Character(BaseModel):
    model_config = _forbid()

    id: str
    identity: CharacterIdentity
    importance: Literal["core", "supporting", "minor"]
    tracking_level: Literal["full", "continuity"]
    narrative_function: str
    profile: CharacterProfile | None = None
    continuity_card: ContinuityCard
    affiliations: list[Affiliation] = Field(default_factory=list)
    last_changed_by: EventRef | None = None


class Collective(BaseModel):
    model_config = _forbid()

    id: str
    kind: Literal["organization", "faction", "community", "family"]
    name: str
    function: str
    current_state: str
    stance_toward_characters: list[Stance] = Field(default_factory=list)
    summary: str | None = None
    last_changed_by: EventRef | None = None


class WorldRule(BaseModel):
    model_config = _forbid()

    id: str
    name: str
    statement: str
    scope: str = "world"
    exceptions: list[str] = Field(default_factory=list)


class Glossary(BaseModel):
    model_config = _forbid()

    id: str
    term: str
    definition: str


class CustodyRef(BaseModel):
    """An artifact may only be held by a character, collective, or location."""

    model_config = _forbid()

    kind: Literal["character", "collective", "location"]
    id: str


class Relationship(BaseModel):
    model_config = _forbid()

    id: str
    participant_ids: list[str]
    structural_bonds: list[StructuralBond] = Field(default_factory=list)
    shared_state: SharedState = Field(default_factory=SharedState)
    perspectives: list[Perspective] = Field(default_factory=list)
    arc_summary: str = ""
    lifecycle: Literal["active", "resolved"] = "active"
    last_changed_by: EventRef | None = None

    @model_validator(mode="after")
    def _check(self):
        pids = self.participant_ids
        if len(pids) != 2:
            raise ValueError("Relationship must have exactly 2 participant_ids")
        if any(not pid.startswith("char_") for pid in pids):
            raise ValueError("participant_ids must reference char_* entities only")
        if len(set(pids)) != 2:
            raise ValueError("participant_ids must be two distinct characters")
        # normalize to ascending ID order (§4.2)
        self.participant_ids = sorted(pids)
        # exactly one perspective per participant, both participants present
        if len(self.perspectives) != 2:
            raise ValueError("Relationship must have exactly 2 perspectives")
        pset = {p.character_id for p in self.perspectives}
        if pset != set(self.participant_ids):
            raise ValueError("perspectives must cover exactly the two participants")
        return self


class Foreshadowing(BaseModel):
    model_config = _forbid()

    id: str
    description: str
    status: Literal["planted", "resolved", "abandoned"] = "planted"
    planted_by: EventRef | None = None
    resolved_by: EventRef | None = None
    intended_payoff: str = ""
    related_character_ids: list[str] = Field(default_factory=list)
    related_subplot_ids: list[str] = Field(default_factory=list)
    last_changed_by: EventRef | None = None


class Subplot(BaseModel):
    model_config = _forbid()

    id: str
    name: str
    status: Literal["active", "resolved", "abandoned"] = "active"
    dramatic_question: str
    stakes: str
    current_state: str = ""
    related_character_ids: list[str] = Field(default_factory=list)
    related_foreshadowing_ids: list[str] = Field(default_factory=list)
    last_changed_by: EventRef | None = None


class Location(BaseModel):
    model_config = _forbid()

    id: str
    name: str
    kind: str
    parent_location: EntityRef | None = None
    immutable_constraints: list[str] = Field(default_factory=list)
    current_state: str
    last_changed_by: EventRef | None = None


class Artifact(BaseModel):
    model_config = _forbid()

    id: str
    name: str
    kind: str
    properties: list[str] = Field(default_factory=list)
    custody: CustodyRef | None = None
    condition: str = ""
    narrative_significance: str = ""
    last_changed_by: EventRef | None = None


class Knowledge(BaseModel):
    model_config = _forbid()

    id: str
    proposition: str
    truth_status: Literal["confirmed", "contested", "false_belief"] = "confirmed"
    visibility: Literal["public", "secret"] = "public"
    holders: list[HolderState] = Field(default_factory=list)
    related_entity_refs: list[EntityRef] = Field(default_factory=list)
    last_changed_by: EventRef | None = None


class Chronology(BaseModel):
    model_config = _forbid()

    current_marker: Marker
    active_deadlines: list[Deadline] = Field(default_factory=list)


class Canon(BaseModel):
    model_config = _forbid()

    schema_version: Literal[2] = 2
    series: Series
    characters: list[Character] = Field(default_factory=list)
    collectives: list[Collective] = Field(default_factory=list)
    world_rules: list[WorldRule] = Field(default_factory=list)
    glossary: list[Glossary] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    foreshadowing: list[Foreshadowing] = Field(default_factory=list)
    subplots: list[Subplot] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    knowledge: list[Knowledge] = Field(default_factory=list)
    chronology: Chronology | None = None

    # -- lookup helpers (used by idgen / store / slice) -------------------
    def _kind_list(self, kind: str):
        name = {
            "character": "characters",
            "collective": "collectives",
            "location": "locations",
            "artifact": "artifacts",
            "knowledge": "knowledge",
            "relationship": "relationships",
            "foreshadowing": "foreshadowing",
            "subplot": "subplots",
            "glossary": "glossary",
            "world_rule": "world_rules",
            "deadline": "deadlines",
        }[kind]
        if name == "deadlines":
            return self.chronology.active_deadlines if self.chronology else []
        return getattr(self, name)

    def get_entity(self, kind: str, entity_id: str):
        if kind == "series":
            return self.series
        if kind == "deadline":
            for d in self.chronology.active_deadlines if self.chronology else []:
                if d.id == entity_id:
                    return d
            return None
        for e in self._kind_list(kind):
            if e.id == entity_id:
                return e
        return None

    def all_ids(self) -> set[str]:
        ids = {self.series.id}
        for kind in PREFIX_BY_KIND:
            if kind in ("series", "deadline"):
                continue
            for e in self._kind_list(kind):
                ids.add(e.id)
        if self.chronology:
            for d in self.chronology.active_deadlines:
                ids.add(d.id)
        return ids


# ---------------------------------------------------------------------------
# §5 Design Intent / ContextScope / WriterContext
# ---------------------------------------------------------------------------


class CastCharacter(BaseModel):
    model_config = _forbid()

    kind: Literal["character"] = "character"
    character: EntityRef


class CastLocalRole(BaseModel):
    model_config = _forbid()

    kind: Literal["local_role"] = "local_role"
    label: str
    count: Literal["one", "some", "many", "crowd"]
    scene_function: str


# A cast entry: a stable Character ref OR a scene-local (never Canon) role.
CastEntry = CastCharacter | CastLocalRole


class IntentItem(BaseModel):
    """A typed, reviewable design commitment retained through all phases."""

    model_config = _forbid()

    topic: str
    desired_outcome: str = ""
    constraints: list[str] = Field(default_factory=list)
    target: EntityRef | CreationRef | None = None


class DesignIntent(BaseModel):
    model_config = _forbid()

    constraints: list[str] = Field(default_factory=list)
    foreshadowing: list[IntentItem] = Field(default_factory=list)
    subplots: list[IntentItem] = Field(default_factory=list)
    relationship_arcs: list[IntentItem] = Field(default_factory=list)
    cast: list[IntentItem] = Field(default_factory=list)


class ContextScope(BaseModel):
    """§5.1 typed context scope (no string-search references)."""

    model_config = _forbid()

    pov_character: EntityRef | None = None
    setting: EntityRef | None = None
    required_refs: list[EntityRef] = Field(default_factory=list)


class WriterContext(BaseModel):
    """§6.2 writer projection (no stable IDs / author truth)."""

    model_config = _forbid()

    pov: dict[str, Any] = Field(default_factory=dict)
    cast_constraints: list[dict[str, Any]] = Field(default_factory=list)
    setting_constraints: list[str] = Field(default_factory=list)
    setting_state: list[str] = Field(default_factory=list)
    artifact_constraints: list[str] = Field(default_factory=list)
    artifact_state: list[str] = Field(default_factory=list)
    time_constraints: list[str] = Field(default_factory=list)
    required_story_beats: list[str] = Field(default_factory=list)
    unrevealed_guardrails: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# §6 CanonPatch — create payloads (shared field shapes + creation_key)
# ---------------------------------------------------------------------------


class CharCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    identity: CharacterIdentity
    importance: Literal["core", "supporting", "minor"]
    tracking_level: Literal["full", "continuity"]
    narrative_function: str
    parent_design_intent: IntentItem | None = None
    profile: CharacterProfile | None = None
    continuity_card: ContinuityCard
    affiliations: list[Affiliation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _supporting_requires_parent_intent(self):
        if self.importance == "supporting" and self.parent_design_intent is None:
            raise ValueError("supporting character create requires parent_design_intent")
        return self


class CharStateUpdate(BaseModel):
    model_config = _forbid()

    character: ChangeRef
    current_state: str | None = None
    current_location: EntityRef | None = None


class CharPromote(BaseModel):
    model_config = _forbid()

    character: ChangeRef
    to_importance: Literal["supporting", "core"]
    profile_additions: CharacterProfile | None = None
    reason: str = ""


class CharIdentityReveal(BaseModel):
    model_config = _forbid()

    character: ChangeRef
    display_name: str
    add_aliases: list[str] = Field(default_factory=list)


class CharacterPatchOps(BaseModel):
    model_config = _forbid()

    create: list[CharCreate] = Field(default_factory=list)
    state_updates: list[CharStateUpdate] = Field(default_factory=list)
    promote: list[CharPromote] = Field(default_factory=list)
    identity_reveals: list[CharIdentityReveal] = Field(default_factory=list)


class CollectiveCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    kind: Literal["organization", "faction", "community", "family"]
    name: str
    function: str
    current_state: str
    stance_toward_characters: list[Stance] = Field(default_factory=list)
    summary: str | None = None


class CollectiveStateUpdate(BaseModel):
    model_config = _forbid()

    id: str
    current_state: str


class CollectivePatchOps(BaseModel):
    model_config = _forbid()

    create: list[CollectiveCreate] = Field(default_factory=list)
    state_updates: list[CollectiveStateUpdate] = Field(default_factory=list)


class LocCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    name: str
    kind: str
    parent_location: EntityRef | None = None
    immutable_constraints: list[str] = Field(default_factory=list)
    current_state: str = ""


class LocStateUpdate(BaseModel):
    model_config = _forbid()

    id: str
    current_state: str | None = None
    immutable_constraints: list[str] = Field(default_factory=list)


class LocationPatchOps(BaseModel):
    model_config = _forbid()

    create: list[LocCreate] = Field(default_factory=list)
    state_updates: list[LocStateUpdate] = Field(default_factory=list)


class ArtCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    name: str
    kind: str
    properties: list[str] = Field(default_factory=list)
    custody: CustodyRef | None = None
    narrative_significance: str = ""
    condition: str = ""


class ArtCustodyUpdate(BaseModel):
    model_config = _forbid()

    id: str
    custody: CustodyRef | None = None
    properties: list[str] | None = None


class ArtConditionUpdate(BaseModel):
    model_config = _forbid()

    id: str
    condition: str


class ArtifactPatchOps(BaseModel):
    model_config = _forbid()

    create: list[ArtCreate] = Field(default_factory=list)
    custody_updates: list[ArtCustodyUpdate] = Field(default_factory=list)
    condition_updates: list[ArtConditionUpdate] = Field(default_factory=list)


class KnowCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    proposition: str
    truth_status: Literal["confirmed", "contested", "false_belief"] = "confirmed"
    visibility: Literal["public", "secret"] = "public"
    holders: list[HolderState] = Field(default_factory=list)
    related_entity_refs: list[EntityRef] = Field(default_factory=list)


class HolderStateUpdate(BaseModel):
    model_config = _forbid()

    holder: EntityRef
    state: Literal["knows", "suspects", "believes", "unaware"]
    basis: str | None = None


class KnowledgeHolderUpdate(BaseModel):
    model_config = _forbid()

    knowledge: ChangeRef
    holder_updates: list[HolderStateUpdate] = Field(default_factory=list)


class KnowledgeVisibilityUpdate(BaseModel):
    model_config = _forbid()

    knowledge: EntityRef
    visibility: Literal["public", "secret"]


class KnowledgeTruthTransition(BaseModel):
    model_config = _forbid()

    knowledge: ChangeRef
    to_status: Literal["confirmed", "false_belief"]  # contested -> only (§4.6)


class KnowledgePatchOps(BaseModel):
    model_config = _forbid()

    create: list[KnowCreate] = Field(default_factory=list)
    holder_updates: list[KnowledgeHolderUpdate] = Field(default_factory=list)
    visibility_updates: list[KnowledgeVisibilityUpdate] = Field(default_factory=list)
    truth_status_transitions: list[KnowledgeTruthTransition] = Field(default_factory=list)


class ChronologyPatchOps(BaseModel):
    model_config = _forbid()

    advance_to: Marker | None = None
    deadline_updates: list[dict[str, Any]] = Field(default_factory=list)


class RelCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    participant_ids: list[str]
    structural_bonds: list[StructuralBond] = Field(default_factory=list)
    shared_state: SharedState = Field(default_factory=SharedState)
    perspectives: list[Perspective] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self):
        pids = self.participant_ids
        if any(not pid.startswith("char_") for pid in pids):
            raise ValueError("participant_ids must reference char_* entities only")
        # NOTE: the exactly-2 and perspectives-coverage invariants are enforced
        # by the applier (§6.1), not at model construction, so a malformed
        # create reaches _apply and is rejected as PatchValidationError.
        self.participant_ids = sorted(set(pids))
        return self


class PerspectiveUpdate(BaseModel):
    model_config = _forbid()

    character_id: str
    attitude: str
    trust: str = "conditional"
    desire_from_other: str = ""
    boundary: str = ""


class RelationshipUpdate(BaseModel):
    model_config = _forbid()

    relationship: ChangeRef
    shared_state: SharedState | None = None
    perspective_updates: list[PerspectiveUpdate] = Field(default_factory=list)
    arc_summary: str | None = None
    lifecycle: Literal["resolved"] | None = None  # active -> resolved only (§4.4)


class RelationshipPatchOps(BaseModel):
    model_config = _forbid()

    create: list[RelCreate] = Field(default_factory=list)
    updates: list[RelationshipUpdate] = Field(default_factory=list)


class FhCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    description: str
    intended_payoff: str = ""
    related_character_refs: list[EntityRef] = Field(default_factory=list)


class FhTransition(BaseModel):
    model_config = _forbid()

    foreshadowing: ChangeRef
    status: Literal["planted", "resolved", "abandoned"]  # planted -> only (§4.4)


class ForeshadowingPatchOps(BaseModel):
    model_config = _forbid()

    create: list[FhCreate] = Field(default_factory=list)
    transitions: list[FhTransition] = Field(default_factory=list)


class SpCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    name: str
    dramatic_question: str
    stakes: str
    current_state: str = ""


class SpUpdate(BaseModel):
    model_config = _forbid()

    subplot: ChangeRef
    current_state: str | None = None
    status: Literal["resolved", "abandoned"] | None = None  # active -> only (§4.4)


class SubplotPatchOps(BaseModel):
    model_config = _forbid()

    create: list[SpCreate] = Field(default_factory=list)
    updates: list[SpUpdate] = Field(default_factory=list)


class TermCreate(BaseModel):
    model_config = _forbid()

    creation_key: str
    id: str = ""  # stable id assigned by StableIdGenerator at apply time
    term: str
    definition: str


class GlossaryPatchOps(BaseModel):
    model_config = _forbid()

    create: list[TermCreate] = Field(default_factory=list)


class CanonPatch(BaseModel):
    """§6 full Canon Patch: per-entity create + typed updates."""

    model_config = _forbid()

    characters: CharacterPatchOps = Field(default_factory=CharacterPatchOps)
    collectives: CollectivePatchOps = Field(default_factory=CollectivePatchOps)
    locations: LocationPatchOps = Field(default_factory=LocationPatchOps)
    artifacts: ArtifactPatchOps = Field(default_factory=ArtifactPatchOps)
    knowledge: KnowledgePatchOps = Field(default_factory=KnowledgePatchOps)
    chronology: ChronologyPatchOps = Field(default_factory=ChronologyPatchOps)
    relationships: RelationshipPatchOps = Field(default_factory=RelationshipPatchOps)
    foreshadowing: ForeshadowingPatchOps = Field(default_factory=ForeshadowingPatchOps)
    subplots: SubplotPatchOps = Field(default_factory=SubplotPatchOps)
    glossary: GlossaryPatchOps = Field(default_factory=GlossaryPatchOps)

    @model_validator(mode="wrap")
    @classmethod
    def _wrap_construction(cls, values, handler):
        try:
            return handler(values)
        except ValidationError as exc:
            errs = [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in exc.errors()
            ]
            raise PatchValidationError(
                f"canon patch rejected: {exc.error_count()} violation(s): {'; '.join(errs)}",
                errors=errs,
            ) from exc


class PatchValidationError(ValueError):
    """Raised by the applier when a CanonPatch violates §6.1 constraints.

    Also raised when a patch fails model validation at construction time
    (e.g. an entity create that breaks an invariant such as the 2-participant
    rule for relationships).
    """

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


# ---------------------------------------------------------------------------
# §7 CanonEvent
# ---------------------------------------------------------------------------


class CanonEvent(BaseModel):
    model_config = _forbid()

    event_id: str
    source: SourceRef
    artifact_digest: str
    review_evidence: ReviewEvidence
    patch: CanonPatch
    created_entity_ids: dict[str, str] = Field(default_factory=dict)
    # Scope evidence needed to replay cast-relevant semantic validation without
    # consulting transient runtime design objects.
    scene_cast_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# Canonical JSON / digest helpers (preserved for sibling modules)
# ---------------------------------------------------------------------------


def canonical_json(model: BaseModel) -> str:
    """Deterministic JSON serialization (sorted keys, no None)."""
    data = model.model_dump(mode="json", exclude_none=True)
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_canonical_digest(canon: Canon) -> str:
    """sha256 of the normalized JSON of the entire Canon (§6.2)."""
    return "sha256:" + sha256_hex(canonical_json(canon))


def entity_size(model: BaseModel) -> int:
    """Approximate token/projection budget unit (character count)."""
    return len(canonical_json(model))


def find_refs(obj: Any) -> list[EntityRef]:
    """Recursively collect EntityRef-shaped dicts from any structure (§3.2/§5.1)."""
    out: list[EntityRef] = []
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if keys == {"kind", "id"} and isinstance(obj["id"], str) and isinstance(obj["kind"], str):
            out.append(EntityRef(kind=cast(EntityKind, obj["kind"]), id=obj["id"]))
        else:
            for v in obj.values():
                out.extend(find_refs(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(find_refs(v))
    elif isinstance(obj, BaseModel):
        out.extend(find_refs(obj.model_dump(mode="json", exclude_none=True)))
    return out


def parse_seq(entity_id: str) -> int:
    """Extract trailing numeric sequence from an id like 'char_014' -> 14."""
    digits = "".join(ch for ch in reversed(entity_id) if ch.isdigit())
    return int(digits[::-1]) if digits else 0
