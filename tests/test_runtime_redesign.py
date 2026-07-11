"""Contract tests for the immutable runtime redesign."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from novel_forge.config import RuntimeConfig
from novel_forge.runtime import (
    CorruptArtifactError,
    LockHeldError,
    RunManager,
    RunRepository,
    SeriesSlugExistsError,
)
from novel_forge.task_registry import DEFAULT_TASK_REGISTRY


def _run(repo: RunRepository, *, verbose: bool = False):
    return repo.create_run(command="plan", model="test-model", verbose=verbose)


def _artifact(repo: RunRepository, run, *, artifact_type: str, logical_key: str, payload: object, **kwargs):
    attempt = repo.start_attempt(
        run,
        task_id="plan.concept.generate",
        phase="plan",
        reason="generation",
    )
    return repo.commit_artifact(
        attempt,
        artifact_type=artifact_type,
        logical_key=logical_key,
        payload=payload,
        payload_name="payload.json",
        **kwargs,
    )


def test_registry_has_only_explicit_and_complete_resource_ownership() -> None:
    task_ids = {spec.task_id for spec in DEFAULT_TASK_REGISTRY.all()}
    assert len(task_ids) == 16
    assert not any(task_id.startswith(("plan.concept.", "plan.characters.", "plan.volumes.")) for task_id in task_ids)
    assert DEFAULT_TASK_REGISTRY.validate_resources() == []
    assert DEFAULT_TASK_REGISTRY.get("write.draft.revise").schema == "write_draft"
    assert DEFAULT_TASK_REGISTRY.get("write.draft.review").schema == "review_issues"


def test_runtime_config_uses_only_canonical_path_and_cli_workdir_wins(tmp_path: Path) -> None:
    config = RuntimeConfig.model_validate({"workspace": {"root": str(tmp_path / "configured")}})
    assert config.resolve_workdir(tmp_path / "cli") == (tmp_path / "cli").resolve()
    assert config.resolve_workdir(None) == (tmp_path / "configured").resolve()
    with pytest.raises(ValueError, match="作業フォルダが未設定"):
        RuntimeConfig().resolve_workdir(None)


def test_success_attempt_is_immutable_and_ready_before_succeeded(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = _run(repo)
    artifact = _artifact(repo, run, artifact_type="plan.series", logical_key="plan.series", payload={"title": "x"})
    assert (artifact.path / "attempt.json").is_file()
    assert (artifact.path / f"artifact-ready.{artifact.artifact_id}.json").is_file()
    events = [json.loads(line)["event_type"] for line in (run.path / "events.jsonl").read_text().splitlines()]
    assert events[-2:] == ["artifact.ready", "attempt.succeeded"]
    assert repo.verify_artifact(artifact.artifact_id).artifact_id == artifact.artifact_id
    with pytest.raises(FileExistsError):
        repo.writer.write_text(artifact.path / f"artifact-ready.{artifact.artifact_id}.json", "again")


def test_failure_attempt_has_safe_error_and_no_ready_marker(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = _run(repo)
    attempt = repo.start_attempt(run, task_id="plan.concept.generate", phase="plan", reason="generation")
    repo.fail_attempt(attempt, error_code="HTTP_ERROR", retryable=True, http_status=503, detail="provider secret=abc")
    assert not (attempt.path / "artifact-ready.json").exists()
    error = json.loads((attempt.path / "error.json").read_text())
    assert error == {
        "body_saved": False,
        "error_class": "HTTP_ERROR",
        "error_code": "HTTP_ERROR",
        "format_version": 1,
        "http_status": 503,
        "record_type": "attempt_error",
        "retryable": True,
    }
    events = [json.loads(line)["event_type"] for line in (run.path / "events.jsonl").read_text().splitlines()]
    assert events[-1] == "attempt.failed"


def test_snapshot_revalidates_snapshot_and_marker_hashes(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = _run(repo)
    plan = _artifact(repo, run, artifact_type="plan.series", logical_key="plan.series", payload={"title": "x"})
    seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    root = _artifact(
        repo,
        run,
        artifact_type="canon.event_set",
        logical_key="canon.frontier.root",
        payload={"events": []},
        canon_lineage_root_digest=seed.manifest.content_digest,
    )
    snapshot = repo.create_selection_snapshot(
        slug="series",
        slots={"plan.series": plan.artifact_id, "canon.seed": seed.artifact_id, "canon.frontier": root.artifact_id},
        reason="bootstrap",
    )
    assert repo.load_snapshot("series", snapshot.selection_snapshot_id).slots == snapshot.slots
    snapshot_path = repo.ledger_root("series") / "snapshots" / f"{snapshot.selection_snapshot_id}.json"
    snapshot_path.write_text("{}", encoding="utf-8")
    with pytest.raises(CorruptArtifactError, match="snapshot digest"):
        repo.load_snapshot("series", snapshot.selection_snapshot_id)


def test_canon_frontier_parent_chain_accepts_ancestor_and_rejects_branch(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = _run(repo)
    seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed", payload={"seed": True})
    root = _artifact(repo, run, artifact_type="canon.event_set", logical_key="canon.frontier.root", payload={"events": []}, canon_lineage_root_digest=seed.manifest.content_digest)
    patch = _artifact(repo, run, artifact_type="canon.patch", logical_key="canon.patch.1", payload={"patch": 1}, canon_lineage_root_digest=seed.manifest.content_digest, input_canon_frontier_digest=root.manifest.content_digest)
    child = _artifact(repo, run, artifact_type="canon.event_set", logical_key="canon.frontier.1", payload={"events": [1]}, canon_lineage_root_digest=seed.manifest.content_digest, parent_frontier_artifact_id=root.artifact_id, parent_frontier_digest=root.manifest.content_digest, source_patch_artifact_ids=(patch.artifact_id,))
    consumer = _artifact(repo, run, artifact_type="write.draft", logical_key="write.vol01.ch01.sc01.draft", payload={"content": "x"}, canon_lineage_root_digest=seed.manifest.content_digest, input_canon_frontier_digest=root.manifest.content_digest)
    repo.create_selection_snapshot(slug="series", slots={"canon.seed": seed.artifact_id, "canon.frontier": child.artifact_id, "write.vol01.ch01.sc01.draft": consumer.artifact_id}, reason="accepted")
    foreign_seed = _artifact(repo, run, artifact_type="canon.seed", logical_key="canon.seed.foreign", payload={"seed": "foreign"})
    foreign_root = _artifact(repo, run, artifact_type="canon.event_set", logical_key="canon.frontier.foreign", payload={"events": []}, canon_lineage_root_digest=foreign_seed.manifest.content_digest)
    with pytest.raises(Exception, match="canon"):
        repo.create_selection_snapshot(slug="other", slots={"canon.seed": seed.artifact_id, "canon.frontier": foreign_root.artifact_id, "write.vol01.ch01.sc01.draft": consumer.artifact_id}, reason="bad")


def test_nonverbose_capture_never_writes_raw_llm_body_and_diff_requires_capture(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    first = repo.start_attempt(_run(repo), task_id="write.draft.generate", phase="write", reason="generation")
    second = repo.start_attempt(_run(repo), task_id="write.draft.generate", phase="write", reason="generation")
    with pytest.raises(Exception, match="complete verbose capture"):
        repo.llm_diff(first.manifest.attempt_id, second.manifest.attempt_id)
    assert "metadata" in repo.llm_diff(first.manifest.attempt_id, second.manifest.attempt_id, metadata_only=True)


def test_lock_reports_owner_and_slug_collision_does_not_touch_existing_series(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    manager = RunManager(repo)
    run = _run(repo)
    lock = manager.acquire(scope="workspace", run=run, phase="plan")
    try:
        with pytest.raises(LockHeldError, match="run="):
            manager.acquire(scope="workspace", run=run, phase="plan")
    finally:
        lock.release()
    existing = repo.ledger_root("existing")
    existing.mkdir(parents=True)
    workspace = manager.acquire(scope="workspace", run=run, phase="plan")
    try:
        with pytest.raises(SeriesSlugExistsError, match="SERIES_SLUG_EXISTS"):
            manager.promote_plan_to_series(workspace_lock=workspace, run=run, slug="existing")
    finally:
        workspace.release()


def test_runtime_permissions_are_private(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = _run(repo)
    assert (repo.runtime_root.stat().st_mode & 0o777) == 0o700
    assert (run.path.stat().st_mode & 0o777) == 0o700
    assert ((run.path / "run.json").stat().st_mode & 0o777) == 0o600
