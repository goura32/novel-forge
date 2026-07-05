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
