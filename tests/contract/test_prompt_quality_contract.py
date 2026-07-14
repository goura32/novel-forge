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


def test_scene_prompts_keep_existing_core_characters_out_of_scene_create() -> None:
    """A scene must refer to seed Core IDs, never recreate them by display name."""
    expected = {
        "design_scene_generate.md": [
            "`canon_context.characters` にいる人物",
            "`core` character は plan seed 専用",
        ],
        "design_scene_review.md": [
            "`canon_context.characters` にいる人物",
            "importance: \"core\"",
        ],
        "design_scene_revise.md": [
            "`canon_context.characters` にいる人物",
            "`core` は plan seed 専用",
        ],
    }
    missing = {
        filename: [
            fragment
            for fragment in fragments
            if fragment not in (PROMPTS_DIR / filename).read_text(encoding="utf-8")
        ]
        for filename, fragments in expected.items()
    }
    assert {filename: fragments for filename, fragments in missing.items() if fragments} == {}


def test_plan_review_never_emits_an_unactionable_empty_replacement() -> None:
    prompt = (PROMPTS_DIR / "plan_concept_review.md").read_text(encoding="utf-8")

    assert "空の `after`、`対象なし`、未定義の修正案を出さない" in prompt


def test_write_draft_revise_returns_both_title_and_content() -> None:
    prompt = (PROMPTS_DIR / "write_draft_revise.md").read_text(encoding="utf-8")
    assert "title" in prompt
    assert "content" in prompt
    assert "元の値" in prompt or "保持" in prompt


def test_write_draft_review_requires_core_issue_fields() -> None:
    prompt = (PROMPTS_DIR / "write_draft_review.md").read_text(encoding="utf-8")

    assert "各issueには必ず `severity`、`field`、`description`、`suggestion` を含める" in prompt
    assert "`before` / `after` は任意の補足" in prompt




def test_pnca_scene_prompts_require_completed_observable_beats() -> None:
    render = (PROMPTS_DIR / "pnca_scene_render.md").read_text(encoding="utf-8")
    revise = (PROMPTS_DIR / "pnca_scene_revise.md").read_text(encoding="utf-8")

    assert "準備・試行・直前で止めず" in render
    assert "未完の準備・試行・直前で終わらせない" in revise
    assert "Current draft.coverage.evidence[].draft_quote" in revise
    assert "一字も変更・削除・言い換えしてはならない" in revise
    assert "`constraint_kind` が `pov_fact` の場合は誤検出として維持してはならない" in revise
    assert "そのissueの `draft_quote` が本文に残っていないことを確認する" in revise


def test_pnca_draft_audit_keeps_pov_uncertainty_and_nonexclusive_end_state_out_of_blockers() -> None:
    audit = (PROMPTS_DIR / "pnca_draft_audit.md").read_text(encoding="utf-8")

    assert "瞳や髪の色" in audit
    assert "WriterView は直接観測できる感覚的詳細を一つずつ列挙する必要はない" in audit
    assert "POV人物の疑問、可能性の列挙、不確かな期待、主観的な解釈・印象は外部事実の断定ではない" in audit
    assert "指定された観測可能な終端状態が草稿内で実現しているかだけを審査する" in audit
    assert "明示的な禁止に反していなければならない" in audit
    assert "実在する混在語は必ず `language_contamination` / `blocker` にし" in audit
    assert "入力の WriterView に実在するJSON field pathを一字も変えずにcopyする" in audit


def test_pnca_writer_prompts_require_final_japanese_only_self_review() -> None:
    expected = "出力直前に `content` 全体を読み直し、台詞・独白・地の文のいずれにも日本語以外の単語・語法・文字種が一つも残っていないことを自分で確認してから返す"
    for prompt_name in ("pnca_scene_render.md", "pnca_scene_revise.md", "pnca_scene_rerender.md"):
        assert expected in (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")


def test_pnca_coverage_does_not_force_evidence_for_an_unproven_obligation() -> None:
    coverage = (PROMPTS_DIR / "pnca_scene_coverage.md").read_text(encoding="utf-8")

    assert "要求の一部だけに触れた文、近接する別の行為、主語や語句だけが似た文は証拠にしてはならない" in coverage
    assert "件数を埋める目的で無関係な `sentence_index` を出力してはならない" in coverage


def test_pnca_scene_render_forbids_omniscient_third_party_claims() -> None:
    render = (PROMPTS_DIR / "pnca_scene_render.md").read_text(encoding="utf-8")

    assert "第三者の感情・意図・評価・関係性を事実として断定しない" in render
    assert "見える表情や動作も、内面の証明にはしない" in render


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
        "入力キーワードまたは前工程JSONに明示された期間、職業、役割、性別、タイトル、ジャンル、固有名は正として扱い",
        "後続工程で具体化できる未定義要素",
        "自然なカタカナ語、英語表記、英字略語、一般的なジャンル語、固有名詞、日本語として成立する漢語は言語純度の問題にしない",
        "`issues` は最大8件に限定",
        "`description` と `suggestion` は短文にする",
        "二重引用符を書かない",
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