"""Tests for CanonEventStore / BibleFactory / replay / recovery / reset (§7, §8)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Canon,
    CanonEvent,
    CanonPatch,
    ReviewEvidence,
    SourceRef,
    compute_canonical_digest,
)
from novel_forge.canon.store import (
    BibleFactory,
    CanonEventStore,
    ReviewEvidenceMismatchError,
    SeedImmutableError,
)


def _write_seed(store: CanonEventStore) -> Canon:
    plan = {
        "series": {
            "id": "series",
            "title": "T",
            "constraints": [{"id": "constraint_001", "statement": "X", "scope": "series"}],
        },
        "characters": [
            {
                "id": "char_001",
                "identity": {"kind": "named", "display_name": "A", "aliases": []},
                "importance": "core",
                "tracking_level": "full",
                "narrative_function": "主人公",
                "profile": None,
                "continuity_card": {
                    "current_state": "start",
                    "current_location": {"kind": "location", "id": "loc_001"},
                },
            }
        ],
        "locations": [
            {"id": "loc_001", "name": "街", "kind": "city", "immutable_constraints": ["夜封鎖"], "current_state": ""}
        ],
        "chronology": {
            "current_marker": {"ordinal": 0, "label": "開始"},
            "active_deadlines": [
                {"id": "deadline_001", "statement": "夜明けまで", "due_marker": {"ordinal": 1, "label": "朝"}, "status": "active"}
            ],
        },
    }
    canon = BibleFactory.create_seed(plan)
    store.write_seed(canon)
    return canon


def _src(scene_id="scn_A", ordinal=1, revision=1):
    return SourceRef(
        scene_id=scene_id,
        location={"volume": 1, "chapter": 1, "ordinal": ordinal},
        revision=revision,
    )


def _approved_event(source, patch, artifact_digest, created_entity_ids=None):
    return CanonEvent(
        event_id=f"cev_{source.scene_id}_r{source.revision}",
        source=source,
        artifact_digest=artifact_digest,
        review_evidence=ReviewEvidence(
            status="approved",
            reviewed_artifact_digest=artifact_digest,
            review_digest=artifact_digest,
            review_contract_version=1,
        ),
        patch=patch,
        created_entity_ids=created_entity_ids or {},
    )


def test_bible_factory_seed_and_write(tmp_path):
    store = CanonEventStore(tmp_path)
    canon = _write_seed(store)
    assert (tmp_path / "bible_seed.json").exists()
    assert canon.series.title == "T"
    assert canon.get_entity("character", "char_001") is not None


def test_bible_factory_maps_public_plan_genre_to_canon_genres() -> None:
    canon = BibleFactory.create_seed({"title": "T", "genre": ["mystery", "fantasy"]})
    assert canon.series.genres == ["mystery", "fantasy"]


def test_replay_idempotent(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    patch = CanonPatch(
        characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "決意"}]}
    )
    ev = _approved_event(_src("scn_A", 1), patch, "sha256:abc")
    store.save_events([ev])

    c1 = store.replay(seed)
    c2 = store.replay(seed)
    assert compute_canonical_digest(c1) == compute_canonical_digest(c2)
    assert c1.get_entity("character", "char_001").continuity_card.current_state == "決意"


def test_replay_order_deterministic_by_ordinal(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    p1 = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "first"}]})
    p2 = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "second"}]})
    ev1 = _approved_event(_src("scn_B", 2), p2, "sha256:b")
    ev2 = _approved_event(_src("scn_A", 1), p1, "sha256:a")
    store.save_events([ev1, ev2])
    canon = store.replay(seed)
    # later ordinal wins
    assert canon.get_entity("character", "char_001").continuity_card.current_state == "second"


def test_stable_id_created_across_replays(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    gen = StableIdGenerator()
    patch = CanonPatch(
        characters={
            "create": [
                {
                    "creation_key": "sister_voice",
                    "identity": {"kind": "role_anchored", "display_name": "妹の声", "aliases": []},
                    "importance": "minor",
                    "tracking_level": "continuity",
                    "narrative_function": "声",
                    "profile": None,
                    "continuity_card": {"current_state": "石の中"},
                }
            ]
        }
    )
    source = _src("scn_A", 1)
    patch, created = gen.assign(patch, seed, source)
    assert "character:sister_voice" in created
    assert created["character:sister_voice"].startswith("char_")

    ev = _approved_event(source, patch, "sha256:x", created_entity_ids=created)
    store.save_events([ev])
    canon = store.replay(seed)
    # created entity present with assigned id
    assert canon.get_entity("character", created["character:sister_voice"]) is not None

    # revision reuses the same id
    patch2 = CanonPatch(
        characters={
            "create": [
                {
                    "creation_key": "sister_voice",
                    "identity": {"kind": "role_anchored", "display_name": "妹の声", "aliases": []},
                    "importance": "minor",
                    "tracking_level": "continuity",
                    "narrative_function": "声",
                    "profile": None,
                    "continuity_card": {"current_state": "石の中"},
                }
            ]
        }
    )
    source2 = _src("scn_A", 1, revision=2)
    patch2, created2 = gen.assign(patch2, canon, source2, existing_events=[ev])
    assert created2["character:sister_voice"] == created["character:sister_voice"]


def test_recover_regenerates_stale_materialized_view(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    patch = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "changed"}]})
    ev = _approved_event(_src("scn_A", 1), patch, "sha256:abc")
    store.save_events([ev])

    # materialize a WRONG view (stale)
    store.materialize(seed)
    assert (tmp_path / "bible.json").exists()
    stale_digest = compute_canonical_digest(seed)

    recovered = store.recover()
    assert compute_canonical_digest(recovered) != stale_digest
    # bible.json now matches replay digest
    stored = Canon.model_validate_json((tmp_path / "bible.json").read_text())
    assert compute_canonical_digest(stored) == compute_canonical_digest(recovered)


def test_recovery_stop_on_review_mismatch(tmp_path):
    store = CanonEventStore(tmp_path)
    _write_seed(store)
    patch = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "x"}]})
    ev = _approved_event(_src("scn_A", 1), patch, "sha256:real")
    ev.review_evidence = ReviewEvidence(
        status="rejected",
        reviewed_artifact_digest="sha256:real",
        review_digest="sha256:real",
        review_contract_version=1,
    )
    store.save_events([ev])
    try:
        store.recover()
    except ReviewEvidenceMismatchError:
        pass
    else:
        raise AssertionError("expected ReviewEvidenceMismatchError")


def test_dependency_rejection_on_segment_replacement(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    # scene A creates an artifact
    gen = StableIdGenerator()
    create_patch = CanonPatch(
        artifacts={
            "create": [
                {"creation_key": "key", "name": "鍵", "kind": "tool", "properties": [], "condition": "", "narrative_significance": ""}
            ]
        }
    )
    src_a = _src("scn_A", 1)
    create_patch, created = gen.assign(create_patch, seed, src_a)
    ev_a = _approved_event(src_a, create_patch, "sha256:a", created_entity_ids=created)
    store.save_events([ev_a])

    # scene B references that artifact
    ref_patch = CanonPatch(
        characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "持った"}]},
    )
    # make B reference the artifact via an artifact custody update
    ref_patch.artifacts = CanonPatch.model_validate({
        "artifacts": {
            "custody_updates": [
                {"id": created["artifact:key"], "custody": {"kind": "character", "id": "char_001"}}
            ]
        }
    }).artifacts
    src_b = _src("scn_B", 2)
    ev_b = _approved_event(src_b, ref_patch, "sha256:b")
    store.save_events([ev_a, ev_b])

    # attempt to remove scene A (which created the artifact) without surviving replacement
    errors = store.validate_segment_replacement(
        removed_scene_ids=["scn_A"], replacement_events=[], events=[ev_a, ev_b]
    )
    assert len(errors) == 1
    assert created["artifact:key"] in errors[0]


def test_dependency_accepted_when_replacement_survives(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    gen = StableIdGenerator()
    create_patch = CanonPatch(
        artifacts={
            "create": [
                {"creation_key": "key", "name": "鍵", "kind": "tool", "properties": [], "condition": "", "narrative_significance": ""}
            ]
        }
    )
    src_a = _src("scn_A", 1)
    create_patch, created = gen.assign(create_patch, seed, src_a)
    ev_a = _approved_event(src_a, create_patch, "sha256:a", created_entity_ids=created)
    store.save_events([ev_a])

    # replacement event for scene A re-creates the same artifact id
    repl_patch = CanonPatch(
        artifacts={
            "create": [
                {"creation_key": "key", "name": "鍵", "kind": "tool", "properties": [], "condition": "", "narrative_significance": ""}
            ]
        }
    )
    repl_patch, repl_created = gen.assign(repl_patch, seed, src_a, existing_events=[ev_a])
    repl_ev = _approved_event(_src("scn_A", 1, revision=2), repl_patch, "sha256:ar", created_entity_ids=repl_created)
    errors = store.validate_segment_replacement(
        removed_scene_ids=["scn_A"], replacement_events=[repl_ev], events=[ev_a]
    )
    assert errors == []


def test_plan_seed_immutable_after_events(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    patch = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "x"}]})
    store.save_events([_approved_event(_src("scn_A", 1), patch, "sha256:a")])
    try:
        store.write_seed(seed)
    except SeedImmutableError:
        pass
    else:
        raise AssertionError("expected SeedImmutableError")


def test_reset_discards_events(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    patch = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "x"}]})
    store.save_events([_approved_event(_src("scn_A", 1), patch, "sha256:a")])
    assert store.events_path.exists()
    store.reset_series_canon()
    assert not store.events_path.exists()
    # after reset, seed is mutable again
    store.write_seed(seed)


def test_replace_source_atomic(tmp_path):
    store = CanonEventStore(tmp_path)
    seed = _write_seed(store)
    patch = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "v1"}]})
    store.save_events([_approved_event(_src("scn_A", 1, revision=1), patch, "sha256:1")])
    patch2 = CanonPatch(characters={"state_updates": [{"character": {"kind": "character", "id": "char_001"}, "current_state": "v2"}]})
    store.replace_source(_src("scn_A", 1, revision=2), [_approved_event(_src("scn_A", 1, revision=2), patch2, "sha256:2")])
    active = store.load_active()
    assert len(active) == 1
    assert active[0].source.revision == 2
    canon = store.replay(seed)
    assert canon.get_entity("character", "char_001").continuity_card.current_state == "v2"
