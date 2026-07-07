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


def test_prompts_do_not_use_ok_ng_examples() -> None:
    forbidden_fragments = [
        "OK例",
        "NG例",
        "良い例",
        "悪い例",
        "### 例",
        "## 例",
    ]
    issues = {}
    for prompt_path in sorted(PROMPTS_DIR.glob("*.md")):
        text = prompt_path.read_text(encoding="utf-8")
        found = [fragment for fragment in forbidden_fragments if fragment in text]
        if found:
            issues[prompt_path.name] = found

    assert issues == {}


def test_revision_prompts_preserve_unmentioned_fields() -> None:
    revision_prompts = sorted(PROMPTS_DIR.glob("*_revision.md"))

    assert revision_prompts, "expected revision prompts"
    required_fragments = [
        "`issues[].field` に関係しないフィールドは原則として元の値を保持",
        "整合性調整が必要な場合だけ、最小限変更",
        "明示的な指摘がない限り変更しない",
    ]
    issues = {}
    for prompt_path in revision_prompts:
        text = prompt_path.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            issues[prompt_path.name] = missing

    assert issues == {}


def test_scene_summary_bible_update_forbids_inference() -> None:
    prompt = (PROMPTS_DIR / "scene_summary_and_bible_update.md").read_text(encoding="utf-8")

    required_fragments = [
        "本文に明示されていない過去設定、能力、関係性、世界ルールを推測で追加しない",
        "比喩表現や登場人物の主観を、客観的事実として Bible に登録しない",
        "一時的な感情や誤解は、恒久的な関係性変化として扱わない",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


def test_volume_design_preserves_given_title_exactly() -> None:
    prompt = (PROMPTS_DIR / "volume_design.md").read_text(encoding="utf-8")

    required_fragments = [
        "入力の「既定巻タイトル」と完全一致",
        "表記ゆれ、装飾、サブタイトル追加、言い換えをしない",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


def test_review_prompts_emit_only_actionable_issues() -> None:
    review_prompts = sorted(PROMPTS_DIR.glob("*_review.md"))

    assert review_prompts, "expected review prompts"
    required_fragments = [
        "### 指摘対象",
        "改訂工程がそのまま使える指摘事項だけ",
        "修正可能な差分に限定",
        "出版可否、総評、長所、スコア",
        "`issues` が空配列なら改訂不要、1件以上なら改訂を継続",
        "問題がない場合は、無理に指摘を作らず `issues` を空配列にする。",
    ]
    forbidden_fragments = [
        "### 出版可否",
        "ready_for_publication",
        "overall_assessment",
        "strengths",
        "publication_blocking",
        "publication_blocking=false",
    ]
    issues = {}
    for prompt in review_prompts:
        text = prompt.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        forbidden = [fragment for fragment in forbidden_fragments if fragment in text]
        if missing or forbidden:
            issues[prompt.name] = {"missing": missing, "forbidden": forbidden}

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
