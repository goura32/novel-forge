"""Transport retries must be recorded as distinct immutable attempts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from novel_forge.llm_client import LLMClient, LLMError, LLMTransportError
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def _make_streaming_response(chunks: list[str]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.iter_lines = MagicMock(return_value=iter([chunk.encode() for chunk in chunks]))
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_resp)
    mock_ctx.__exit__ = MagicMock(return_value=False)
    return mock_ctx


def _ndjson_response(full: str) -> MagicMock:
    return _make_streaming_response([json.dumps({"message": {"content": full}, "done": True})])


def test_transport_failure_surfaces_without_internal_retry(tmp_path: Path) -> None:
    """LLMClient no longer retries transport failures; the workflow loop owns retry."""
    client = LLMClient(api_url="http://x/api/chat")

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise httpx.TimeoutException("boom")

    with patch("novel_forge.llm_client.httpx.stream", side_effect=boom), pytest.raises(LLMError):
        client.complete_json("test_kind", "sys", "usr")

    # The transport error must be a typed, retry-eligible signal.
    with patch("novel_forge.llm_client.httpx.stream", side_effect=boom), pytest.raises(LLMTransportError):
        client.complete_json("test_kind", "sys", "usr")


def test_workflow_retries_transport_failure_as_distinct_attempts(tmp_path: Path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=True)
    workflow = RuntimeWorkflow(repo, run, task_runner=lambda _t, _v: {})
    workflow.max_generation_count = 3
    task_id = "plan.series.generate"

    # First two calls fail at the transport layer; the third succeeds.
    attempts_before = len(list((run.path / "attempts").iterdir()))
    calls = {"n": 0}

    def flaky(_task_id: str, _values: dict[str, Any]) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] < 3:
            raise LLMTransportError("transient down")
        return {"slug": "s", "title": "t", "planned_volumes": [{"number": 1, "title": "V"}]}

    workflow.task_runner = flaky
    attempt, result = workflow._run_task(task_id, {}, reason="generate")

    assert result["slug"] == "s"
    attempts_after = len(list((run.path / "attempts").iterdir()))
    # two failed attempts + one success == 3 new attempts
    assert attempts_after - attempts_before == 3
