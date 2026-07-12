"""Prompt quality contract tests."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "novel_forge" / "resources" / "prompts"


def test_scene_draft_prompt_contains_core_prose_quality_requirements() -> None:
    prompt = (PROMPTS_DIR / "write_draft_generate.md").read_text(encoding="utf-8")

    required_fragments = [
        "完成",
        "POV",
        "メタ注釈",
        "continuity handoff",
        "スキーマ",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


def test_scene_design_review_is_grounded_in_the_assigned_scene_seed() -> None:
    prompt = (PROMPTS_DIR / "design_scene_review.md").read_text(encoding="utf-8")

    required_fragments = [
        "### シーン種",
        "{scene_seed}",
        "Canonにある関係、伏線、世界ルール、人物、場所が候補に登場しないことだけを issue にしない",
        "可能性だけで issue にしない",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


def test_plan_review_never_emits_an_unactionable_empty_replacement() -> None:
    prompt = (PROMPTS_DIR / "plan_concept_review.md").read_text(encoding="utf-8")

    assert "空の `after`、`対象なし`、未定義の修正案を出さない" in prompt


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
    revision_prompts = sorted(PROMPTS_DIR.glob("*_revise.md"))

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


def test_volume_design_preserves_given_title_exactly() -> None:
    prompt = (PROMPTS_DIR / "design_volume_generate.md").read_text(encoding="utf-8")

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
        "レビュー対象に根拠があり、改訂工程で具体的に修正できる問題に限定",
        "severity は後続工程への影響度で決める",
        "軽微に見える表記・用語でも、後続工程で固定化・拡散する場合は指摘する",
        "修正可能な差分に限定",
        "出版可否、総評、長所、スコア",
        "`issues` が空配列なら改訂不要、1件以上なら改訂を継続",
        "問題がない場合は、無理に指摘を作らず `issues` を空配列にする。",
        "`before` には入力JSON内の実際の値だけを書く",
        "入力キーワードまたは前工程JSONに明示された期間、職業、役割、性別、タイトル、ジャンル、固有名は正として扱い",
        "後続工程で具体化できる未定義要素",
        "自然なカタカナ語、英語表記、英字略語、一般的なジャンル語、固有名詞、日本語として成立する漢語は言語純度の問題にしない",
        "`issues` は最大8件に限定",
        "`description` と `suggestion` は短文にする",
        "二重引用符を書かない",
        "`after` は1つの完成値だけを書く",
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


def test_generation_prompts_explain_hard_to_fill_required_fields() -> None:
    expectations = {
        "design_chapter_generate.md": ["chapter_turning_point", "chapter_hook", "scenes[]", "foreshadowing_notes"],
        "design_scene_generate.md": ["hook", "turning_point", "ending_hook", "key_events"],
        "plan_concept_generate.md": ["world_rules", "selling_points", "target_audience"],
        "design_volume_generate.md": ["chapters[]", "title", "purpose"],
    }

    issues = {}
    for filename, fragments in expectations.items():
        prompt = (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        missing = [fragment for fragment in fragments if fragment not in prompt]
        if missing:
            issues[filename] = missing

    assert issues == {}


def test_series_plan_concept_prompts_guard_raw_run_failures() -> None:
    prompts = [
        PROMPTS_DIR / "plan_concept_generate.md",
    ]

    required_fragments = [
        "不自然な英語・簡体字・ハングル等を混在させない",
        "簡体字・中国語表現・不自然な外来語",
        "logline は要素の羅列にしない",
        "中心課題を1つに絞り",
        "能動的な行動目標",
        "読者層、ジャンル期待、感情濃度、緊張感、対象年齢を矛盾させない",
        "slug はローマ字ならローマ字で統一",
        "英単語を混在させない",
        "主要語3〜6個程度",
    ]
    issues = {}
    for prompt in prompts:
        text = prompt.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            issues[prompt.name] = missing

    assert issues == {}


def test_all_review_prompts_must_flag_non_japanese_contamination() -> None:
    review_prompts = sorted(PROMPTS_DIR.glob("*_review.md"))
    assert review_prompts, "expected review prompts"

    required_fragments = [
        "日本語文脈で不自然な簡体字、中国語構文、英語混在、ハングル混在を指摘する",
        "指摘時は問題文字列を引用する",
        "自然なカタカナ語、英語表記、英字略語、一般的なジャンル語、固有名詞、日本語として成立する漢語は問題にしない",
    ]

    issues = {}
    for prompt_path in review_prompts:
        text = prompt_path.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            issues[prompt_path.name] = missing

    assert issues == {}