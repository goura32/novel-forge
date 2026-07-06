"""Review/generation loop retry contracts."""

from __future__ import annotations

import pytest

from novel_forge.engine.review import generate_and_review
from novel_forge.llm_client import LLMError


class Quality:
    generation_max_count = 3
    review_max_count = 2


def test_generation_loop_retries_llm_output_failures_with_generation_counter() -> None:
    """Invalid model output should consume generation attempts, not LLM transport retries."""
    calls: list[int] = []

    def generate_fn(_prompt: str, seed_offset: int) -> dict:
        calls.append(seed_offset)
        if len(calls) == 1:
            raise LLMError("JSON parse error: invalid output")
        return {"ok": True}

    result, review = generate_and_review(
        generate_fn=generate_fn,
        validate_fn=lambda _result: [],
        review_fn=lambda _result, _system: {"issues": []},
        revise_fn=lambda result, _review, _system, _seed_offset: result,
        system="sys",
        user_prompt="usr",
        kind="test_kind",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result == {"ok": True}
    assert review == {"issues": []}
    assert calls == [0, 1]


def test_generation_loop_raises_after_generation_count_llm_output_failures() -> None:
    """generation_max_count is the only counter for repeated invalid model output."""
    calls: list[int] = []

    def generate_fn(_prompt: str, seed_offset: int) -> dict:
        calls.append(seed_offset)
        raise LLMError("schema validation error: invalid output")

    with pytest.raises(RuntimeError, match="failed after 3 retries"):
        generate_and_review(
            generate_fn=generate_fn,
            validate_fn=lambda _result: [],
            review_fn=lambda _result, _system: {"issues": []},
            revise_fn=lambda result, _review, _system, _seed_offset: result,
            system="sys",
            user_prompt="usr",
            kind="test_kind",
            llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
            quality=Quality(),
        )

    assert calls == [0, 1, 2]


def test_review_loop_uses_publication_blocking_not_severity_for_revision() -> None:
    """Important non-blocking feedback should not consume a revision cycle."""
    revise_calls: list[dict] = []

    result, review = generate_and_review(
        generate_fn=lambda _prompt, _seed_offset: {"ok": True},
        validate_fn=lambda _result: [],
        review_fn=lambda _result, _system: {
            "issues": [
                {
                    "severity": "重要",
                    "field": "ターゲット読者",
                    "description": "主観的な磨き込み",
                    "suggestion": "より具体化する",
                    "before": "",
                    "after": "",
                    "publication_blocking": False,
                }
            ],
            "ready_for_publication": True,
        },
        revise_fn=lambda result, review, _system, _seed_offset: revise_calls.append(review) or result,
        system="sys",
        user_prompt="usr",
        kind="test_kind",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result == {"ok": True}
    assert review["issues"][0]["severity"] == "重要"
    assert revise_calls == []


def test_review_loop_revises_publication_blocking_issues() -> None:
    """Only publication_blocking=true feedback should force revision."""
    generated = [{"version": 1}, {"version": 2}]
    reviews = [
        {
            "issues": [
                {
                    "severity": "軽微",
                    "field": "logline",
                    "description": "後続工程で使えない矛盾",
                    "suggestion": "直す",
                    "before": "",
                    "after": "",
                    "publication_blocking": True,
                }
            ],
            "ready_for_publication": False,
        },
        {"issues": [], "ready_for_publication": True},
    ]

    def generate_fn(_prompt: str, seed_offset: int) -> dict:
        return generated[seed_offset]

    def review_fn(_result: dict, _system: str) -> dict:
        return reviews.pop(0)

    result, review = generate_and_review(
        generate_fn=generate_fn,
        validate_fn=lambda _result: [],
        review_fn=review_fn,
        revise_fn=lambda _result, _review, _system, _seed_offset: generated[1],
        system="sys",
        user_prompt="usr",
        kind="test_kind",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result == {"version": 2}
    assert review == {"issues": [], "ready_for_publication": True}


def test_review_loop_ignores_stale_resolved_issue() -> None:
    """Resolved before→after issues should not force another revision."""
    revise_calls: list[dict] = []

    result, review = generate_and_review(
        generate_fn=lambda _prompt, _seed_offset: {"title": "雨音と錆びた歯車の序曲"},
        validate_fn=lambda _result: [],
        review_fn=lambda _result, _system: {
            "issues": [
                {
                    "severity": "重要",
                    "field": "title",
                    "description": "簡体字が残っている",
                    "suggestion": "日本語表記に統一する",
                    "before": "雨音と錆びた齿轮の序曲",
                    "after": "雨音と錆びた歯車の序曲",
                    "publication_blocking": True,
                }
            ],
            "ready_for_publication": False,
        },
        revise_fn=lambda result, review, _system, _seed_offset: revise_calls.append(review) or result,
        system="sys",
        user_prompt="usr",
        kind="volume_design",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result == {"title": "雨音と錆びた歯車の序曲"}
    assert review == {"issues": [], "ready_for_publication": True}
    assert revise_calls == []
