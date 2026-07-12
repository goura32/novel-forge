"""RuntimeWorkflow generation retries are immutable attempt records."""

from __future__ import annotations

import json

from novel_forge.llm_client import LLMError
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def test_generation_retry_uses_a_new_attempt_and_preserves_failure(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    calls = 0

    def runner(_task: str, _values: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise LLMError("schema validation error: missing required field")
        return {"title": "recovered"}

    workflow = RuntimeWorkflow(repo, run, task_runner=runner, max_retry_count=2)
    attempt, result = workflow._run_task("plan.series.generate", {}, reason="retry contract")

    assert result == {"title": "recovered"}
    assert attempt.manifest.retry_number == 2
    attempts = sorted((run.path / "attempts").iterdir())
    assert len(attempts) == 2
    first = json.loads((attempts[0] / "attempt.json").read_text(encoding="utf-8"))
    first_error = json.loads((attempts[0] / "error.json").read_text(encoding="utf-8"))
    second = json.loads((attempts[1] / "attempt.json").read_text(encoding="utf-8"))
    assert first["retry_number"] == 1
    assert first_error["retryable"] is True
    assert second["retry_number"] == 2


def test_task_capture_writes_evidence_even_when_run_is_not_verbose(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    captured = []

    def runner(_task: str, _values: dict[str, object]) -> dict[str, object]:
        capture = captured[-1]
        capture.request({"Authorization": "Bearer test-token"})
        capture.response_ndjson([{"message": {"content": "{}", "thinking": "hidden"}}])
        capture.response_content("{}")
        capture.parsed({"title": "ok"})
        capture.validation({"outcome": "passed"})
        return {"title": "ok"}

    def set_attempt_capture(capture) -> None:
        if capture is not None:
            captured.append(capture)

    runner.set_attempt_capture = set_attempt_capture  # type: ignore[attr-defined]
    workflow = RuntimeWorkflow(repo, run, task_runner=runner)
    attempt, _ = workflow._run_task("plan.series.generate", {}, reason="capture contract")

    llm = attempt.path / "llm"
    assert {path.name for path in llm.iterdir()} == {
        "request.json", "response.ndjson", "response.content.json", "parsed.json", "validation.json"
    }
    request = (llm / "request.json").read_text(encoding="utf-8")
    ndjson = (llm / "response.ndjson").read_text(encoding="utf-8")
    assert "test-token" not in request
    assert "[REDACTED]" in request
    assert "thinking" not in ndjson
