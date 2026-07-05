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


def test_series_plan_volumes_requires_non_empty_final_volume_hook() -> None:
    prompt = (PROMPTS_DIR / "series_plan_volumes.md").read_text(encoding="utf-8")

    required_fragments = [
        "最終巻",
        "非空",
        "余韻",
        "未来へのフック",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


def test_series_plan_characters_revision_preserves_real_character_array() -> None:
    prompt = (PROMPTS_DIR / "series_plan_characters_revision.md").read_text(encoding="utf-8")

    required_fragments = [
        "main_characters は必ず配列",
        "既存の人数",
        "スキーマ定義",
        "出力しない",
        "arc フィールド",
    ]
    forbidden_fragments = ["growth フィールド"]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    forbidden = [fragment for fragment in forbidden_fragments if fragment in prompt]
    assert missing == []
    assert forbidden == []
