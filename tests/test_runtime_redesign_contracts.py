"""Acceptance contracts that define the destructive runtime migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from novel_forge.runtime import (
    CorruptArtifactError,
    RunManifest,
    RunRepository,
    RuntimeContractError,
)


def _run(repo: RunRepository, *, command: str = "plan", verbose: bool = False):
    return repo.create_run(command=command, model="test-model", verbose=verbose)


def _artifact(
    repo: RunRepository,
    run,
    *,
    artifact_type: str = "plan.series",
    logical_key: str = "plan.series",
    payload: object = None,
):
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
        payload={} if payload is None else payload,
        payload_name="payload.json",
    )


def test_unknown_record_format_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unsupported format_version"):
        RunManifest(
            format_version=999,
            run_id="run_test",
            command="plan",
            workspace="/workspace",
            input_snapshot_id=None,
            input_kind="bootstrap",
            started_at="2026-07-11T00:00:00Z",
            verbose=False,
            model="test-model",
        )


def test_only_plan_may_start_a_bootstrap_run(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    with pytest.raises(RuntimeContractError, match="only plan"):
        _run(repo, command="design")


def test_selection_slot_must_match_referenced_artifact_logical_key(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    artifact = _artifact(repo, _run(repo), logical_key="plan.other")

    with pytest.raises(RuntimeContractError, match="logical key"):
        repo.create_selection_snapshot(
            slug="series",
            slots={"plan.series": artifact.artifact_id},
            reason="invalid-slot",
        )


def test_payload_read_revalidates_ready_artifact_hash(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    artifact = _artifact(repo, _run(repo), payload={"title": "original"})
    (artifact.path / artifact.manifest.payload_path).write_text('{"title":"tampered"}', encoding="utf-8")

    with pytest.raises(CorruptArtifactError, match="digest mismatch"):
        repo.read_payload(artifact)


def test_verbose_failure_redacts_inline_credentials(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    attempt = repo.start_attempt(
        _run(repo, verbose=True),
        task_id="plan.concept.generate",
        phase="plan",
        reason="generation",
    )
    repo.fail_attempt(
        attempt,
        error_code="HTTP_ERROR",
        retryable=False,
        detail="Authorization: Bearer top-secret; api_key=hunter2; token=xyz",
    )

    stored = json.dumps(json.loads((attempt.path / "error.json").read_text(encoding="utf-8")))
    assert "top-secret" not in stored
    assert "hunter2" not in stored
    assert "xyz" not in stored
    assert "[REDACTED]" in stored
