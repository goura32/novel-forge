"""Regression tests for Series Bible v2 review findings.

Each test captures a behavior required by
``docs/dev/SERIES_BIBLE_SCHEMA_REDESIGN.md`` that the initial Phase 3–5
integration did not enforce.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Artifact,
    CanonPatch,
    PatchValidationError,
    Relationship,
    ReviewEvidence,
    SourceRef,
    Subplot,
)
from novel_forge.canon.patch_apply import CanonPatchApplier
from novel_forge.canon.runtime import (
    ReviewResult,
    apply_reviewed_patch,
    attach_projection,
    build_chapter_intent,
    build_scene_design,
    build_volume_intent,
    review_scene_patch,
)
from novel_forge.canon.store import (
    BibleFactory,
    CanonEventStore,
)
from tests.test_v2_pipeline_e2e import _BASIC_SCOPE, SERIES_PLAN, _make_patch


def _design(canon):
    volume = build_volume_intent(SERIES_PLAN, 1)
    chapter = build_chapter_intent(volume, 1)
    return attach_projection(build_scene_design(chapter, 1, _BASIC_SCOPE), canon)


def _store() -> tuple[TemporaryDirectory[str], CanonEventStore]:
    tmp = TemporaryDirectory()
    store = CanonEventStore(Path(tmp.name))
    store.write_seed(BibleFactory.create_seed(SERIES_PLAN))
    return tmp, store


def _state_patch(state: str) -> dict:
    return _make_patch(
        characters={
            "create": [],
            "state_updates": [
                {
                    "character": {"kind": "character", "id": "char_001"},
                    "current_state": state,
                }
            ],
            "promote": [],
            "identity_reveals": [],
        }
    )


def test_rejected_review_never_persists_an_event():
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(seed)
        rejected = ReviewResult(passed=False, issues=["continuity conflict"])

        with pytest.raises(ValueError, match="review"):
            apply_reviewed_patch(design, _make_patch(), seed, store, rejected)

        assert store.load_active() == []
        assert design.status == "draft"
    finally:
        tmp.cleanup()


def test_source_replacement_materializes_replay_not_incremental_live_state():
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(seed)
        patch_v1 = _state_patch("old")
        live_v1, _ = apply_reviewed_patch(
            design, patch_v1, seed, store, review_scene_patch(design, patch_v1, seed), revision=1
        )
        patch_v2 = _make_patch()
        design = attach_projection(design, live_v1)
        live_v2, _ = apply_reviewed_patch(
            design,
            patch_v2,
            live_v1,
            store,
            review_scene_patch(design, patch_v2, live_v1),
            revision=2,
        )

        replayed = store.replay()
        assert live_v2 == replayed
        assert live_v2.characters[0].continuity_card.current_state == "冷凍睡眠から覚醒"
        assert store.recover() == replayed
    finally:
        tmp.cleanup()


def test_corrupt_materialized_cache_is_regenerated_from_seed_and_events():
    tmp, store = _store()
    try:
        store.bible_path.write_text("{not json", encoding="utf-8")
        canon = store.recover()

        assert canon.series.title == "星海の継承者"
        assert store.bible_path.read_text(encoding="utf-8").startswith("{")
    finally:
        tmp.cleanup()


def test_review_rejects_a_projection_built_from_stale_canon():
    seed = BibleFactory.create_seed(SERIES_PLAN)
    design = _design(seed)
    changed = seed.model_copy(deep=True)
    changed.characters[0].continuity_card.current_state = "projection after state changed"

    review = review_scene_patch(design, _make_patch(), changed)

    assert not review.passed
    assert any("canon digest" in issue for issue in review.issues)


def test_relationship_and_subplot_status_transitions_are_applied():
    canon = BibleFactory.create_seed(SERIES_PLAN)
    canon.relationships.append(
        Relationship(
            id="rel_001",
            participant_ids=["char_001", "char_002"],
            structural_bonds=[{"kind": "trust", "label": "協力"}],
            perspectives=[
                {"character_id": "char_001", "attitude": "警戒"},
                {"character_id": "char_002", "attitude": "協力"},
            ],
        )
    )
    canon.subplots.append(
        Subplot(
            id="sp_001",
            name="脱出",
            dramatic_question="脱出できるか",
            stakes="命",
        )
    )
    patch = CanonPatch.model_validate(
        _make_patch(
            relationships={
                "create": [],
                "updates": [
                    {"relationship": {"kind": "relationship", "id": "rel_001"}, "lifecycle": "resolved"}
                ],
            },
            subplots={
                "create": [],
                "updates": [{"subplot": {"kind": "subplot", "id": "sp_001"}, "status": "resolved"}],
            },
        )
    )

    applied, _ = CanonPatchApplier().apply(
        canon,
        patch,
        SourceRef(scene_id="scn_opaque_a", location={"volume": 1, "chapter": 1, "ordinal": 1}),
        ReviewEvidence(
            status="approved",
            reviewed_artifact_digest="sha256:test",
            review_digest="sha256:review",
        ),
        StableIdGenerator(),
        scene_cast_ids={"char_001"},
    )

    assert applied.relationships[0].lifecycle == "resolved"
    assert applied.subplots[0].status == "resolved"



def test_supporting_character_requires_parent_design_intent():
    bad = _make_patch(
        characters={
            "create": [{
                "creation_key": "supporting_without_intent",
                "identity": {"kind": "named", "display_name": "準主役"},
                "importance": "supporting",
                "tracking_level": "full",
                "narrative_function": "相棒",
                "continuity_card": {"current_state": "登場"},
            }],
            "state_updates": [], "promote": [], "identity_reveals": [],
        }
    )
    with pytest.raises(ValueError, match="parent_design_intent"):
        CanonPatch.model_validate(bad)


def test_custody_reference_must_match_the_actual_entity_kind():
    canon = BibleFactory.create_seed(SERIES_PLAN)
    canon.artifacts.append(
        Artifact(
            id="art_001",
            name="通行証",
            kind="document",
            condition="完全",
        )
    )
    patch = CanonPatch.model_validate(
        _make_patch(
            artifacts={
                "create": [],
                "custody_updates": [
                    {
                        "id": "art_001",
                        "custody": {"kind": "character", "id": "loc_001"},
                    }
                ],
                "condition_updates": [],
            }
        )
    )

    with pytest.raises(PatchValidationError, match="custody"):
        CanonPatchApplier().apply(
            canon,
            patch,
            SourceRef(scene_id="scn_opaque_a", location={"volume": 1, "chapter": 1, "ordinal": 1}),
            ReviewEvidence(
                status="approved",
                reviewed_artifact_digest="sha256:test",
                review_digest="sha256:review",
            ),
            StableIdGenerator(),
        )
