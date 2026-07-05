"""Prompt quality contract tests."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def test_scene_draft_prompt_contains_core_prose_quality_requirements() -> None:
    prompt = (PROMPTS_DIR / "scene_draft.md").read_text(encoding="utf-8")

    required_fragments = [
        "冒頭1-2文",
        "Show Don't Tell",
        "POV",
        "感覚描写",
        "メタ説明",
        "シーン末尾",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []
