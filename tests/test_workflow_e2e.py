"""Snapshot-authoritative end-to-end workflow contracts.

Replaces the legacy mutable-engine integration tests (test_engine_integration.py,
test_export.py, test_public_v2_design_write.py, …) which asserted fixed-file and
mutable-state behavior.  This suite drives ``RuntimeWorkflow`` directly with a
deterministic task runner so it verifies the persistent boundary — plan → design →
write → export — without depending on a live model or the deleted engine.

Key invariants asserted here:
- Every downstream step reads ONLY from the run's immutable selection snapshot.
- A newer, unselected candidate draft does NOT leak into the exported manuscript.
- No legacy fixed files (``series_plan.json``, ``vol01.json``, ``bible.json``,
  ``exports/``) are written outside the runtime tree.
- The summary handoff carries only the writer-safe fields.
"""

from __future__ import annotations

from pathlib import Path

from novel_forge.canon.store import BibleFactory
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def _fake_task(task: str, values: dict[str, object]) -> dict[str, object]:
    """Deterministic task runner producing schema-shaped payloads."""
    if task == "write.draft.generate":
        return {"title": "Scene", "content": "本文です。" * 50}
    if task == "write.summary.generate":
        return {
            "summary": "前のシーンの要点。",
            "end_state": {"pov": "主人公", "setting": "村"},
            "character_changes": [],
            "world_or_item_changes": [],
            "unresolved_threads": [],
            "next_scene_handoff": ["次へ"],
            "facts": [],
        }
    if task.endswith(".review"):
        # No issues on the first review cycle → selection passes.
        return {"issues": [], "suggestions": []}
    if task.endswith(".revise"):
        base = values.get("draft") or values.get("summary") or {}
        return dict(base)  # type: ignore[arg-type]
    if task in ("plan.concept.generate", "plan.series.generate", "plan.canon_seed.generate"):
        return {
            "title": "テストシリーズ",
            "slug": "test_series",
            "planned_volumes": [{"number": 1, "title": "第1巻"}],
            "facts": [],
        }
    if task == "design.volume.generate":
        return {
            "title": "第1巻",
            "chapters": [
                {
                    "number": 1,
                    "title": "第1章",
                    "scenes": [
                        {
                            "chapter_number": 1,
                            "scene_number": 1,
                            "title": "出発",
                            "goal": "旅立ち",
                        },
                        {
                            "chapter_number": 1,
                            "scene_number": 2,
                            "title": "出会い",
                            "goal": "仲間と出会う",
                        },
                    ],
                }
            ],
            "scenes": [
                {"chapter_number": 1, "scene_number": 1, "title": "出発", "goal": "旅立ち", "writer_context": {}},
                {"chapter_number": 1, "scene_number": 2, "title": "出会い", "goal": "仲間と出会う", "writer_context": {}},
            ],
        }
    raise AssertionError(f"unexpected task: {task}")


def _bootstrap(repo: RunRepository, task_runner) -> tuple[str, str, str]:
    run = repo.create_run(command="plan", model="fake", verbose=False)
    workflow = RuntimeWorkflow(repo, run, task_runner=task_runner)
    plan = {
        "title": "テストシリーズ",
        "slug": "test_series",
        "planned_volumes": [{"number": 1, "title": "第1巻"}],
    }
    snapshot = workflow.bootstrap_plan(
        slug="test_series",
        plan=plan,
        canon_seed=BibleFactory.create_seed(plan).model_dump(mode="json"),
    )
    return run.manifest.run_id, snapshot.selection_snapshot_id, "test_series"


def test_complete_pipeline_publishes_snapshot_chain(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    task_runner = _fake_task
    _, input_snapshot, slug = _bootstrap(repo, task_runner)

    design_run = repo.create_run(
        command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot
    )
    design = RuntimeWorkflow(repo, design_run, slug=slug, task_runner=task_runner)
    design_snapshot = design.publish_design(
        1,
        {
            "title": "第1巻",
            "scenes": [
                {"chapter_number": 1, "scene_number": 1, "title": "出発", "goal": "旅立ち", "writer_context": {}},
                {"chapter_number": 1, "scene_number": 2, "title": "出会い", "goal": "仲間と出会う", "writer_context": {}},
            ],
        },
    )

    write_run = repo.create_run(
        command="write", model="fake", verbose=False,
        input_snapshot_id=design_snapshot.selection_snapshot_id,
    )
    writer = RuntimeWorkflow(repo, write_run, slug=slug, task_runner=task_runner)
    written = writer.write_volume(1)
    final_snapshot = repo.load_snapshot(slug, written.selection_snapshot_id)

    assert final_snapshot.slots["write.vol01.ch01.sc01.draft"]
    assert final_snapshot.slots["write.vol01.ch01.sc01.summary"]
    assert final_snapshot.slots["write.vol01.ch01.sc01.final_review"]
    assert final_snapshot.slots["write.vol01.ch01.sc02.draft"]

    export_run = repo.create_run(
        command="export", model="fake", verbose=False,
        input_snapshot_id=written.selection_snapshot_id,
    )
    exporter = RuntimeWorkflow(repo, export_run, slug=slug, task_runner=task_runner)
    manuscript = exporter.export_volume(1)

    assert "本文です。" in manuscript["content"]
    assert manuscript["input_snapshot_id"] == written.selection_snapshot_id


def test_export_markdown_writes_a_pinned_reader_facing_artifact(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    _, input_snapshot, slug = _bootstrap(repo, _fake_task)

    design_run = repo.create_run(
        command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot
    )
    design_snapshot = RuntimeWorkflow(repo, design_run, slug=slug, task_runner=_fake_task).publish_design(
        1,
        {
            "title": "第1巻：旅立ち",
            "scenes": [
                {
                    "chapter_number": 1,
                    "scene_number": 1,
                    "title": "出発",
                    "goal": "旅立ち",
                    "writer_context": {},
                },
                {
                    "chapter_number": 1,
                    "scene_number": 2,
                    "title": "出会い",
                    "goal": "仲間と出会う",
                    "writer_context": {},
                },
            ],
        },
    )
    write_run = repo.create_run(
        command="write", model="fake", verbose=False, input_snapshot_id=design_snapshot.selection_snapshot_id
    )
    written = RuntimeWorkflow(repo, write_run, slug=slug, task_runner=_fake_task).write_volume(1)

    export_run = repo.create_run(
        command="export", model="fake", verbose=False, input_snapshot_id=written.selection_snapshot_id
    )
    markdown = RuntimeWorkflow(repo, export_run, slug=slug, task_runner=_fake_task).export_volume(
        1, format="markdown"
    )

    assert markdown["format"] == "markdown"
    assert markdown["input_snapshot_id"] == written.selection_snapshot_id
    assert markdown["content"].startswith("# 第1巻：旅立ち\n")
    assert "## 第1章\n" in markdown["content"]
    assert "### 出発\n" in markdown["content"]
    assert "### 出会い\n" in markdown["content"]
    assert markdown["content"].count("本文です。") == 100

    ref = repo.verify_artifact(markdown["artifact_id"])
    assert ref.manifest.artifact_type == "export.manuscript.markdown"
    assert ref.manifest.logical_key == "export.vol01.manuscript.markdown"
    assert ref.manifest.payload_path.endswith(".md")
    assert ref.manifest.metadata["input_snapshot_id"] == written.selection_snapshot_id
    assert repo.read_payload(ref) == markdown["content"]


def test_export_ignores_newer_unselected_candidate(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    task_runner = _fake_task
    _, input_snapshot, slug = _bootstrap(repo, task_runner)

    design_run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot)
    design_snapshot = RuntimeWorkflow(repo, design_run, slug=slug, task_runner=task_runner).publish_design(
        1,
        {
            "title": "第1巻",
            "scenes": [{"chapter_number": 1, "scene_number": 1, "title": "出発", "goal": "旅立ち", "writer_context": {}}],
        },
    )
    write_run = repo.create_run(command="write", model="fake", verbose=False, input_snapshot_id=design_snapshot.selection_snapshot_id)
    selected_snapshot = RuntimeWorkflow(repo, write_run, slug=slug, task_runner=task_runner).write_volume(1)

    # Inject a newer, UNSELECTED candidate draft for the same logical key.
    candidate_run = repo.create_run(command="write", model="fake", verbose=False, input_snapshot_id=selected_snapshot.selection_snapshot_id)
    attempt = repo.start_attempt(candidate_run, task_id="write.draft.generate", phase="write", reason="candidate")
    repo.commit_artifact(
        attempt,
        artifact_type="write.draft",
        logical_key="write.vol01.ch01.sc01.draft",
        payload={"content": "より新しいが未選択の本文"},
        payload_name="draft.json",
    )

    export_run = repo.create_run(command="export", model="fake", verbose=False, input_snapshot_id=selected_snapshot.selection_snapshot_id)
    manuscript = RuntimeWorkflow(repo, export_run, slug=slug, task_runner=task_runner).export_volume(1)

    assert "本文です。" in manuscript["content"]
    assert "より新しいが未選択" not in manuscript["content"]


def test_pipeline_writes_no_legacy_fixed_files(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    task_runner = _fake_task
    _, input_snapshot, slug = _bootstrap(repo, task_runner)

    design_run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot)
    design_snapshot = RuntimeWorkflow(repo, design_run, slug=slug, task_runner=task_runner).publish_design(
        1,
        {
            "title": "第1巻",
            "scenes": [{"chapter_number": 1, "scene_number": 1, "title": "出発", "goal": "旅立ち", "writer_context": {}}],
        },
    )
    write_run = repo.create_run(command="write", model="fake", verbose=False, input_snapshot_id=design_snapshot.selection_snapshot_id)
    RuntimeWorkflow(repo, write_run, slug=slug, task_runner=task_runner).write_volume(1)

    assert not (tmp_path / "series_plan.json").exists()
    assert not (tmp_path / "exports").exists()
    assert not (tmp_path / "bible.json").exists()


def test_summary_handoff_carries_only_writer_safe_fields(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    task_runner = _fake_task
    _, input_snapshot, slug = _bootstrap(repo, task_runner)

    design_run = repo.create_run(command="design", model="fake", verbose=False, input_snapshot_id=input_snapshot)
    design_snapshot = RuntimeWorkflow(repo, design_run, slug=slug, task_runner=task_runner).publish_design(
        1,
        {
            "title": "第1巻",
            "scenes": [
                {"chapter_number": 1, "scene_number": 1, "title": "出発", "goal": "旅立ち", "writer_context": {}},
                {"chapter_number": 1, "scene_number": 2, "title": "出会い", "goal": "仲間と出会う", "writer_context": {}},
            ],
        },
    )
    write_run = repo.create_run(command="write", model="fake", verbose=False, input_snapshot_id=design_snapshot.selection_snapshot_id)
    written = RuntimeWorkflow(repo, write_run, slug=slug, task_runner=task_runner).write_volume(1)
    final_snapshot = repo.load_snapshot(slug, written.selection_snapshot_id)

    summary_ref = repo.verify_artifact(final_snapshot.slots["write.vol01.ch01.sc02.summary"])
    summary = repo.read_payload(summary_ref)
    allowed = {
        "summary",
        "end_state",
        "character_changes",
        "world_or_item_changes",
        "unresolved_threads",
        "next_scene_handoff",
        "facts",
    }
    assert set(summary) == allowed
