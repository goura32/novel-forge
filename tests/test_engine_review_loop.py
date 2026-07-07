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


def test_review_loop_retries_review_llm_output_failures_without_revision() -> None:
    """Invalid review JSON should retry review generation, not revise content immediately."""
    review_calls = 0
    revise_calls = 0

    def review_fn(_result: dict, _system: str) -> dict:
        nonlocal review_calls
        review_calls += 1
        if review_calls == 1:
            raise LLMError("JSON parse error: invalid review output")
        return {"issues": []}

    def revise_fn(result: dict, _review: dict, _system: str, _seed_offset: int) -> dict:
        nonlocal revise_calls
        revise_calls += 1
        return result

    result, review = generate_and_review(
        generate_fn=lambda _prompt, _seed_offset: {"ok": True},
        validate_fn=lambda _result: [],
        review_fn=review_fn,
        revise_fn=revise_fn,
        system="sys",
        user_prompt="usr",
        kind="test_kind",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=type("Quality", (), {"generation_max_count": 3, "review_max_count": 3})(),
    )

    assert result == {"ok": True}
    assert review == {"issues": []}
    assert review_calls == 2
    assert revise_calls == 0


def test_review_loop_raises_after_review_llm_output_failure_limit() -> None:
    """Repeated invalid review JSON should stop at review_max_count."""
    review_calls = 0

    def review_fn(_result: dict, _system: str) -> dict:
        nonlocal review_calls
        review_calls += 1
        raise LLMError("JSON parse error: invalid review output")

    with pytest.raises(RuntimeError, match="review failed after 2 retries"):
        generate_and_review(
            generate_fn=lambda _prompt, _seed_offset: {"ok": True},
            validate_fn=lambda _result: [],
            review_fn=review_fn,
            revise_fn=lambda result, _review, _system, _seed_offset: result,
            system="sys",
            user_prompt="usr",
            kind="test_kind",
            llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
            quality=Quality(),
        )

    assert review_calls == 2


def test_review_loop_revises_any_actionable_issue() -> None:
    """Any emitted issue should consume a revision cycle."""
    revise_calls: list[dict] = []

    reviews: list[dict] = [
        {
            "issues": [
                {
                    "severity": "重要",
                    "field": "ターゲット読者",
                    "description": "主観的な磨き込み",
                    "suggestion": "より具体化する",
                    "before": "",
                    "after": "具体的な読者体験を明記する",
                }
            ],
        },
        {"issues": []},
    ]

    def revise_with_record(result: dict, review: dict, _system: str, _seed_offset: int) -> dict:
        revise_calls.append(review)
        return {**result, "revised": True}

    result, review = generate_and_review(
        generate_fn=lambda _prompt, _seed_offset: {"ok": True},
        validate_fn=lambda _result: [],
        review_fn=lambda _result, _system: reviews.pop(0),
        revise_fn=revise_with_record,
        system="sys",
        user_prompt="usr",
        kind="test_kind",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result == {"ok": True, "revised": True}
    assert review == {"issues": []}
    assert len(revise_calls) == 1


def test_review_loop_keeps_revising_current_result_without_regenerating() -> None:
    """Multiple review issues should revise the latest result, not restart from the original prompt."""
    generate_calls: list[int] = []
    revise_calls: list[tuple[int, dict]] = []
    reviews: list[dict] = [
        {
            "issues": [
                {
                    "severity": "重要",
                    "field": "field_a",
                    "description": "first issue",
                    "suggestion": "fix first",
                    "before": "OLD_AAA",
                    "after": "NEW_BBB",
                }
            ]
        },
        {
            "issues": [
                {
                    "severity": "重要",
                    "field": "field_b",
                    "description": "second issue",
                    "suggestion": "fix second",
                    "before": "OLD_CCC",
                    "after": "NEW_DDD",
                }
            ]
        },
        {"issues": []},
    ]

    def generate_fn(_prompt: str, seed_offset: int) -> dict:
        generate_calls.append(seed_offset)
        return {"stage": "generated", "seed_offset": seed_offset}

    def revise_fn(result: dict, _review: dict, _system: str, seed_offset: int) -> dict:
        revise_calls.append((seed_offset, result))
        return {"stage": "revised", "seed_offset": seed_offset, "previous": result}

    result, review = generate_and_review(
        generate_fn=generate_fn,
        validate_fn=lambda _result: [],
        review_fn=lambda _result, _system: reviews.pop(0),
        revise_fn=revise_fn,
        system="sys",
        user_prompt="usr",
        kind="test_kind",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=type("Quality", (), {"generation_max_count": 5, "review_max_count": 4})(),
    )

    assert generate_calls == [0]
    assert [seed for seed, _result in revise_calls] == [0, 1]
    assert revise_calls[1][1]["stage"] == "revised"
    assert result["stage"] == "revised"
    assert result["seed_offset"] == 1
    assert review == {"issues": []}


def test_review_loop_revises_issues() -> None:
    """Any issue should force revision."""
    generated = [{"version": 1}, {"version": 2}]
    reviews: list[dict] = [
        {
            "issues": [
                {
                    "severity": "軽微",
                    "field": "logline",
                    "description": "後続工程で使えない矛盾",
                    "suggestion": "直す",
                    "before": "",
                    "after": "後続工程で使える矛盾のない説明",
                }
            ],
        },
        {"issues": []},
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
    assert review == {"issues": []}


def test_review_loop_ignores_stale_resolved_issue() -> None:
    """Resolved before→after issues should not force another revision."""
    revise_calls: list[dict] = []

    def record_stale_revision(result: dict, review: dict, _system: str, _seed_offset: int) -> dict:
        revise_calls.append(review)
        return result

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
                }
            ],
        },
        revise_fn=record_stale_revision,
        system="sys",
        user_prompt="usr",
        kind="volume_design",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result == {"title": "雨音と錆びた歯車の序曲"}
    assert review == {"issues": []}
    assert revise_calls == []


def test_review_loop_ignores_noop_before_after_issue() -> None:
    """A blocking issue with identical before/after is not an actionable revision."""
    revise_calls: list[dict] = []

    def record_noop_revision(result: dict, review: dict, _system: str, _seed_offset: int) -> dict:
        revise_calls.append(review)
        return result

    result, review = generate_and_review(
        generate_fn=lambda _prompt, _seed_offset: {
            "goal": "連日続く梅雨を避け、神楽坂蓮は茶屋で静寂を取り戻す。"
        },
        validate_fn=lambda _result: [],
        review_fn=lambda _result, _system: {
            "issues": [
                {
                    "severity": "重要",
                    "field": "目標",
                    "description": "主人公名が誤っているという誤検知",
                    "suggestion": "キャラクター名を正しく修正する。",
                    "before": "神楽坂蓮は茶屋で静寂を取り戻す。",
                    "after": "神楽坂蓮は茶屋で静寂を取り戻す。",
                }
            ],
        },
        revise_fn=record_noop_revision,
        system="sys",
        user_prompt="usr",
        kind="scene_design",
        llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
        quality=Quality(),
    )

    assert result["goal"].startswith("連日続く梅雨")
    assert review == {"issues": []}


def test_review_loop_raises_when_blocking_issues_remain_at_review_limit() -> None:
    """A blocking issue at the review limit must stop the next phase."""
    review_calls = 0
    revise_calls: list[int] = []

    def review_fn(_result: dict, _system: str) -> dict:
        nonlocal review_calls
        review_calls += 1
        return {
            "issues": [
                {
                    "severity": "重要",
                    "field": "logline",
                    "description": "さらなる具体化要求",
                    "suggestion": "表現を磨く",
                    "before": f"v{review_calls}",
                    "after": f"v{review_calls + 1}",
                }
            ],
        }

    def revise_fn(result: dict, _review: dict, _system: str, seed_offset: int) -> dict:
        revise_calls.append(seed_offset)
        return {"version": result["version"] + 1}

    with pytest.raises(RuntimeError, match="revision needed but max count reached"):
        generate_and_review(
            generate_fn=lambda _prompt, _seed_offset: {"version": 1},
            validate_fn=lambda _result: [],
            review_fn=review_fn,
            revise_fn=revise_fn,
            system="sys",
            user_prompt="usr",
            kind="series_plan_concept",
            llm=type("LLM", (), {"_is_schema_echo": staticmethod(lambda _value: False)})(),
            quality=Quality(),
        )

    assert review_calls == 2
    assert revise_calls == [0]
