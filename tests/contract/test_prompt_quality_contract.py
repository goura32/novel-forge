"""Prompt quality contract tests."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def test_scene_draft_prompt_contains_core_prose_quality_requirements() -> None:
    prompt = (PROMPTS_DIR / "scene_draft.md").read_text(encoding="utf-8")

    required_fragments = [
        "完成した小説本文のみ",
        "2000〜5000字",
        "常体",
        "冒頭1-2文",
        "Show Don't Tell",
        "POV",
        "感覚描写",
        "メタ説明",
        "シーン末尾",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


def test_review_prompts_define_publication_readiness_fields() -> None:
    review_prompts = sorted(PROMPTS_DIR.glob("*_review.md"))

    assert review_prompts, "expected review prompts"
    required_fragments = [
        "### 出版可否",
        "ready_for_publication=true",
        "ready_for_publication=false",
        "overall_assessment",
        "strengths",
        "publication_blocking",
    ]
    issues = {
        prompt.name: [fragment for fragment in required_fragments if fragment not in prompt.read_text(encoding="utf-8")]
        for prompt in review_prompts
    }
    issues = {name: missing for name, missing in issues.items() if missing}

    assert issues == {}


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


def test_generation_prompts_explain_hard_to_fill_required_fields() -> None:
    expectations = {
        "chapter_design.md": ["chapter_turning_point", "chapter_hook", "scenes[]", "foreshadowing_notes"],
        "scene_design.md": ["hook", "turning_point", "ending_hook", "key_events"],
        "series_plan_concept.md": ["world_rules", "selling_points", "target_audience"],
        "series_plan_characters.md": ["main_characters[]", "motivation", "flaw", "arc"],
        "series_plan_volumes.md": ["planned_volumes[]", "emotional_arc", "cliffhanger"],
        "volume_design.md": ["chapters[]", "title", "purpose"],
        "scene_summary_and_bible_update.md": ["facts[]", "subject", "predicate", "world_rules[]", "文字列の配列"],
        "kdp_metadata.md": ["title", "description", "keywords", "categories"],
        "cover_prompt.md": ["negative_prompt", "prompt", "画像生成ツール"],
    }

    issues = {}
    for filename, fragments in expectations.items():
        prompt = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        missing = [fragment for fragment in fragments if fragment not in prompt]
        if missing:
            issues[filename] = missing

    assert issues == {}


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
