"""Prompt quality contract tests."""

from __future__ import annotations

from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "novel_forge" / "resources" / "prompts"


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


def test_concept_review_does_not_over_specify_design_details() -> None:
    text = (PROMPTS_DIR / "series_plan_concept_review.md").read_text(encoding="utf-8")

    required_fragments = [
        "人物の詳細設定、逃走・追跡ギミックの運用細部は重要指摘にしない",
        "人物の詳細な職能、関係性の細部、具体的な作戦手順、専門技術、場面単位の実行方法は Character/Design 工程で具体化できる",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in text]
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


def test_series_plan_volumes_guards_against_raw_run_failures() -> None:
    generation = (PROMPTS_DIR / "series_plan_volumes.md").read_text(encoding="utf-8")
    review = (PROMPTS_DIR / "series_plan_volumes_review.md").read_text(encoding="utf-8")

    generation_fragments = [
        "自然な日本語だけで書く",
        "日本語文脈で不自然な簡体字、中国語構文、英語混在、ハングル混在",
        "具体的な出来事として書く",
    ]
    review_fragments = [
        "章タイトルの表記ゆれだけを致命的・重要な問題にしない",
        "key_events に抽象テーマだけが置かれている場合",
    ]

    assert [fragment for fragment in generation_fragments if fragment not in generation] == []
    assert [fragment for fragment in review_fragments if fragment not in review] == []


def test_generation_prompts_explain_hard_to_fill_required_fields() -> None:
    expectations = {
        "chapter_design.md": ["chapter_turning_point", "chapter_hook", "scenes[]", "foreshadowing_notes"],
        "scene_design.md": ["hook", "turning_point", "ending_hook", "key_events"],
        "series_plan_concept.md": ["world_rules", "selling_points", "target_audience"],
        "series_plan_characters.md": ["main_characters[]", "motivation", "flaw", "arc"],
        "series_plan_characters_review.md": ["役割ラベル・分類名・固有識別子", "結末や報復方法の好み", "成長弧や動機は、文字列がほぼ同一"],
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


def test_series_plan_concept_prompts_require_japanese_punctuation() -> None:
    prompts = [
        PROMPTS_DIR / "series_plan_concept.md",
        PROMPTS_DIR / "series_plan_concept_revision.md",
    ]

    required_fragments = [
        "日本語の句読点「、」「。」で文を区切り",
        "1文を長くしすぎない",
        "複数要素を詰め込まず",
    ]
    issues = {}
    for prompt in prompts:
        text = prompt.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            issues[prompt.name] = missing

    assert issues == {}


def test_series_plan_concept_prompts_keep_core_magic_mechanism_coherent() -> None:
    prompts = [
        PROMPTS_DIR / "series_plan_concept.md",
        PROMPTS_DIR / "series_plan_concept_revision.md",
    ]

    required_fragments = [
        "中核ギミックや独自ルール",
        "同じ現象を複数の別ルールで説明しない",
        "発動条件",
        "直接の効果",
        "解除または緩和条件",
        "入力キーワードで指定された中核ギミックの型は途中で変えない",
        "不可逆・絶対条件",
        "未定義の新リスクや新儀式",
        "入力キーワードに明示されていない場合",
        "重い不可逆ルールを勝手に追加しない",
        "入力ジャンルの物語を進めやすい制約を優先する",
    ]
    issues = {}
    for prompt in prompts:
        text = prompt.read_text(encoding="utf-8")
        missing = [fragment for fragment in required_fragments if fragment not in text]
        if missing:
            issues[prompt.name] = missing

    assert issues == {}

def test_series_plan_concept_prompts_guard_raw_run_failures() -> None:
    prompts = [
        PROMPTS_DIR / "series_plan_concept.md",
        PROMPTS_DIR / "series_plan_concept_revision.md",
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


def test_series_plan_concept_review_must_flag_non_japanese_contamination() -> None:
    prompt = (PROMPTS_DIR / "series_plan_concept_review.md").read_text(encoding="utf-8")

    required_fragments = [
        "日本語文脈で不自然な簡体字、中国語構文、英語混在、ハングル混在を指摘する",
        "指摘時は問題文字列を引用する",
        "日本語として成立する漢語は問題にしない",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []


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


def test_series_plan_concept_review_must_preserve_swap_gimmick() -> None:
    prompt = (PROMPTS_DIR / "series_plan_concept_review.md").read_text(encoding="utf-8")

    required_fragments = [
        "入力キーワードまたはタイトルに中核ギミックが含まれる場合",
        "何が、誰に、どの範囲で、どの条件で変化・交換・喪失・制限されるのか",
        "別種のギミックへ置き換わっている場合は重要指摘",
        "`after` でも元のギミックの型を保持",
    ]

    missing = [fragment for fragment in required_fragments if fragment not in prompt]
    assert missing == []
