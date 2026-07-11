"""Selection-authoritative workflow contracts.

These tests use a deterministic task runner so the persistent boundary is tested
without depending on a live local model.
"""

from __future__ import annotations

from pathlib import Path

from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def _task_result(task: str, values: dict[str, object]) -> dict[str, object]:
    if task == "write.draft.generate":
        return {"content": "draft"}
    if task == "write.summary.generate":
        return {"summary": "handoff", "end_state": {}, "character_changes": [], "world_or_item_changes": [], "unresolved_threads": [], "next_scene_handoff": [], "facts": []}
    if task.endswith("review"):
        return {"issues": []}
    if task.endswith("revise"):
        return dict(values.get("draft") or values.get("summary") or {})
    raise AssertionError(task)


def _bootstrap(repo: RunRepository) -> tuple[str, str]:
    run = repo.create_run(command="plan", model="fake", verbose=False)
    workflow = RuntimeWorkflow(repo, run, task_runner=lambda task, values: values["result"])
    snapshot = workflow.bootstrap_plan(
        slug="series",
        plan={"title": "Series", "planned_volumes": [{"number": 1, "title": "Vol"}]},
        canon_seed={"facts": []},
    )
    return run.manifest.run_id, snapshot.selection_snapshot_id


def test_bootstrap_plan_creates_only_snapshot_authoritative_roots(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    _, snapshot_id = _bootstrap(repo)
    snapshot = repo.load_snapshot("series", snapshot_id)

    assert set(snapshot.slots) == {"plan.series", "canon.seed", "canon.frontier"}
    assert repo.current_snapshot_id("series") == snapshot_id


def test_design_and_write_publish_new_snapshot_without_mutating_input(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    _, input_snapshot = _bootstrap(repo)
    run = repo.create_run(
        command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot
    )
    workflow = RuntimeWorkflow(repo, run, slug="series", task_runner=lambda task, values: values["result"])
    design_snapshot = workflow.publish_design(
        1,
        {"title": "Vol", "scenes": [{"chapter_number": 1, "scene_number": 1, "title": "S"}]},
    )
    assert repo.load_snapshot("series", input_snapshot).slots.keys() == {
        "plan.series", "canon.seed", "canon.frontier"
    }
    assert "design.vol01" in design_snapshot.slots

    write_run = repo.create_run(
        command="write", model="fake", verbose=False,
        input_snapshot_id=design_snapshot.selection_snapshot_id,
    )
    writer = RuntimeWorkflow(repo, write_run, slug="series", task_runner=_task_result)
    written = writer.write_volume(1)
    final_snapshot = repo.load_snapshot("series", written.selection_snapshot_id)
    assert final_snapshot.slots["write.vol01.ch01.sc01.draft"]
    assert final_snapshot.slots["write.vol01.ch01.sc01.summary"]
    assert final_snapshot.slots["write.vol01.ch01.sc01.final_review"]


def test_export_uses_the_pinned_snapshot_not_newer_unselected_candidate(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    _, input_snapshot = _bootstrap(repo)
    design_run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot)
    design = RuntimeWorkflow(repo, design_run, slug="series", task_runner=lambda task, values: values["result"])
    design_snapshot = design.publish_design(
        1, {"title": "Vol", "scenes": [{"chapter_number": 1, "scene_number": 1, "title": "S"}]}
    )
    write_run = repo.create_run(command="write", model="fake", verbose=False, input_snapshot_id=design_snapshot.selection_snapshot_id)
    writer = RuntimeWorkflow(
        repo,
        write_run,
        slug="series",
        task_runner=lambda task, values: {"content": "selected draft"} if task == "write.draft.generate" else {"issues": []} if task.endswith("review") else {"summary": "handoff"},
    )
    selected_snapshot = writer.write_volume(1)

    candidate_run = repo.create_run(command="write", model="fake", verbose=False, input_snapshot_id=selected_snapshot.selection_snapshot_id)
    candidate = candidate_run
    attempt = repo.start_attempt(candidate, task_id="write.draft.generate", phase="write", reason="candidate")
    repo.commit_artifact(
        attempt, artifact_type="write.draft", logical_key="write.vol01.ch01.sc01.draft",
        payload={"content": "newer but unselected"}, payload_name="draft.json",
    )

    export_run = repo.create_run(command="export", model="fake", verbose=False, input_snapshot_id=selected_snapshot.selection_snapshot_id)
    exporter = RuntimeWorkflow(repo, export_run, slug="series", task_runner=lambda task, values: values["result"])
    manuscript = exporter.export_volume(1)
    assert manuscript["content"] == "selected draft"
