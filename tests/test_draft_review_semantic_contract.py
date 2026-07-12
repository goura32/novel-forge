"""Semantic contract for review issues that may be sent to draft revision."""

from __future__ import annotations

import json

from novel_forge.review_contracts import validate_draft_review_actionability
from novel_forge.runtime import RunRepository
from novel_forge.workflow_runtime import RuntimeWorkflow


def _draft() -> dict[str, str]:
    return {"title": "夜の孔", "content": "エリナは暗い孔を見つめた。ルークが頷いた。"}


def _issue(*, before: str, after: str) -> dict[str, str]:
    return {
        "severity": "重要",
        "field": "content",
        "description": "直接修正できる問題です。",
        "suggestion": "置換します。",
        "before": before,
        "after": after,
    }


def test_draft_review_requires_an_editable_exact_span_and_real_replacement() -> None:
    review = {
        "issues": [
            _issue(before="仮設シェルター内は静寂だ。", after="洞窟内は静寂だ。"),
            _issue(before="エリナは暗い孔を見つめた。", after=""),
            _issue(before="ルークが頷いた。", after="ルークが頷いた。"),
        ]
    }

    errors = validate_draft_review_actionability(_draft(), review)

    assert len(errors) == 3
    assert "issues[0].before" in errors[0]
    assert "issues[1].after" in errors[1]
    assert "issues[2].after" in errors[2]


def test_draft_review_allows_exact_span_in_title_or_content() -> None:
    review = {
        "issues": [
            _issue(before="夜の孔", after="夜の洞穴"),
            _issue(before="ルークが頷いた。", after="ルークは小さく頷いた。"),
        ]
    }

    assert validate_draft_review_actionability(_draft(), review) == []


def test_semantically_invalid_draft_review_retries_as_contract_error(tmp_path) -> None:
    repo = RunRepository(tmp_path)
    run = repo.create_run(command="plan", model="fake", verbose=False)
    calls = 0

    def runner(_task: str, _values: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"issues": [_issue(before="writer contextだけの文", after="本文の置換")]} 
        return {"issues": [_issue(before="ルークが頷いた。", after="ルークは頷いた。")]} 

    workflow = RuntimeWorkflow(repo, run, task_runner=runner, max_retry_count=2)
    attempt, result = workflow._run_task(
        "write.draft.review",
        {"writer_context": {}, "draft": _draft()},
        reason="draft review semantic contract",
    )

    assert result["issues"][0]["before"] == "ルークが頷いた。"
    assert attempt.manifest.retry_number == 2
    attempts = sorted((run.path / "attempts").iterdir())
    first_error = json.loads((attempts[0] / "error.json").read_text(encoding="utf-8"))
    assert first_error["error_code"] == "CONTRACT_ERROR"
    assert first_error["retryable"] is True
