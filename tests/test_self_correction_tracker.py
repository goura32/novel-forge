"""Tests for canon self-correction tracking (review-gate telemetry).

These verify the *observer* layer only: it must never mutate the Canon, a
CanonEvent, or the materialized view.  It records review issues and detects
recurrence so a repeated mistake class surfaces instead of staying buried in
per-scene logs.
"""

from __future__ import annotations

from pathlib import Path

from novel_forge.canon.models import (
    Canon,
    ContextScope,
    SceneLocation,
    WriterContext,
)
from novel_forge.canon.runtime import (
    attach_projection,
    build_chapter_intent,
    build_scene_design,
    build_volume_intent,
    review_scene_patch,
)
from novel_forge.canon.self_correction_tracker import (
    POV_LEAK,
    SCHEMA,
    SelfCorrectionTracker,
    classify_review_issues,
)
from novel_forge.canon.store import BibleFactory, CanonEventStore
from tests.test_v2_pipeline_e2e import _BASIC_SCOPE, SERIES_PLAN, SceneDesign


def _secret_knowledge_plan() -> dict:
    """SERIES_PLAN plus a secret knowledge proposition (drives POV-leak)."""
    plan = {k: v for k, v in SERIES_PLAN.items()}
    plan["knowledge"] = [
        {
            "id": "know_secret",
            "proposition": "船長は記憶の珠を隠匿している",
            "truth_status": "confirmed",
            "visibility": "secret",
            "holders": [
                {"holder": {"kind": "character", "id": "char_001"}, "state": "knows"}
            ],
            "related_entity_refs": [],
        }
    ]
    return plan


def _seed_with_secret(tmp_path: Path) -> Canon:
    store = CanonEventStore(tmp_path)
    seed = BibleFactory.create_seed(_secret_knowledge_plan())
    store.write_seed(seed)
    return seed


def _design_with_pov(canon: Canon) -> SceneDesign:
    vol = build_volume_intent(SERIES_PLAN, 1)

    ch = build_chapter_intent(vol, 1)
    scope = ContextScope.model_validate(_BASIC_SCOPE)
    design = build_scene_design(
        ch,
        1,
        scope,
        source_location=SceneLocation(volume=1, chapter=1, ordinal=1),
    )
    return attach_projection(design, canon)


def test_classify_categorizes_issue_tags():
    issues = [
        "[pov_leak] secret author truth leaked into writer_context: '船長は記憶の珠を隠匿している'",
        "[canon_patch schema] [/characters] required",
        "[cast_relevant] relationship rel_001 involves out-of-scope cast: ['char_002']",
    ]
    records = classify_review_issues(issues, scene_id="scn_x")
    assert records[0].category == POV_LEAK
    assert records[1].category == SCHEMA
    assert records[2].category == "cast_relevant"
    assert all(r.scene_id == "scn_x" for r in records)
    assert records[0].recurring_key.startswith(POV_LEAK + ":")


def test_recurring_detects_repeated_mistake_class():
    tracker = SelfCorrectionTracker()
    leak_a = "[pov_leak] secret author truth leaked: '船長は記憶の珠を隠匿している'"
    leak_b = "[pov_leak] secret author truth leaked: '船長は記憶の珠を隠匿している'"
    other = "[canon_patch schema] [/x] required"
    tracker.record_issues([leak_a, other])
    tracker.record_issues([leak_b])
    recur = tracker.recurring(min_count=2)
    assert len(recur) == 1
    key = next(iter(recur))
    assert key.startswith(POV_LEAK + ":")
    assert recur[key][0].category == POV_LEAK


def test_recurring_ignores_distinct_messages():
    tracker = SelfCorrectionTracker()
    tracker.record_issues(["[pov_leak] alpha leaked"])
    tracker.record_issues(["[pov_leak] beta leaked"])
    assert tracker.recurring(min_count=2) == {}


def test_persistence_roundtrip(tmp_path: Path):
    p = tmp_path / "corrections.jsonl"
    t1 = SelfCorrectionTracker(path=p)
    t1.record_issues(["[pov_leak] secret leaked"], scene_id="scn_1")
    t2 = SelfCorrectionTracker(path=p)
    assert len(t2.records) == 1
    assert t2.records[0].category == POV_LEAK
    assert t2.categories()[POV_LEAK] == 1


def test_review_scene_patch_records_pov_leak_when_tracker_passed(tmp_path: Path):
    canon = _seed_with_secret(tmp_path)
    design = _design_with_pov(canon)
    # Inject a POV leak: the secret proposition text appears in writer_context.
    design.writer_context = WriterContext(
        pov={"display_name": "レイ"},
        cast_constraints=[{"text": "船長は記憶の珠を隠匿している"}],
        setting_constraints=[],
        artifact_state=[],
        time_constraints=[],
        unrevealed_guardrails=[],
        required_story_beats=[],
    )
    tracker = SelfCorrectionTracker()
    review = review_scene_patch(design, {"characters": {}}, canon, tracker=tracker)
    assert not review.passed
    assert any(POV_LEAK in r.category for r in tracker.records)
    # Canon itself is untouched by tracking.
    assert canon.get_entity("knowledge", "know_secret").visibility == "secret"


def test_tracker_does_not_record_when_review_passes(tmp_path: Path):
    canon = _seed_with_secret(tmp_path)
    design = _design_with_pov(canon)
    tracker = SelfCorrectionTracker()
    patch = {
        "characters": {
            "state_updates": [
                {"character": {"kind": "character", "id": "char_001"}, "current_state": "探索を開始した"}
            ]
        }
    }
    review = review_scene_patch(design, patch, canon, tracker=tracker)
    assert review.passed
    assert tracker.records == []
