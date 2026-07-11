"""Tests for CanonPatchApplier (§6.1 constraints).

Uses fake data only — no Ollama, no network, no I/O. Each scenario builds a
small seed ``Canon`` and a ``CanonPatch``, applies it through
:class:`CanonPatchApplier`, and asserts the resulting ``Canon`` / ``CanonEvent``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Artifact,
    Canon,
    CanonPatch,
    Character,
    CharacterIdentity,
    CharacterProfile,
    Chronology,
    ContinuityCard,
    Deadline,
    EntityRef,
    Foreshadowing,
    Knowledge,
    Location,
    Marker,
    Relationship,
    ReviewEvidence,
    Series,
    SourceRef,
)
from novel_forge.canon.patch_apply import CanonPatchApplier, PatchValidationError


def _review() -> ReviewEvidence:
    return ReviewEvidence(
        status="approved",
        reviewed_artifact_digest="sha256:abc",
        review_digest="sha256:rev",
        review_contract_version=1,
    )


def _source(scene_id: str = "scn_01", revision: int = 1) -> SourceRef:
    return SourceRef(
        scene_id=scene_id,
        location={"volume": 1, "chapter": 1, "ordinal": 1},
        revision=revision,
    )


def er(kind: str, eid: str) -> dict:
    """Build an EntityRef-shaped dict for patch payloads."""
    return {"kind": kind, "id": eid}


def _base_canon() -> Canon:
    return Canon(
        series=Series(id="series", title="test", logline="", genres=[], themes=[], tone=""),
        characters=[
            Character(
                id="char_001",
                identity=CharacterIdentity(kind="named", display_name="アリーン"),
                importance="core",
                tracking_level="full",
                narrative_function="protagonist",
                profile=CharacterProfile(
                    personality="quiet", motivation="find sister", appearance=None,
                    background=None, arc=None, flaw=None,
                ),
                continuity_card=ContinuityCard(
                    current_state="arrived",
                    current_location=EntityRef(kind="location", id="loc_stone_city"),
                ),
                affiliations=[],
            ),
            Character(
                id="char_002",
                identity=CharacterIdentity(kind="named", display_name="ベル"),
                importance="supporting",
                tracking_level="full",
                narrative_function="ally",
                profile=None,
                continuity_card=ContinuityCard(current_state="watching"),
                affiliations=[],
            ),
            Character(
                id="char_014",
                identity=CharacterIdentity(kind="role_anchored", display_name="北門の薬師"),
                importance="minor",
                tracking_level="continuity",
                narrative_function="gives clue",
                profile=None,
                continuity_card=ContinuityCard(current_state="suspicious"),
                affiliations=[],
            ),
        ],
        locations=[
            Location(
                id="loc_stone_city",
                name="石の都",
                kind="city",
                immutable_constraints=["night gate closed"],
                current_state="normal",
            )
        ],
        artifacts=[
            Artifact(
                id="art_001",
                name="記憶石",
                kind="magical_item",
                properties=["replay one memory"],
                custody={"kind": "character", "id": "char_001"},
                condition="cracked",
            )
        ],
        knowledge=[
            Knowledge(
                id="know_001",
                proposition="sister memory sealed in stone",
                truth_status="contested",
                visibility="secret",
                holders=[
                    {"holder": {"kind": "character", "id": "char_002"}, "state": "suspects"}
                ],
            )
        ],
        relationships=[
            Relationship(
                id="rel_001",
                participant_ids=["char_001", "char_002"],
                structural_bonds=[{"kind": "kinship", "label": "sisters", "direction": "symmetric"}],
                shared_state={"cooperation": "conditional"},
                perspectives=[
                    {"character_id": "char_001", "attitude": "protective", "trust": "guarded",
                     "desire_from_other": "truth", "boundary": "no solo"},
                    {"character_id": "char_002", "attitude": "wary", "trust": "conditional",
                     "desire_from_other": "equal", "boundary": "no orders"},
                ],
                arc_summary="reunion",
            )
        ],
        foreshadowing=[
            Foreshadowing(
                id="fh_001",
                description="voice in stone",
                status="planted",
                intended_payoff="reveal",
                related_character_ids=["char_001"],
            )
        ],
        chronology=Chronology(
            current_marker=Marker(ordinal=3, label="day3"),
            active_deadlines=[
                Deadline(
                    id="deadline_gate",
                    statement="cross gate by dawn",
                    due_marker=Marker(ordinal=4, label="day4 dawn"),
                    status="active",
                )
            ],
        ),
    )


def _apply(canon, patch, scene_cast_ids=None, **kw):
    applier = CanonPatchApplier()
    new_canon, event = applier.apply(
        canon, patch, _source(), _review(), StableIdGenerator(),
        scene_cast_ids=scene_cast_ids, **kw,
    )
    return new_canon, event


# --------------------------------------------------------------------------
# 0. Patch payload integrity
# --------------------------------------------------------------------------


def test_location_state_update_requires_an_actual_state_change():
    """An empty update must not coerce Location.current_state to None."""
    with pytest.raises(ValidationError, match="current_state"):
        CanonPatch.model_validate({"locations": {"state_updates": [{"id": "loc_stone_city"}]}})


def test_character_state_update_requires_a_location_ref() -> None:
    with pytest.raises(ValidationError, match="current_location"):
        CanonPatch.model_validate(
            {
                "characters": {
                    "state_updates": [
                        {
                            "character": {"kind": "character", "id": "char_001"},
                            "current_location": {"kind": "character", "id": "char_002"},
                        }
                    ]
                }
            }
        )


# --------------------------------------------------------------------------
# 1. Minor create
# --------------------------------------------------------------------------


def test_minor_create():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "create": [{
                "creation_key": "north_gate_guard",
                "identity": {"kind": "role_anchored", "display_name": "北門の衛兵"},
                "importance": "minor",
                "tracking_level": "continuity",
                "narrative_function": "guards gate",
                "continuity_card": {
                    "current_state": "watching",
                    "current_location": er("location", "loc_stone_city"),
                },
            }]
        }
    )
    new_canon, event = _apply(canon, patch)
    assert len(new_canon.characters) == 4
    created = [c for c in new_canon.characters if c.identity.display_name == "北門の衛兵"][0]
    assert created.id == event.created_entity_ids["character:north_gate_guard"]
    assert created.importance == "minor"
    # pure: original canon untouched
    assert len(canon.characters) == 3


# --------------------------------------------------------------------------
# 2. role-anchored identity reveal
# --------------------------------------------------------------------------


def test_identity_reveal_role_anchored_to_named():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "identity_reveals": [{
                "character": er("character", "char_014"),
                "display_name": "ガルド",
                "add_aliases": ["北門の薬師"],
            }]
        }
    )
    new_canon, event = _apply(canon, patch)
    ch = new_canon.get_entity("character", "char_014")
    assert ch.identity.kind == "named"
    assert ch.identity.display_name == "ガルド"
    assert "北門の薬師" in ch.identity.aliases
    assert ch.importance == "minor"  # unchanged


def test_identity_reveal_on_named_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "identity_reveals": [{
                "character": er("character", "char_001"),
                "display_name": "newname",
                "add_aliases": [],
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


# --------------------------------------------------------------------------
# 3. Minor -> Supporting promotion
# --------------------------------------------------------------------------


def test_minor_to_supporting_promotion():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "promote": [{
                "character": er("character", "char_014"),
                "to_importance": "supporting",
                "profile_additions": {"motivation": "guard the north gate"},
                "reason": "recurring antagonist",
            }]
        }
    )
    new_canon, event = _apply(canon, patch)
    ch = new_canon.get_entity("character", "char_014")
    assert ch.importance == "supporting"
    assert ch.profile is not None
    assert ch.profile.motivation == "guard the north gate"
    assert ch.identity.kind == "role_anchored"  # unchanged


def test_promote_rejects_profile_correction():
    canon = _base_canon()
    canon.get_entity("character", "char_002").profile = CharacterProfile(
        personality="quiet", motivation=None, appearance=None, background=None, arc=None, flaw=None
    )
    patch = CanonPatch(
        characters={
            "promote": [{
                "character": er("character", "char_002"),
                "to_importance": "core",
                "profile_additions": {"personality": "loud"},  # overwrite existing
                "reason": "x",
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_promote_non_strict_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "promote": [{
                "character": er("character", "char_001"),  # core already
                "to_importance": "supporting",
                "profile_additions": {},
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


# --------------------------------------------------------------------------
# 4. Artifact custody transfer
# --------------------------------------------------------------------------


def test_artifact_custody_transfer():
    canon = _base_canon()
    patch = CanonPatch(
        artifacts={
            "custody_updates": [{
                "id": "art_001",
                "custody": {"kind": "character", "id": "char_002"},
            }]
        }
    )
    new_canon, event = _apply(canon, patch)
    art = new_canon.get_entity("artifact", "art_001")
    assert art.custody is not None
    assert art.custody.model_dump() == {"kind": "character", "id": "char_002"}


def test_artifact_custody_invalid_kind_rejected():
    with pytest.raises(ValueError, match="character.*collective.*location"):
        CanonPatch(
            artifacts={
                "custody_updates": [{
                    "id": "art_001",
                    "custody": {"kind": "relationship", "id": "rel_001"},
                }]
            }
        )


def test_artifact_properties_update_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        artifacts={
            "custody_updates": [{
                "id": "art_001",
                "properties": ["new power"],  # correction-only
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


# --------------------------------------------------------------------------
# 5. Knowledge contested->confirmed + POV leak rejection
# --------------------------------------------------------------------------


def test_knowledge_contested_to_confirmed():
    canon = _base_canon()
    patch = CanonPatch(
        knowledge={
            "truth_status_transitions": [{
                "knowledge": er("knowledge", "know_001"),
                "to_status": "confirmed",
            }]
        }
    )
    new_canon, event = _apply(canon, patch)
    k = new_canon.get_entity("knowledge", "know_001")
    assert k.truth_status == "confirmed"


def test_knowledge_pov_leak_rejected():
    """Promoting an off-scene, basis-less holder to 'knows' must be rejected."""
    canon = _base_canon()
    patch = CanonPatch(
        knowledge={
            "holder_updates": [{
                "knowledge": er("knowledge", "know_001"),
                "holder_updates": [
                    {"holder": {"kind": "character", "id": "char_002"}, "state": "knows"}
                ],
            }]
        }
    )
    # char_002 not in scene cast and no explicit basis -> POV leak guard
    with pytest.raises(PatchValidationError):
        _apply(canon, patch, scene_cast_ids=set())


def test_knowledge_holder_update_with_basis_ok():
    canon = _base_canon()
    patch = CanonPatch(
        knowledge={
            "holder_updates": [{
                "knowledge": er("knowledge", "know_001"),
                "holder_updates": [
                    {"holder": {"kind": "character", "id": "char_002"},
                     "state": "knows", "basis": "observation"}
                ],
            }]
        }
    )
    new_canon, event = _apply(canon, patch, scene_cast_ids={"char_002"})
    k = new_canon.get_entity("knowledge", "know_001")
    assert k.holders[0].state == "knows"


def test_knowledge_confirmed_to_false_belief_rejected():
    canon = _base_canon()
    canon.get_entity("knowledge", "know_001").truth_status = "confirmed"
    patch = CanonPatch(
        knowledge={
            "truth_status_transitions": [{
                "knowledge": er("knowledge", "know_001"),
                "to_status": "false_belief",
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


# --------------------------------------------------------------------------
# 6. Chronology ordinal monotonic forward
# --------------------------------------------------------------------------


def test_chronology_advance_forward_ok():
    canon = _base_canon()
    patch = CanonPatch(chronology={"advance_to": {"ordinal": 4, "label": "day4"}})
    new_canon, event = _apply(canon, patch)
    assert new_canon.chronology.current_marker.ordinal == 4


def test_chronology_equal_ordinal_rejected():
    canon = _base_canon()
    patch = CanonPatch(chronology={"advance_to": {"ordinal": 3, "label": "renamed"}})
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_chronology_rewind_rejected():
    canon = _base_canon()
    patch = CanonPatch(chronology={"advance_to": {"ordinal": 2, "label": "day2"}})
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_chronology_deadline_resolve_ok():
    canon = _base_canon()
    patch = CanonPatch(
        chronology={"deadline_updates": [{"id": "deadline_gate", "status": "resolved"}]}
    )
    new_canon, event = _apply(canon, patch)
    d = new_canon.chronology.active_deadlines[0]
    assert d.status == "resolved"


def test_chronology_deadline_invalid_transition_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        chronology={"deadline_updates": [{"id": "deadline_gate", "status": "planted"}]}
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


# --------------------------------------------------------------------------
# 7. Relationship asymmetric perspective update
# --------------------------------------------------------------------------


def test_relationship_asymmetric_perspective_update():
    canon = _base_canon()
    patch = CanonPatch(
        relationships={
            "updates": [{
                "relationship": er("relationship", "rel_001"),
                "perspective_updates": [
                    {"character_id": "char_001", "attitude": "trusting", "trust": "open"}
                ],
            }]
        }
    )
    new_canon, event = _apply(canon, patch, scene_cast_ids={"char_001"})
    rel = new_canon.get_entity("relationship", "rel_001")
    p1 = [p for p in rel.perspectives if p.character_id == "char_001"][0]
    p2 = [p for p in rel.perspectives if p.character_id == "char_002"][0]
    assert p1.attitude == "trusting"
    assert p1.trust == "open"
    assert p2.attitude == "wary"


def test_relationship_update_offstage_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        relationships={
            "updates": [{
                "relationship": er("relationship", "rel_001"),
                "perspective_updates": [
                    {"character_id": "char_001", "attitude": "x"}
                ],
            }]
        }
    )
    # neither participant in cast
    with pytest.raises(PatchValidationError):
        _apply(canon, patch, scene_cast_ids=set())


def test_relationship_create_requires_two_participants_and_perspectives():
    canon = _base_canon()
    patch = CanonPatch(
        relationships={
            "create": [{
                "creation_key": "rel_new",
                "participant_ids": ["char_001"],  # only one
                "structural_bonds": [{"kind": "kinship", "label": "x", "direction": "symmetric"}],
                "shared_state": {},
                "perspectives": [
                    {"character_id": "char_001", "attitude": "a", "trust": "b",
                     "desire_from_other": "c", "boundary": "d"}
                ],
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


# --------------------------------------------------------------------------
# 8. Forbidden operations (correction-only) rejected
# --------------------------------------------------------------------------


def test_core_character_create_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "create": [{
                "creation_key": "boss",
                "identity": {"kind": "named", "display_name": "Big Boss"},
                "importance": "core",
                "tracking_level": "full",
                "narrative_function": "antagonist",
                "continuity_card": {"current_state": "x"},
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_location_immutable_constraint_update_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        locations={
            "state_updates": [{
                "id": "loc_stone_city",
                "current_state": "normal",
                "immutable_constraints": ["changed"],  # correction-only
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_character_current_location_unknown_rejected():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "state_updates": [{
                "character": er("character", "char_001"),
                "current_location": er("location", "loc_unknown"),
            }]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_foreshadowing_non_planted_transition_rejected():
    canon = _base_canon()
    canon.get_entity("foreshadowing", "fh_001").status = "resolved"
    patch = CanonPatch(
        foreshadowing={
            "transitions": [{"foreshadowing": er("foreshadowing", "fh_001"), "status": "planted"}]
        }
    )
    with pytest.raises(PatchValidationError):
        _apply(canon, patch)


def test_event_digest_and_review_recorded():
    canon = _base_canon()
    patch = CanonPatch(
        characters={
            "state_updates": [{"character": er("character", "char_001"), "current_state": "decided"}]
        }
    )
    new_canon, event = _apply(canon, patch)
    assert event.artifact_digest.startswith("sha256:")
    assert event.review_evidence.status == "approved"
    assert new_canon.get_entity("character", "char_001").continuity_card.current_state == "decided"


# --------------------------------------------------------------------------
# 9. No-op / empty updates rejected (spec violation guard)
# --------------------------------------------------------------------------


def test_location_state_update_noop_rejected():
    """A state update that repeats the current value must be rejected as a
    no-op (empty update must not pass as a real change)."""
    canon = _base_canon()
    patch = CanonPatch(
        locations={
            "state_updates": [{"id": "loc_stone_city", "current_state": "normal"}]
        }
    )
    with pytest.raises(PatchValidationError, match="no-op|unchanged|same"):
        _apply(canon, patch)


def test_relationship_lifecycle_resolved_accepts_valid_transition():
    canon = _base_canon()
    patch = CanonPatch(
        relationships={
            "updates": [
                {
                    "relationship": er("relationship", "rel_001"),
                    "lifecycle": "resolved",
                }
            ]
        }
    )
    new_canon, event = _apply(canon, patch, scene_cast_ids={"char_001"})
    rel = new_canon.get_entity("relationship", "rel_001")
    assert rel.lifecycle == "resolved"


def test_relationship_lifecycle_invalid_transition_rejected():
    with pytest.raises((PatchValidationError, ValidationError), match="lifecycle|resolved"):
        CanonPatch(
            relationships={
                "updates": [
                    {
                        "relationship": er("relationship", "rel_001"),
                        "lifecycle": "dormant",  # not in allowed set
                    }
                ]
            }
        )

