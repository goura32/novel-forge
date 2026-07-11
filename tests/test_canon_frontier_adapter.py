"""Tests for immutable artifact-backed Canon frontier replay."""

from __future__ import annotations

from copy import deepcopy

import pytest

from novel_forge.canon.frontier import FrontierPayloadError, replay_frontier
from novel_forge.canon.models import Canon


def _seed_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "series": {
            "id": "series",
            "title": "Frontier replay test",
        },
        "characters": [
            {
                "id": "char_001",
                "identity": {"kind": "named", "display_name": "A"},
                "importance": "core",
                "tracking_level": "full",
                "narrative_function": "protagonist",
                "continuity_card": {"current_state": "seed"},
            }
        ],
    }


def _event_payload(
    *,
    scene_id: str,
    volume: int,
    chapter: int,
    ordinal: int,
    revision: int = 1,
    state: str,
) -> dict[str, object]:
    digest = f"sha256:{scene_id}-{revision}"
    return {
        "event_id": f"cev_{scene_id}_r{revision}",
        "source": {
            "scene_id": scene_id,
            "location": {"volume": volume, "chapter": chapter, "ordinal": ordinal},
            "revision": revision,
        },
        "artifact_digest": digest,
        "review_evidence": {
            "status": "approved",
            "reviewed_artifact_digest": digest,
            "review_digest": "sha256:review",
            "review_contract_version": 1,
        },
        "patch": {
            "characters": {
                "state_updates": [
                    {
                        "character": {"kind": "character", "id": "char_001"},
                        "current_state": state,
                    }
                ]
            }
        },
    }


def test_empty_frontier_replays_to_seed_without_mutating_seed_payload() -> None:
    seed_payload = _seed_payload()
    original_seed = deepcopy(seed_payload)

    canon = replay_frontier(seed_payload, {"events": []})

    assert canon == Canon.model_validate(original_seed)
    assert seed_payload == original_seed


def test_malformed_event_payload_is_rejected() -> None:
    with pytest.raises(FrontierPayloadError, match="frontier event payload"):
        replay_frontier(_seed_payload(), {"events": [{"event_id": "incomplete"}]})


def test_typed_reference_kind_must_match_the_referenced_entity() -> None:
    event = _event_payload(
        scene_id="scene-knowledge",
        volume=1,
        chapter=1,
        ordinal=1,
        state="unchanged",
    )
    event["patch"] = {
        "knowledge": {
            "create": [
                {
                    "creation_key": "wrong-kind",
                    "proposition": "主人公の秘密",
                    "related_entity_refs": [{"kind": "artifact", "id": "char_001"}],
                }
            ]
        }
    }

    with pytest.raises(FrontierPayloadError, match="typed reference|missing entity|replay point"):
        replay_frontier(_seed_payload(), {"events": [event]})


def test_replay_orders_by_volume_chapter_and_ordinal_not_ordinal_alone() -> None:
    chapter_two = _event_payload(
        scene_id="scene-chapter-two",
        volume=1,
        chapter=2,
        ordinal=1,
        state="chapter two",
    )
    chapter_one = _event_payload(
        scene_id="scene-chapter-one",
        volume=1,
        chapter=1,
        ordinal=99,
        state="chapter one",
    )

    canon = replay_frontier(_seed_payload(), {"events": [chapter_two, chapter_one]})

    character = canon.get_entity("character", "char_001")
    assert character is not None
    assert character.continuity_card.current_state == "chapter two"


# --------------------------------------------------------------------------
# Integrity guards: P0 findings on the public frontier replay path
# --------------------------------------------------------------------------


def test_frontier_rejects_created_entity_id_collision_with_seed() -> None:
    """A schema-valid event that assigns an existing seed id to a create must
    be rejected (created_entity_ids must be unique unused ids)."""
    event = _event_payload(scene_id="scene-dup", volume=1, chapter=1, ordinal=1, state="x")
    event["patch"] = {
        "characters": {
            "create": [
                {
                    "creation_key": "dup",
                    "identity": {"kind": "named", "display_name": "Dup"},
                    "importance": "minor",
                    "tracking_level": "continuity",
                    "narrative_function": "x",
                    "continuity_card": {"current_state": "x"},
                }
            ]
        }
    }
    event["created_entity_ids"] = {"character:dup": "char_001"}  # collides with seed
    with pytest.raises(FrontierPayloadError, match="created_entity_ids|collision|char_001"):
        replay_frontier(_seed_payload(), {"events": [event]})


def test_frontier_rejects_duplicate_active_source_revision() -> None:
    """Two events for the same (scene_id, revision) must be rejected."""
    r1 = _event_payload(scene_id="scene-one", volume=1, chapter=1, ordinal=1, revision=1, state="first")
    r2 = _event_payload(scene_id="scene-one", volume=1, chapter=1, ordinal=1, revision=1, state="second")
    with pytest.raises(FrontierPayloadError, match="duplicate|same source|revision"):
        replay_frontier(_seed_payload(), {"events": [r1, r2]})


def test_frontier_rejects_forward_reference_at_originating_event() -> None:
    """An event that references an entity created by a *later* event must be
    rejected: references must resolve against the canon built so far
    (covers refs apply_patch's targeted checks miss, e.g. knowledge holders)."""
    # scene A creates knowledge referencing loc_room which scene B creates later
    a = _event_payload(scene_id="scene-a", volume=1, chapter=1, ordinal=1, state="x")
    a["created_entity_ids"] = {"knowledge:k1": "know_001"}
    a["patch"] = {
        "knowledge": {
            "create": [
                {
                    "creation_key": "k1",
                    "id": "know_001",
                    "proposition": "部屋の謎",
                    "holders": [],
                    "related_entity_refs": [{"kind": "location", "id": "loc_room"}],
                }
            ]
        }
    }
    b = _event_payload(scene_id="scene-b", volume=1, chapter=1, ordinal=2, state="y")
    b["created_entity_ids"] = {"location:room": "loc_room"}
    b["patch"] = {
        "locations": {
            "create": [
                {
                    "creation_key": "room",
                    "id": "loc_room",
                    "name": "Room",
                    "kind": "room",
                    "current_state": "ok",
                }
            ]
        }
    }
    # loc_room is created by the *later* event -> forward reference rejected
    with pytest.raises(FrontierPayloadError, match="missing entity|references|replay point"):
        replay_frontier(_seed_payload(), {"events": [a, b]})
