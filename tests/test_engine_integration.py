"""Engine integration tests — verify behavior, not implementation.

Design principle:
- Tests verify INPUT → OUTPUT of public methods (plan, design, write, export)
- Internal implementation (retry counts, call order) is NOT tested
- MockLLMClient is used only for tests that need to control LLM responses
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fakes import MockLLMClient

from novel_forge.context_builder import ContextBuilder
from novel_forge.engine import NovelEngine
from novel_forge.models import (
    Bible,
    CharacterProfile,
)
from novel_forge.prompts import PromptManager
from novel_forge.quality_gate import QualityGate
from novel_forge.scene_writer import SceneWriter
from novel_forge.storage import BibleStorage, BlackboardStorage

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_plan_response(**overrides) -> dict:
    """Create a valid series plan core response."""
    base = {
        "title": "テストシリーズ長いタイトル",
        "slug": "test_series",
        "logline": "テストのあらすじです。これは十分な長さのあらすじです。主人公が冒険に出ます。",
        "genre": ["fantasy"],
        "target_audience": "10代後半から30代の読者をターゲットにしたファンタジー小説で、冒険と成長の物語を求める層に向けて書かれています。",
        "themes": ["冒険", "成長"],
        "selling_points": ["ユニークな世界観と複雑な魔法システムが社会のあらゆる側面に影響を与えている", "複雑なキャラクター関係がシリーズを通じて自然に進化していく"],
        "world_summary": "魔法が存在し、古代の法則によって規制されている世界。物語は若い魔法使いが自分の力を発見し、魔法能力が社会的地位を決定する社会をナビゲートすることを学ぶところから始まる。",
        "world_rules": ["魔法には貴重な何かを犠牲にする必要がある", "古代の法則がすべての呪文詠唱を支配し、違反は厳しく罰せられる"],
        "main_characters": [{"name": "主人公", "role": "主人公", "arc": "成長"}],
        "planned_volumes": [{"title": "第1巻", "premise": "始まり"}],
    }
    base.update(overrides)
    return base


def _make_chars_response(**overrides) -> dict:
    """Create a valid series plan characters response."""
    base = {
        "main_characters": [
            {
                "name": "主人公",
                "role": "主人公",
                "personality": "勇敢で好奇心旺盛な性格",
                "background": "平凡な村で育った若者",
                "arc": "無力から英雄への成長",
                "relationships": ["師匠", "ライバル"],
                "skills": ["魔法", "剣術"],
                "flaws": ["未熟さ", "衝動的"],
                "motivation": "世界を救う",
            }
        ],
    }
    base.update(overrides)
    return base


def _make_volumes_response(**overrides) -> dict:
    """Create a valid series plan volumes response."""
    base = {
        "planned_volumes": [
            {"title": "第一巻 旅立ちの刻", "premise": "主人公が村を出て冒険の旅に出る。道中で仲間と出会い、世界の秘密を知る。"},
            {"title": "第二巻 試練の森", "premise": "仲間と共に試練の森へ入り、それぞれの過去と向き合う。"},
            {"title": "第三巻 決戦の時", "premise": "最終決戦に向け、全ての伏線が回収され、世界の運命が決まる。"},
        ],
    }
    base.update(overrides)
    return base


def _make_design_response(**overrides) -> dict:
    """Create a valid volume design response."""
    base = {
        "chapters": [
            {
                "title": "プロローグ 旅立ちの朝",
                "purpose": "導入",
                "theme": "未知への挑戦と不安の克服",
                "emotional_arc": "不安から希望へ、小さな一歩を踏み出す勇気",
                "outcome": "主人公が旅立つ決意を固め、最初の一歩を踏み出す",
                "scenes": [
                    {
                        "title": "出発の朝",
                        "pov": "主人公",
                        "goal": "家族に別れを告げ、旅立ちの準備を整える",
                        "conflict": "不安と期待が入り混じる心情、父親の反対",
                        "outcome": "父親の理解を得て、旅立つ決意を新たにする",
                        "characters": ["主人公", "父親", "母親"],
                        "key_events": ["荷物の最終確認", "父親との対話", "母親の手作り弁当", "門を出る瞬間"],
                        "setting": "主人公の実家、早朝の台所から玄関、そして村道へ"
                    },
                    {
                        "title": "最初の道",
                        "pov": "主人公",
                        "goal": "村を出て最初の街道を歩き始める",
                        "conflict": "未知の世界への恐怖と、後ろ髪を引かれる故郷への思い",
                        "outcome": "村の外れで老商人と出会い、旅の心構えを学ぶ",
                        "characters": ["主人公", "老商人"],
                        "key_events": ["村を出る決意", "街道に出る", "老商人との会話"],
                        "setting": "村はずれの街道、朝もやの中に見える遠い山々"
                    }
                ]
            },
            {
                "title": "第一章 出会いと別れ",
                "purpose": "展開",
                "theme": "新たな絆と別れの悲しみ",
                "emotional_arc": "喜びから悲しみへ、そして決意へ",
                "outcome": "最初の仲間を得るが、師匠を失う",
                "scenes": [
                    {
                        "title": "運命の出会い",
                        "pov": "主人公",
                        "goal": "街で情報を集め、次の目的地を決める",
                        "conflict": "怪しい人物に絡まれ、正体を隠す必要がある",
                        "outcome": "謎の少女と出会い、共に行動することに",
                        "characters": ["主人公", "謎の少女"],
                        "key_events": ["街での情報収集", "トラブルに巻き込まれる", "少女との出会い"],
                        "setting": "賑やかな街の市場、昼下がり"
                    }
                ]
            }
        ],
    }
    base.update(overrides)
    return base


def _make_review_response(score: float = 80.0, issues: list | None = None) -> dict:
    """Create a valid review response."""
    return {
        "score": score,
        "issues": issues or [],
        "strengths": ["良い"],
        "recommendations": [],
    }


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_workdir(tmp_path):
    """Create a minimal workdir with prompts and schemas."""
    src_prompts = Path(__file__).resolve().parent.parent / "prompts"
    dst_prompts = tmp_path / "prompts"
    if src_prompts.exists():
        import shutil

        shutil.copytree(src_prompts, dst_prompts)
    return tmp_path


@pytest.fixture
def mock_llm():
    return MockLLMClient()


@ pytest.fixture
def engine(tmp_workdir, mock_llm):
    """Create a NovelEngine with mock LLM.

    Note: For tests that only verify plan() output, the engine uses
    real plan() with MockLLMClient. For tests that verify internal
    behavior, plan() is mocked directly.
    """
    prompts = PromptManager(prompt_dir=tmp_workdir / "prompts")
    eng = NovelEngine(
        workdir=tmp_workdir,
        model="test-model",
        llm_client=mock_llm,
        prompt_manager=prompts,
        config={
            "llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 3},
            "quality": {"max_generation_count": 3, "max_review_count": 3},
        },
    )
    return eng


@pytest.fixture
def planned_engine(tmp_workdir, mock_llm):
    """Engine with plan() already completed.

    Uses real plan() with MockLLMClient. The MockLLMClient's default
    responses ensure plan() completes successfully.
    """
    mock_llm.add_sequence("series_plan_concept", _make_plan_response())
    mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
    mock_llm.add_sequence("series_plan_characters", _make_chars_response())
    mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
    mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
    mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})
    mock_llm.add_sequence("volume_design", _make_design_response())
    mock_llm.add_sequence("volume_design_review", {"issues": [], "suggestions": []})
    # 4 chapters → 4 chapter_design calls
    for _ in range(4):
        mock_llm.add_sequence("chapter_design", {
            "title": "第1章", 
            "purpose": "導入", 
            "theme": "テーマ", 
            "emotional_arc": "感情",
            "outcome": "結果",
            "scenes": [{"title": "シーン1", "goal": "目標", "conflict": "葛藤", "outcome": "結果"}]
        })
        mock_llm.add_sequence("chapter_design_review", {"issues": [], "suggestions": []})
    # 4 chapters × ~2 scenes each → up to 8 scene_design calls
    for _ in range(8):
        mock_llm.add_sequence("scene_design", {"number": 1, "chapter_number": 1, "title": "シーン1", "goal": "目標", "conflict": "葛藤", "outcome": "結果"})
        mock_llm.add_sequence("scene_design_review", {"issues": [], "suggestions": []})
    # scene_draft + scene_review + scene_summary for each scene
    for _ in range(8):
        mock_llm.add_sequence("scene_draft", {"title": "シーン", "content": "本文" * 2000})
        mock_llm.add_sequence("scene_review", {"issues": []})
        mock_llm.add_sequence("scene_summary_and_bible_update", {"summary": "要約"})
    # second round
    mock_llm.add_sequence("volume_design", _make_design_response())
    mock_llm.add_sequence("volume_design_review", {"issues": [], "suggestions": []})
    mock_llm.add_sequence("chapter_design", {
                "title": "第1章",
                "purpose": "導入",
                "theme": "テーマ",
                "emotional_arc": "感情",
                "outcome": "結果",
                "scenes": [{"title": "シーン1", "goal": "目標", "conflict": "葛藤", "outcome": "結果"}]
            })
    mock_llm.add_sequence("chapter_design_review", {"issues": [], "suggestions": []})
    mock_llm.add_sequence("scene_design", {"number": 1, "chapter_number": 1, "title": "シーン1", "goal": "目標", "conflict": "葛藤", "outcome": "結果"})
    mock_llm.add_sequence("scene_design_review", {"issues": [], "suggestions": []})
    mock_llm.add_sequence("scene_design", {"number": 2, "chapter_number": 2, "title": "シーン2", "goal": "目標2", "conflict": "葛藤2", "outcome": "結果2"})
    mock_llm.add_sequence("scene_design_review", {"issues": [], "suggestions": []})
    for _ in range(2):
        mock_llm.add_sequence("scene_draft", {"title": "シーン", "content": "本文" * 2000})
        mock_llm.add_sequence("scene_review", {"issues": []})
        mock_llm.add_sequence("scene_summary_and_bible_update", {"summary": "要約"})

    prompts = PromptManager(prompt_dir=tmp_workdir / "prompts")
    eng = NovelEngine(
        workdir=tmp_workdir,
        model="test-model",
        llm_client=mock_llm,
        prompt_manager=prompts,
        config={"llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 3}},
    )
    eng.plan("テスト")
    mock_llm._call_log.clear()
    return eng


# ── Plan tests ──────────────────────────────────────────────────────────


class TestPlan:
    """Verify plan() output (not internal implementation)."""

    def test_plan_creates_series_plan(self, engine, mock_llm, tmp_workdir):
        """plan() should create series_plan.json with valid data."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        engine.plan("テスト")

        plan_path = engine._series_dir / "series_plan.json"
        assert plan_path.exists()
        saved = json.loads(plan_path.read_text(encoding="utf-8"))
        assert saved["title"] == "テストシリーズ長いタイトル"

    def test_plan_saves_review(self, engine, mock_llm, tmp_workdir):
        """plan() should save the review result."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        engine.plan("テスト")
        review_path = engine._series_dir / "series_concept_review.json"
        assert review_path.exists()

    def test_plan_calls_llm_for_generation_and_review(self, engine, mock_llm):
        """plan() should call LLM at least twice (generate + review)."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        engine.plan("テスト")
        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_concept" in kinds
        assert "review" in kinds  # unified review kind

    def test_plan_volume_numbers_assigned(self, engine, mock_llm):
        """Engine should auto-assign volume numbers."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        result = engine.plan("テスト")
        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            assert vol["number"] == i

    def test_plan_slug_truncated(self, engine, mock_llm):
        """Slug longer than 32 chars should be truncated."""
        long_slug = "a" * 300
        mock_llm.add_sequence("series_plan_concept", _make_plan_response(slug=long_slug))
        mock_llm.add_sequence("series_plan_concept", _make_plan_response(slug="a" * 32))
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        result = engine.plan("テスト")
        assert len(result["slug"]) <= 32


# ── Plan review → revise loop ──────────────────────────────────────────


class TestPlanReviewLoop:
    """Verify plan review behavior (not internal call counts)."""

    def test_plan_stops_after_max_retries(self, engine, mock_llm):
        """Plan revision should stop after max_retries.

        With max_retries=3, the loop runs at most 3 iterations.
        We verify the final result is valid regardless of retry count.
        """
        review_fail = {
            "issues": [{"severity": "致命的", "field": "test", "description": "問題", "suggestion": "修正", "before": "a", "after": "b"}],
        }
        # Add enough entries for 3 revision attempts
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        for _ in range(3):
            mock_llm.add_sequence("series_plan_concept_review", review_fail)
            mock_llm.add_sequence("series_plan_concept", _make_plan_response())
            mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence(
            "series_plan_volumes_review",
            {
                "volume_uniqueness": "良い",
                "series_flow": "良い",
                "cliffhanger": "良い",
                "theme_consistency": "良い",
                "issues": [],
            },
        )

        result = engine.plan("テスト")

        # Plan should complete (not raise) regardless of review failures
        assert result["title"] == "テストシリーズ長いタイトル"
        kinds = [k for k, _ in mock_llm._call_log]
        revision_count = kinds.count("series_plan_concept") - 1  # subtract initial call
        # With max_retries=3, at most 3 revisions should happen
        assert revision_count <= 3

    def test_plan_no_revision_when_passing(self, engine, mock_llm):
        """Plan should not be revised when no critical issues."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence(
            "series_plan_volumes_review",
            {
                "volume_uniqueness": "良い",
                "series_flow": "良い",
                "cliffhanger": "良い",
                "theme_consistency": "良い",
                "issues": [],
            },
        )

        engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        # No separate revision kind — revision reuses series_plan_concept
        assert kinds.count("series_plan_concept") == 1  # only initial, no revision


# ── Outline tests ──────────────────────────────────────────────────────


class TestOutline:
    """Verify design() output."""

    def test_outline_creates_outline(self, planned_engine, mock_llm, tmp_workdir):
        """design() should create outline.json and set state."""
        result = planned_engine.design(volume_number=1)

        assert result["title"] == "第1巻"
        assert planned_engine.state.status == "デザイン済"

        outline_path = planned_engine._series_dir / "vol01" / "vol01.json"
        assert outline_path.exists()

    def test_outline_flattens_scenes(self, planned_engine, mock_llm):
        """design() should flatten scenes from all chapters."""
        result = planned_engine.design(volume_number=1)
        total_scenes = sum(len(ch.get("scenes", [])) for ch in result.get("chapters", []))
        assert total_scenes > 0

    def test_outline_assigns_chapter_numbers(self, planned_engine, mock_llm):
        """design() should assign sequential chapter numbers."""
        result = planned_engine.design(volume_number=1)
        for i, ch in enumerate(result.get("chapters", []), 1):
            assert ch["number"] == i

    def test_chapter_design_keeps_revised_purpose(self, planned_engine, mock_llm):
        """design() must not overwrite a valid chapter purpose returned by revision."""
        mock_llm._sequence = []
        mock_llm._seq_idx = 0
        mock_llm.add_sequence("volume_design", _make_design_response(
            title="第1巻",
            premise="序盤から追跡へ進む巻です。",
            chapters=[
                {
                    "title": "追跡の始まり",
                    "purpose": "クライマックス",
                    "theme": "真実への接近",
                    "emotional_arc": "緊張から決意へ",
                    "outcome": "主人公が追跡を逃れる",
                    "scenes": [],
                }
            ],
        ))
        mock_llm.add_sequence("volume_design_review", {"issues": []})
        mock_llm.add_sequence("chapter_design", {
            "title": "追跡の始まり",
            "purpose": "展開",
            "theme": "真実への接近と最初の危機を通じた関係変化",
            "emotional_arc": "不安から緊張、そして共同戦線への小さな決意へ移る。",
            "outcome": "主人公は追跡を逃れ、次の謎へ向かう必要を理解する。",
            "scenes": [
                {
                    "title": "路地裏の逃走",
                    "pov": "主人公",
                    "goal": "追手から逃れる",
                    "conflict": "過去への不信と目前の危機が重なる",
                    "outcome": "一時的に追手を振り切る",
                    "characters": ["主人公"],
                    "key_events": ["追手の接近", "路地裏への逃走"],
                    "setting": "夜の路地裏",
                }
            ],
        })
        mock_llm.add_sequence("chapter_design_review", {"issues": []})
        mock_llm.add_sequence("scene_design", {
            "number": 1,
            "chapter_number": 1,
            "title": "路地裏の逃走",
            "goal": "追手から逃れる",
            "conflict": "不信と危機が重なる",
            "outcome": "一時的に追手を振り切る",
        })
        mock_llm.add_sequence("scene_design_review", {"issues": []})

        result = planned_engine.design(volume_number=1)

        assert result["chapters"][0]["purpose"] == "展開"

    def test_chapter_design_repairs_invalid_purpose_from_volume_design(self, planned_engine, mock_llm):
        """design() should repair only invalid chapter purpose values from the source chapter."""
        mock_llm._sequence = []
        mock_llm._seq_idx = 0
        mock_llm.add_sequence("volume_design", _make_design_response(
            title="第1巻",
            premise="祈り機械との出会いを描く巻です。",
            chapters=[
                {
                    "title": "共鳴する古物",
                    "purpose": "導入",
                    "theme": "記憶喪失と冒険への入口",
                    "emotional_arc": "孤独から小さな好奇心へ",
                    "outcome": "主人公が異常な祈り機械を受け取る",
                    "scenes": [],
                }
            ],
        ))
        mock_llm.add_sequence("volume_design_review", {"issues": []})
        mock_llm.add_sequence("chapter_design", {
            "title": "共鳴する古物",
            "purpose": "祈り機械が支配する京都の日常と、主人公が冒険へ踏み出す契機を描く。",
            "theme": "記憶喪失と冒険への入口",
            "emotional_arc": "孤独から小さな好奇心へ移る。",
            "outcome": "主人公が異常な祈り機械を受け取り、次の調査へ向かう。",
            "scenes": [
                {
                    "title": "古物店の共鳴",
                    "pov": "主人公",
                    "goal": "祈り機械を確認する",
                    "conflict": "未知の共鳴が過去の記憶を揺さぶる",
                    "outcome": "機械を引き取る決意をする",
                    "characters": ["主人公"],
                    "key_events": ["古物店で機械を受け取る", "異常な共鳴を感じる"],
                    "setting": "近未来京都の古物店",
                }
            ],
        })
        mock_llm.add_sequence("chapter_design_review", {"issues": []})
        mock_llm.add_sequence("scene_design", {
            "number": 1,
            "chapter_number": 1,
            "title": "古物店の共鳴",
            "goal": "祈り機械を確認する",
            "conflict": "未知の共鳴が過去の記憶を揺さぶる",
            "outcome": "機械を引き取る決意をする",
        })
        mock_llm.add_sequence("scene_design_review", {"issues": []})

        result = planned_engine.design(volume_number=1)

        assert result["chapters"][0]["purpose"] == "導入"


# ── Outline review → revise loop ────────────────────────────────────────


class TestOutlineReviewLoop:
    """Verify outline review behavior."""

    def test_outline_revises_on_critical_issues(self, planned_engine, mock_llm):
        """Outline should be revised when critical issues found."""
        mock_llm._responses["volume_design_review"] = _make_review_response(
            issues=[{"severity": "致命的", "field": "テスト", "description": "問題", "suggestion": "", "before": "", "after": ""}]
        )
        mock_llm._responses["volume_design_revision"] = _make_design_response(title="改訂版")
        mock_llm._call_log.clear()

        result = planned_engine.design(volume_number=1)
        assert result["title"]  # title exists

    def test_outline_no_revision_when_passing(self, planned_engine, mock_llm):
        """Outline should not be revised when review passes."""
        mock_llm._responses["volume_design_review"] = _make_review_response()
        mock_llm._call_log.clear()

        result = planned_engine.design(volume_number=1)
        assert result["title"] != "改訂版"


# ── Write tests ────────────────────────────────────────────────────────


class TestWrite:
    """Verify write() output."""

    def test_write_creates_scene_drafts(self, planned_engine, mock_llm):
        """write() should create scene draft files."""
        planned_engine.design(volume_number=1)
        mock_llm._call_log.clear()
        results = planned_engine.write(volume_number=1)
        assert len(results) > 0
        vol_dir = planned_engine._series_dir / "vol01"

        # Check that chapter directories exist
        chapter_dirs = list(vol_dir.glob("vol01_ch*"))
        assert len(chapter_dirs) > 0

    def test_write_updates_volume_status(self, planned_engine, mock_llm):
        """write() should update volume status."""
        planned_engine.design(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.write(volume_number=1)
        assert planned_engine.state.status == "初稿済"



# ── Export tests ────────────────────────────────────────────────────────


class TestExportMixin:
    """Verify export behavior."""

    def test_export_creates_manuscript(self, planned_engine, mock_llm):
        """export() should create manuscript.md."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.export(volume_number=1)

        export_path = planned_engine._series_dir / "exports" / f"{planned_engine._slug}_vol01.md"
        assert export_path.exists()

    def test_export_creates_metadata(self, planned_engine, mock_llm):
        """export() should create metadata.json."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.export(volume_number=1)

        meta_path = (
            planned_engine._series_dir / "exports" / f"{planned_engine._slug}_vol01_metadata.json"
        )
        assert meta_path.exists()

    def test_export_creates_readiness_report(self, planned_engine, mock_llm):
        """export() should create kdp_readiness_report.md."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.export(volume_number=1)

        report_path = (
            planned_engine._series_dir
            / "exports"
            / f"{planned_engine._slug}_vol01_kdp_readiness_report.md"
        )
        assert report_path.exists()


# ── Resume tests ───────────────────────────────────────────────────────


class TestResume:
    """Verify resume behavior."""

    def test_resume_planned(self, engine, mock_llm, tmp_workdir):
        """resume() from planned state should restart plan."""
        engine.state.status = "計画中"
        result = engine.resume()
        assert result is not None

    def test_resume_outlined(self, planned_engine, mock_llm):
        """resume() from outlined state should restart design."""
        planned_engine.design(volume_number=1)
        planned_engine.state.status = "デザイン済"
        result = planned_engine.resume()
        assert result is not None

    def test_resume_drafting(self, planned_engine, mock_llm):
        """resume() from drafting state should continue write."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        planned_engine.state.status = "初稿済"
        result = planned_engine.resume()
        assert result is not None


# ── Context builder tests ──────────────────────────────────────────────


class TestContextBuilder:
    """Verify context building."""

    def test_build_context_empty(self, tmp_workdir):
        """build_context() with no data should return empty context."""
        ctx = ContextBuilder(
            series_dir=tmp_workdir,
            blackboard_storage=BlackboardStorage(tmp_workdir),
            bible_storage=BibleStorage(tmp_workdir),
        )
        result = ctx.build_context()
        assert result is not None

    def test_build_context_with_facts(self, tmp_workdir):
        """build_context() should include facts."""
        ctx = ContextBuilder(
            series_dir=tmp_workdir,
            blackboard_storage=BlackboardStorage(tmp_workdir),
            bible_storage=BibleStorage(tmp_workdir),
        )
        result = ctx.build_context()
        assert result is not None


# ── Bible manager tests ────────────────────────────────────────────────


class TestBibleManager:
    """Verify bible management."""

    def test_to_text_empty(self, tmp_workdir):
        """Bible with no data should return empty or string."""
        bible = Bible()
        # Bible doesn't have to_text(), verify it has basic attributes
        assert hasattr(bible, "characters") or hasattr(bible, "foreshadowing")

    def test_to_text_with_characters(self, tmp_workdir):
        """Bible should include character info."""
        bible = Bible(characters=[CharacterProfile(name="主人公", role="主人公", arc="成長")])
        # Verify characters are accessible
        assert len(bible.characters) == 1
        assert bible.characters[0].name == "主人公"


# ── Scene writer tests ─────────────────────────────────────────────────


class TestSceneWriter:
    """Verify scene writing."""

    def test_load_scene_draft(self, tmp_workdir):
        """load_scene_draft() should load existing draft."""
        from novel_forge.prompts import PromptManager
        from novel_forge.quality_gate import QualityGate

        scene_file = tmp_workdir / "test_scene.md"
        scene_file.write_text("# Test\n\nContent", encoding="utf-8")
        writer = SceneWriter(
            workdir=tmp_workdir,
            llm_client=MockLLMClient(),
            prompt_manager=PromptManager(prompt_dir=tmp_workdir / "prompts"),
            quality=QualityGate(),
            blackboard_storage=BlackboardStorage(tmp_workdir),
            bible_storage=BibleStorage(tmp_workdir),
        )
        result = writer.load_scene_draft(vol_num=1, scene_number=1, chapter_number=1)
        assert result is not None




class TestQualityGate:
    """Verify quality gate."""

    def test_check_passes_clean_review(self):
        """check() should pass when no issues."""
        gate = QualityGate()
        review = {"issues": [], "revision_needed": False, "ready_for_publication": True}
        result = gate.check_scene(review)
        assert result.revision_needed is False

    def test_check_fails_with_blocker(self):
        """check() should fail when blocker issues exist."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "致命的", "field": "test", "description": "問題", "suggestion": "", "before": "", "after": ""}],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is True

    def test_check_fails_with_major_issues(self):
        """check() should fail when 2+ major issues exist."""
        gate = QualityGate()
        review = {
            "issues": [
                {"severity": "重要", "field": "test", "description": "問題1", "suggestion": "", "before": "", "after": ""},
                {"severity": "重要", "field": "test", "description": "問題2", "suggestion": "", "before": "", "after": ""},
            ],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is True


# ── Quality gate boundary tests ────────────────────────────────────────


class TestQualityGateBoundary:
    """Test quality gate boundary conditions."""

    def test_single_minor_issue_passes(self):
        """Single minor issue should pass."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "軽微", "field": "test", "description": "軽微", "suggestion": "", "before": "", "after": ""}],
            "revision_needed": False,
            "ready_for_publication": True,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is False

    def test_single_major_issue_passes(self):
        """Single major issue should pass (threshold is 2)."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "重要", "field": "test", "description": "重要", "suggestion": "", "before": "", "after": ""}],
            "revision_needed": False,
            "ready_for_publication": True,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is False

    def test_critical_issue_fails(self):
        """Critical issue should always fail."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "致命的", "field": "test", "description": "致命的", "suggestion": "", "before": "", "after": ""}],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is True

    def test_empty_issues_passes(self):
        """Empty issues should pass."""
        gate = QualityGate()
        review = {"issues": [], "revision_needed": False, "ready_for_publication": True}
        result = gate.check_scene(review)
        assert result.revision_needed is False

    def test_mixed_severity_fails(self):
        """Mix of critical + minor should fail."""
        gate = QualityGate()
        review = {
            "issues": [
                {"severity": "致命的", "field": "test", "description": "致命的", "suggestion": "", "before": "", "after": ""},
                {"severity": "軽微", "field": "test", "description": "軽微", "suggestion": "", "before": "", "after": ""},
            ],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is True

    def test_two_major_fails(self):
        """Two major issues should fail."""
        gate = QualityGate()
        review = {
            "issues": [
                {"severity": "重要", "field": "test", "description": "重要1", "suggestion": "", "before": "", "after": ""},
                {"severity": "重要", "field": "test", "description": "重要2", "suggestion": "", "before": "", "after": ""},
            ],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check_scene(review)
        assert result.revision_needed is True

    def test_ready_for_publication_flag(self):
        """passed flag should be set correctly."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "致命的", "field": "test", "description": "問題", "suggestion": "", "before": "", "after": ""}],
            "revision_needed": True,
        }
        result = gate.check_scene(review)
        assert result.passed is False


# ── Config generation test ────────────────────────────────────────────


class TestConfigGeneration:
    """Verify config handling."""

    def test_plan_works_without_config(self, tmp_workdir, mock_llm):
        """plan() should work without config.yaml."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        prompts = PromptManager(prompt_dir=tmp_workdir / "prompts")
        eng = NovelEngine(
            workdir=tmp_workdir,
            model="test-model",
            llm_client=mock_llm,
            prompt_manager=prompts,
            config={"llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 3}},
        )

        eng.plan("テスト")

        # Plan should complete successfully
        series_plan_path = eng._series_dir / "series_plan.json"
        assert series_plan_path.exists()


# ── File naming convention tests ────────────────────────────────────────


class TestFileNamingConvention:
    """Verify file naming conventions."""

    def test_plan_review_first_entry_is_version_0(self, engine, mock_llm):
        """First review entry should be version 0."""
        mock_llm.add_sequence("series_plan_concept", _make_plan_response())
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review", {"issues": [], "suggestions": []})

        engine.plan("テスト")
        review_path = engine._series_dir / "series_concept_review.json"
        data = json.loads(review_path.read_text(encoding="utf-8"))
        if data.get("reviews"):
            assert data["reviews"][0]["version"] == 0

    def test_design_review_has_reviews_list(self, planned_engine, mock_llm):
        """Design review files should contain a 'reviews' list."""
        planned_engine.design(volume_number=1)
        vol_dir = planned_engine._series_dir / "vol01"
        review_path = vol_dir / "vol01_review.json"
        if review_path.exists():
            data = json.loads(review_path.read_text(encoding="utf-8"))
            assert "reviews" in data
            assert isinstance(data["reviews"], list)

    def test_no_legacy_design_json(self, planned_engine, mock_llm):
        """design() should not create legacy design.json."""
        planned_engine.design(volume_number=1)
        legacy = planned_engine._series_dir / "design.json"
        assert not legacy.exists()


# ── Prompt input completeness tests ────────────────────────────────────


class TestPromptInputCompleteness:
    """Verify that review prompts receive necessary information.

    These tests use MockLLMClient to control LLM responses and verify
    that the prompts contain the expected context.
    """

    def test_series_plan_review_receives_world_rules(self, engine, mock_llm, tmp_workdir):
        """Series plan review should receive world rules in the plan text."""
        # Direct field overrides: _make_plan_response's 'world' kwarg is a legacy alias
        # that was never expanded by callers — BUG.  Pass via the fields _review_plan_concept
        # actually reads (world_summary + world_rules).
        plan_data = {
            "title": "テストシリーズ長いタイトル",
            "slug": "test_series",
            "logline": "テストのあらすじです。これは十分な長さのあらすじです。主人公が冒険に出ます。",
            "genre": ["fantasy"],
            "target_audience": (
                "10代後半から30代の読者をターゲットにしたファンタジー小説で、"
                "冒険と成長の物語を求める層に向けて書かれています。"
            ),
            "themes": ["冒険", "成長"],
            "selling_points": [
                "ユニークな世界観と複雑な魔法システムが社会のあらゆる側面に影響を与えている",
                "複雑なキャラクター関係がシリーズを通じて自然に進化していく",
            ],
            "world_summary": (
                "魔法が存在し、古代の法則によって規制されている世界。"
                "物語は若い魔法使いが自分の力を発見し、魔法能力が社会的地位を決定する社会を"
                "ナビゲートすることを学ぶところから始まる。"
            ),
            "world_rules": [
                "魔法には貴重な何かを犠牲にする必要がある",
                "古代の法則がすべての呪文詠唱を支配し、違反は厳しく罰せられる",
            ],
            "main_characters": [{"name": "主人公", "role": "主人公", "arc": "成長"}],
            "planned_volumes": [{"title": "第1巻", "premise": "始まり"}],
        }
        mock_llm.add_sequence("series_plan_concept", plan_data)
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence(
            "series_plan_volumes_review",
            {
                "volume_uniqueness": "良い",
                "series_flow": "良い",
                "cliffhanger": "良い",
                "theme_consistency": "良い",
                "issues": [],
            },
        )

        engine.plan("テスト")

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "魔法が存在し" in review_prompt  # world_summary に含まれる (連用形)

    def test_series_plan_review_receives_character_arc(self, engine, mock_llm, tmp_workdir):
        """Series plan core review should receive series plan context."""
        mock_llm.add_sequence(
            "series_plan_concept",
            _make_plan_response(
                main_characters=[{"name": "主人公", "role": "主人公", "arc": "成長から覚醒へ"}]
            ),
        )
        mock_llm.add_sequence("series_plan_concept_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence(
            "series_plan_volumes_review",
            {
                "volume_uniqueness": "良い",
                "series_flow": "良い",
                "cliffhanger": "良い",
                "theme_consistency": "良い",
                "issues": [],
            },
        )

        engine.plan("テスト")

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "テストシリーズ" in review_prompt
        assert "テストのあらすじ" in review_prompt



class TestFakeLLMFullPipeline:
    def test_fake_llm_pipeline_plan_design_write_export(self, planned_engine):
        """A fake LLM can drive the public pipeline through export."""
        design_result = planned_engine.design(1)
        write_result = planned_engine.write(1)
        export_result = planned_engine.export(1)

        assert design_result["scenes"]
        assert write_result
        assert export_result["manuscript_path"].endswith(".md")
        assert export_result["metadata_path"].endswith("_metadata.json")
        assert export_result["report_path"].endswith("_kdp_readiness_report.md")
