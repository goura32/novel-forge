from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from novel_forge.canon.design import SceneDesign
from novel_forge.canon.models import SceneLocation, compute_canonical_digest
from novel_forge.canon.store import BibleFactory
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def _approved_state_event(state: str) -> dict[str, object]:
    digest = "sha256:scene-1"
    return {
        "event_id": "cev_scene_001_r1",
        "source": {
            "scene_id": "scene_001",
            "location": {"volume": 1, "chapter": 1, "ordinal": 1},
            "revision": 1,
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

PLAN = {
    "series": {"id": "series", "title": "星海の継承者", "logline": "忘却された星で目覚めた少女"},
    "characters": [
        {
            "id": "char_001",
            "identity": {"kind": "named", "display_name": "リィナ"},
            "importance": "core",
            "tracking_level": "full",
            "narrative_function": "主人公",
            "continuity_card": {"current_state": "覚醒"},
        }
    ],
    "locations": [{"id": "loc_001", "name": "覚醒室", "kind": "facility", "current_state": "静寂"}],
}


def test_workflow_loads_canon_by_replaying_selected_seed_and_frontier(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    seed = BibleFactory.create_seed(PLAN)
    bootstrap_run = repo.create_run(command="plan", model="fake", verbose=False)
    bootstrap = RuntimeWorkflow(repo, bootstrap_run, task_runner=lambda _task, _values: {})
    snapshot = bootstrap.bootstrap_plan(
        slug="series_a",
        plan={"slug": "series_a", **PLAN},
        canon_seed=seed.model_dump(mode="json"),
    )
    read_run = repo.create_run(
        command="design",
        model="fake",
        verbose=False,
        input_snapshot_id=snapshot.selection_snapshot_id,
    )
    workflow = RuntimeWorkflow(repo, read_run, slug="series_a", task_runner=lambda _task, _values: {})

    actual = workflow.load_canon()

    assert actual.schema_version == 2
    assert compute_canonical_digest(actual) == compute_canonical_digest(seed)


def test_workflow_accepts_scene_design_through_reviewed_event_frontier(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    seed = BibleFactory.create_seed(PLAN)
    bootstrap_run = repo.create_run(command="plan", model="fake", verbose=False)
    bootstrap = RuntimeWorkflow(repo, bootstrap_run, task_runner=lambda _task, _values: {})
    snapshot = bootstrap.bootstrap_plan(
        slug="series_a",
        plan={"slug": "series_a", **PLAN},
        canon_seed=seed.model_dump(mode="json"),
    )
    run = repo.create_run(
        command="design",
        model="fake",
        verbose=False,
        input_snapshot_id=snapshot.selection_snapshot_id,
    )
    workflow = RuntimeWorkflow(repo, run, slug="series_a", task_runner=lambda _task, _values: {})
    design = SceneDesign(
        scene_id="scn_001",
        source_location=SceneLocation(volume=1, chapter=1, ordinal=1),
        chapter_number=1,
        scene_number=1,
        title="覚醒",
        goal="状況を把握する",
        conflict="記憶が曖昧",
        outcome="案内人と話す",
        context_scope={
            "pov_character": {"kind": "character", "id": "char_001"},
            "setting": {"kind": "location", "id": "loc_001"},
        },
    )
    patch = {
        "characters": {
            "state_updates": [
                {
                    "character": {"kind": "character", "id": "char_001"},
                    "current_state": "案内人と話す",
                }
            ]
        }
    }

    published, applied = workflow.accept_scene_design(design, patch)

    assert applied.status == "applied"
    assert applied.writer_context is not None
    assert published.slots["canon.frontier"] != snapshot.slots["canon.frontier"]
    assert f"design.scene.{design.scene_id}" in published.slots
    character = workflow.load_canon().get_entity("character", "char_001")
    assert character is not None
    assert cast(Any, character).continuity_card.current_state == "案内人と話す"

def test_workflow_generates_volume_through_typed_scene_event_boundary(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    seed = BibleFactory.create_seed(PLAN)
    bootstrap_run = repo.create_run(command="plan", model="fake", verbose=False)
    bootstrap = RuntimeWorkflow(repo, bootstrap_run, task_runner=lambda _task, _values: {})
    snapshot = bootstrap.bootstrap_plan(
        slug="series_a",
        plan={"slug": "series_a", "planned_volumes": [{"title": "第1巻"}], **PLAN},
        canon_seed=seed.model_dump(mode="json"),
    )
    calls: list[str] = []
    inputs: list[dict[str, Any]] = []

    def task_runner(task_id: str, values: dict[str, Any]) -> dict[str, Any]:
        calls.append(task_id)
        inputs.append(values)
        if task_id == "design.volume.generate":
            return {"title": "第1巻", "premise": "覚醒", "chapters": [{"title": "覚醒", "purpose": "導入"}]}
        if task_id == "design.chapter.generate":
            return {
                "title": "覚醒", "purpose": "導入", "theme": "覚醒", "emotional_arc": "不安から安堵", "outcome": "対話を始める",
                "scenes": [{"title": "覚醒", "pov": "リィナ", "goal": "状況を把握する", "conflict": "記憶が曖昧", "outcome": "案内人と話す", "characters": ["リィナ"], "key_events": ["目を覚ます"], "setting": "覚醒室"}],
                "chapter_turning_point": "目覚める", "chapter_hook": "案内人が現れる", "foreshadowing_notes": ["星図"], "subplot_notes": ["記憶喪失"],
            }
        if task_id.endswith(".review"):
            return {"issues": []}
        if task_id == "design.scene.generate":
            return {
                "title": "覚醒", "goal": "状況を把握する", "conflict": "記憶が曖昧", "outcome": "案内人と話す", "pov_character_id": "char_001", "character_ids": ["char_001"], "key_events": ["目を覚ます"], "location_id": "loc_001", "hook": "目を開ける", "turning_point": "端末が光る", "emotional_arc": "不安から安堵", "ending_hook": "扉が開く",
                "canon_updates": [{"operation": "set_character_state", "target_id": "char_001", "value": "案内人と話す"}],
            }
        raise AssertionError(task_id)

    run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id=snapshot.selection_snapshot_id)
    workflow = RuntimeWorkflow(repo, run, slug="series_a", task_runner=task_runner)

    published = workflow.generate_volume_design(volume=1, plan={"planned_volumes": [{"title": "第1巻"}]})

    assert calls == [
        "design.volume.generate", "design.volume.review",
        "design.chapter.generate", "design.chapter.review",
        "design.scene.generate", "design.scene.review",
    ]
    for task_input in inputs:
        assert "canon_context" in task_input
        assert "bible" not in task_input
        assert "char_001" in str(task_input["canon_context"])
    scene_review_inputs = [
        values for task_id, values in zip(calls, inputs, strict=True) if task_id == "design.scene.review"
    ]
    assert len(scene_review_inputs) == 1
    assert scene_review_inputs[0]["scene_seed"] == {
        "title": "覚醒",
        "pov": "リィナ",
        "goal": "状況を把握する",
        "conflict": "記憶が曖昧",
        "outcome": "案内人と話す",
        "characters": ["リィナ"],
        "key_events": ["目を覚ます"],
        "setting": "覚醒室",
    }
    assert published.slots["canon.frontier"] != snapshot.slots["canon.frontier"]
    generated = repo.read_payload(repo.verify_artifact(published.slots["design.vol01"]))
    assert generated["scenes"][0]["status"] == "applied"
    assert generated["scenes"][0]["writer_context"]


def test_review_cap_keeps_last_contract_valid_scene_candidate(tmp_path: Path) -> None:
    """A later invalid revise must not replace an earlier Canon-valid scene."""
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    review_count = 0
    revise_candidates = iter(
        [
            {"location_id": "loc_001", "title": "valid intermediate"},
            {"location_id": "loc_003", "title": "invalid final"},
        ]
    )

    def task_runner(task_id: str, _values: dict[str, Any]) -> dict[str, Any]:
        nonlocal review_count
        if task_id == "design.scene.review":
            review_count += 1
            return {"issues": [{"description": "continue revision"}] if review_count == 2 else []}
        if task_id == "design.scene.revise":
            return next(revise_candidates)
        raise AssertionError(task_id)

    workflow = RuntimeWorkflow(
        repo,
        run,
        task_runner=task_runner,
        max_review_count=3,
    )
    initial_attempt = workflow._attempt("design.scene.generate", "test invalid candidate")

    attempt, candidate = workflow._review_and_revise(
        "design.scene",
        {"location_id": "loc_003", "title": "invalid initial"},
        initial_attempt,
        review_values=lambda current: {"candidate": current},
        revise_values=lambda current, review: {"candidate": current, "review": review},
        contract_issues=lambda current: (
            []
            if current["location_id"] == "loc_001"
            else [{"severity": "error", "message": "unknown Canon location"}]
        ),
    )

    assert attempt != initial_attempt
    assert candidate == {"location_id": "loc_001", "title": "valid intermediate"}


def test_scene_candidate_normalizer_drops_unknown_artifact_update(tmp_path: Path) -> None:
    """A hallucinated artifact update must not abort an otherwise valid scene."""
    repo = RunRepository(tmp_path)
    seed = BibleFactory.create_seed(PLAN)
    bootstrap_run = repo.create_run(command="plan", model="fake", verbose=False)
    bootstrap = RuntimeWorkflow(repo, bootstrap_run, task_runner=lambda _task, _values: {})
    snapshot = bootstrap.bootstrap_plan(
        slug="series_a",
        plan={"slug": "series_a", **PLAN},
        canon_seed=seed.model_dump(mode="json"),
    )
    run = repo.create_run(
        command="design",
        model="fake",
        verbose=False,
        input_snapshot_id=snapshot.selection_snapshot_id,
    )
    workflow = RuntimeWorkflow(repo, run, slug="series_a", task_runner=lambda _task, _values: {})
    raw_scene = {
        "title": "覚醒",
        "goal": "状況を把握する",
        "conflict": "記憶が曖昧",
        "outcome": "案内人と話す",
        "pov_character_id": "char_001",
        "character_ids": ["char_001"],
        "key_events": ["目を覚ます"],
        "location_id": "loc_001",
        "hook": "目を開ける",
        "turning_point": "端末が光る",
        "emotional_arc": "不安から安堵",
        "ending_hook": "扉が開く",
        "canon_updates": [
            {"operation": "set_character_state", "target_id": "char_001", "value": "案内人と話す"},
            {
                "operation": "set_artifact_condition",
                "target_id": "photo_akane",
                "value": "現像済み",
            },
        ],
    }

    with pytest.warns(UserWarning, match="dropped 1 Canon-invalid scene update"):
        candidate = workflow._normalize_scene_update_targets(raw_scene, workflow.load_canon())
    _design, patch = workflow._scene_from_generated_payload(
        candidate,
        canon=workflow.load_canon(),
        volume=1,
        chapter=1,
        ordinal=1,
    )

    published, applied = workflow.accept_scene_design(_design, patch)

    assert raw_scene["canon_updates"][1]["target_id"] == "photo_akane"
    assert candidate["canon_updates"] == [raw_scene["canon_updates"][0]]
    assert applied.status == "applied"
    assert f"design.scene.{applied.scene_id}" in published.slots
    assert patch["characters"]["state_updates"] == [
        {"character": {"kind": "character", "id": "char_001"}, "current_state": "案内人と話す"}
    ]
    assert patch["artifacts"]["condition_updates"] == []


def test_scene_payload_without_canon_updates_is_rejected(tmp_path: Path) -> None:
    """Runtime must refuse a scene design that omits the small Canon update DSL."""
    from novel_forge.runtime import RuntimeContractError

    repo = RunRepository(tmp_path)
    seed = BibleFactory.create_seed(PLAN)
    bootstrap_run = repo.create_run(command="plan", model="fake", verbose=False)
    bootstrap = RuntimeWorkflow(repo, bootstrap_run, task_runner=lambda _task, _values: {})
    snapshot = bootstrap.bootstrap_plan(
        slug="series_a",
        plan={"slug": "series_a", "planned_volumes": [{"title": "第1巻"}], **PLAN},
        canon_seed=seed.model_dump(mode="json"),
    )
    run = repo.create_run(
        command="design", model="fake", verbose=False,
        input_snapshot_id=snapshot.selection_snapshot_id,
    )
    workflow = RuntimeWorkflow(repo, run, slug="series_a", task_runner=lambda _t, _v: {})
    canon = workflow.load_canon()

    raw_scene = {
        "title": "覚醒", "goal": "状況を把握する", "conflict": "記憶が曖昧",
        "outcome": "案内人と話す", "pov_character_id": "char_001", "character_ids": ["char_001"],
        "key_events": ["目を覚ます"], "location_id": "loc_001", "hook": "目を開ける",
        "turning_point": "端末が光る", "emotional_arc": "不安から安堵",
        "ending_hook": "扉が開く",
        # canon_updates intentionally omitted
    }
    with pytest.raises(RuntimeContractError, match="canon_updates"):
        workflow._scene_from_generated_payload(raw_scene, canon=canon, volume=1, chapter=1, ordinal=1)


def test_workflow_publishes_replayed_event_set_as_new_selected_frontier(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    seed = BibleFactory.create_seed(PLAN)
    bootstrap_run = repo.create_run(command="plan", model="fake", verbose=False)
    bootstrap = RuntimeWorkflow(repo, bootstrap_run, task_runner=lambda _task, _values: {})
    snapshot = bootstrap.bootstrap_plan(
        slug="series_a",
        plan={"slug": "series_a", **PLAN},
        canon_seed=seed.model_dump(mode="json"),
    )
    run = repo.create_run(
        command="design",
        model="fake",
        verbose=False,
        input_snapshot_id=snapshot.selection_snapshot_id,
    )
    workflow = RuntimeWorkflow(repo, run, slug="series_a", task_runner=lambda _task, _values: {})

    published = workflow.publish_canon_event(_approved_state_event("scene applied"))
    character = workflow.load_canon().get_entity("character", "char_001")

    assert published.slots["canon.frontier"] != snapshot.slots["canon.frontier"]
    assert character is not None
    assert cast(Any, character).continuity_card.current_state == "scene applied"
