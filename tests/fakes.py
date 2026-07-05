"""Shared test doubles for NovelForge tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast


class MockLLMClient:
    """Mock LLM client for tests that need to control LLM responses.

    Uses kind-matching: each request finds the next entry with matching kind,
    regardless of position in the sequence. This makes tests resilient to
    internal call order changes.
    """

    def __init__(self, responses: dict[str, Any] | None = None):
        self._responses = responses or {}
        self._call_log: list[tuple[str, str]] = []
        self._call_count = 0
        self._sequence: list[tuple[str, Any]] = []
        self._seq_idx = 0

    def add_sequence(self, kind: str, response: Any) -> None:
        """Add a response to the sequential response queue."""
        self._sequence.append((kind, response))

    def add_batch(self, *items: tuple[str, Any]) -> None:
        """Add multiple (kind, response) pairs at once."""
        for kind, response in items:
            self._sequence.append((kind, response))

    def add_repeated(self, kind: str, response: Any, count: int) -> None:
        """Add fresh deep-copied responses for repeated calls."""
        for _ in range(count):
            self._sequence.append((kind, deepcopy(response)))

    def complete_json(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
        seed_offset: int = 0,
    ) -> dict[str, Any]:
        self._call_count += 1
        self._call_log.append((kind, user_prompt))

        lookup_kind = kind
        if kind == "review":
            for expected_kind, _resp in self._sequence[self._seq_idx:]:
                if expected_kind.endswith("_review") or expected_kind.endswith("_revision"):
                    lookup_kind = expected_kind
                    break

        for i in range(self._seq_idx, len(self._sequence)):
            expected_kind, resp = self._sequence[i]
            if expected_kind == lookup_kind:
                self._seq_idx = i + 1
                if isinstance(resp, dict) and (kind == "review" or lookup_kind.endswith("_review")):
                    resp = {
                        "ready_for_publication": len(resp.get("issues", [])) == 0,
                        "overall_assessment": "テスト用レビュー結果です。",
                        "strengths": [],
                        **resp,
                    }
                return cast(dict[str, Any], resp)

        raise RuntimeError(f"No response for kind={kind} (looked up as {lookup_kind})")

    @staticmethod
    def _is_schema_echo(parsed: dict[str, Any]) -> bool:
        """Check if parsed response is just the JSON schema echoed back."""
        return False
