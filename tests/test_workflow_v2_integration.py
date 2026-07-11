from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from novel_forge.canon.models import compute_canonical_digest
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
