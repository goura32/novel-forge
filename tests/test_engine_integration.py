"""Engine integration tests with mock LLM client.

Tests the full plan → outline → write → export pipeline
without calling a real LLM.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from novel_forge.context_builder import ContextBuilder
from novel_forge.engine import NovelEngine
from novel_forge.models import (
    Bible,
    Blackboard,
    CharacterProfile,
    SceneRecord,
    VolumeOutline,
    VolumeProgress,
)
from novel_forge.prompts import PromptLoader, PromptManager
from novel_forge.quality import QualityGate
from novel_forge.scene_writer import SceneWriter
from novel_forge.schemas import get_schema
from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage


# ── Mock LLM Client ─────────────────────────────────────────────────────

class MockLLMClient:
    """Mock LLM client that returns predefined responses."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self._responses = responses or {}
        self._call_log: list[tuple[str, str]] = []  # (kind, prompt_snippet)
        self._call_count = 0
        self._sequence: list[tuple[str, Any]] = []  # ordered (kind, response)
        self._seq_idx = 0

    def add_sequence(self, kind: str, response: Any) -> None:
        """Add a response to the sequential response queue."""
        self._sequence.append((kind, response))

    def complete_json(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._call_count += 1
        self._call_log.append((kind, user_prompt))

        # Check sequence first
        if self._seq_idx < len(self._sequence):
            expected_kind, resp = self._sequence[self._seq_idx]
            self._seq_idx += 1
            if isinstance(resp, dict):
                return resp
            return resp

        # Fall back to responses dict
        if kind in self._responses:
            resp = self._responses[kind]
            if callable(resp):
                return resp(kind=kind, system=system_prompt, user=user_prompt, schema=schema)
            if isinstance(resp, dict):
                return resp
            return resp

        # Default responses per kind
        defaults = {
            "series_plan": {
                "title": "テストシリーズ",
                "slug": "test-series",
                "logline": "テストのあらすじ",
                "genre": "fantasy",
                "target_audience": "10代〜30代",
                "themes": ["冒険", "成長"],
                "selling_points": ["ユニークな世界観"],
                "world": {"summary": "魔法の世界", "rules": ["魔法が存在する"]},
                "main_characters": [
                    {"name": "主人公", "role": "主人公", "arc": "成長"}
                ],
                "planned_volumes": [
                    {"title": "第1巻", "premise": "始まり"}
                ],
            },
            "series_plan_review": {
                "score": 80.0,
                "issues": [],
                "strengths": ["良い"],
                "recommendations": [],
            },
            "series_plan_revision": {
                "title": "テストシリーズ改訂",
                "slug": "test-series-rev",
                "logline": "テストのあらすじ改訂",
                "genre": "fantasy",
                "target_audience": "10代〜30代",
                "themes": ["冒険", "成長"],
                "selling_points": ["ユニークな世界観"],
                "world": {"summary": "魔法の世界", "rules": ["魔法が存在する"]},
                "main_characters": [
                    {"name": "主人公", "role": "主人公", "arc": "成長"}
                ],
                "planned_volumes": [
                    {"title": "第1巻", "premise": "始まり"}
                ],
            },
            "volume_outline": {
                "chapters": [
                    {
                        "title": "プロローグ",
                        "purpose": "導入",
                    },
                    {
                        "title": "転換",
                        "purpose": "転換",
                    },
                    {
                        "title": "クライマックス",
                        "purpose": "クライマックス",
                    },
                    {
                        "title": "収束",
                        "purpose": "収束",
                    },
                ],
            },
            "scene_outline": {
                "title": "出会い",
                "goal": "主人公を紹介する",
                "outcome": "主人公が旅立つ",
                "conflict": "葛藤なし",
                "pov": "主人公",
                "characters": ["主人公"],
            },
            "volume_outline_review": {
                "score": 80.0,
                "issues": [],
                "strengths": ["良い構成"],
                "recommendations": [],
            },
            "volume_outline_revision": {
                "chapters": [
                    {
                        "title": "プロローグ改訂",
                        "purpose": "導入",
                    },
                    {
                        "title": "転換改訂",
                        "purpose": "転換",
                    },
                    {
                        "title": "クライマックス改訂",
                        "purpose": "クライマックス",
                    },
                    {
                        "title": "収束改訂",
                        "purpose": "収束",
                    },
                ],
            },
            "scene_review": {
                "score": 80.0,
                "issues": [],
                "strengths": ["良いシーン"],
                "recommendations": [],
                "dimensions": {},
            },
            "scene_summary_and_bible_update": {
                "summary": "シーンの要約",
                "facts": [],
                "continuity_notes": [],
                "characters": [],
                "foreshadowing": [],
                "relationships": [],
                "subplots": [],
                "glossary": [],
                "world_rules": [],
            },
        }
        if kind in defaults:
            return defaults[kind]
        return {}

    def complete_text(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self._call_count += 1
        self._call_log.append((kind, user_prompt))

        if self._seq_idx < len(self._sequence):
            expected_kind, resp = self._sequence[self._seq_idx]
            self._seq_idx += 1
            if isinstance(resp, str):
                return resp
            return str(resp)

        if kind in self._responses:
            resp = self._responses[kind]
            if callable(resp):
                return resp(kind=kind, system=system_prompt, user=user_prompt)
            if isinstance(resp, str):
                return resp
            return str(resp)

        defaults = {
            "scene_draft": "これはテストシーンの本文です。主人公が旅立ちます。",
            "scene_revision": "これは改訂されたテストシーンの本文です。主人公が旅立ちます。",
        }
        if kind in defaults:
            return defaults[kind]
        return ""


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workdir(tmp_path):
    """Create a minimal workdir with prompts and schemas."""
    # Copy prompts
    src_prompts = Path(__file__).resolve().parent.parent / "prompts"
    dst_prompts = tmp_path / "prompts"
    if src_prompts.exists():
        import shutil
        shutil.copytree(src_prompts, dst_prompts)
    return tmp_path


@pytest.fixture
def mock_llm():
    return MockLLMClient()


@pytest.fixture
def engine(tmp_workdir, mock_llm):
    """Create a NovelEngine with mock LLM."""
    prompts = PromptManager(loader=PromptLoader(prompt_dir=tmp_workdir / "prompts"))
    eng = NovelEngine(
        workdir=tmp_workdir,
        model="test-model",
        llm_client=mock_llm,
        prompt_manager=prompts,
        config={"llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 0}},
    )
    return eng


def _make_plan_response(**overrides) -> dict:
    """Create a valid series plan response."""
    base = {
        "title": "テストシリーズ",
        "slug": "test-series",
        "logline": "テストのあらすじ",
        "genre": "fantasy",
        "target_audience": "10代〜30代",
        "themes": ["冒険", "成長"],
        "selling_points": ["ユニークな世界観"],
        "world": {"summary": "魔法の世界", "rules": ["魔法が存在する"]},
        "main_characters": [
            {"name": "主人公", "role": "主人公", "arc": "成長"}
        ],
        "planned_volumes": [
            {"title": "第1巻", "premise": "始まり"}
        ],
    }
    base.update(overrides)
    return base


def _make_review_response(score: float = 80.0, issues: list | None = None) -> dict:
    return {
        "score": score,
        "issues": issues or [],
        "strengths": ["良い"],
        "recommendations": [],
    }


def _make_outline_response(**overrides) -> dict:
    base = {
        "title": "第1巻",
        "premise": "始まりの物語",
        "chapters": [
            {"title": "プロローグ", "purpose": "導入"},
            {"title": "転換", "purpose": "転換"},
            {"title": "クライマックス", "purpose": "クライマックス"},
            {"title": "収束", "purpose": "収束"},
        ],
    }
    base.update(overrides)
    return base


# ── Plan tests ──────────────────────────────────────────────────────────

class TestPlan:
    def test_plan_creates_series_plan(self, engine, mock_llm, tmp_workdir):
        """plan() should create series_plan.json and set state."""
        result = engine.plan("テストキーワード")

        assert result["title"] == "テストシリーズ"
        assert engine.state.series_title == "テストシリーズ"
        assert engine.state.status == "計画中"

        plan_path = tmp_workdir / ".novel-forge" / "series_plan.json"
        assert plan_path.exists()
        saved = json.loads(plan_path.read_text(encoding="utf-8"))
        assert saved["title"] == "テストシリーズ"

    def test_plan_saves_review(self, engine, mock_llm, tmp_workdir):
        """plan() should save the review result."""
        engine.plan("テスト")

        review_path = tmp_workdir / ".novel-forge" / "series_plan_review.json"
        assert review_path.exists()

    def test_plan_calls_llm_for_generation_and_review(self, engine, mock_llm):
        """plan() should call LLM at least twice (generate + review)."""
        engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan" in kinds
        assert "series_plan_review" in kinds

    def test_plan_volume_numbers_assigned(self, engine, mock_llm):
        """Engine should auto-assign volume numbers."""
        result = engine.plan("テスト")

        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            assert vol["number"] == i

    def test_plan_slug_truncated(self, engine, mock_llm):
        """Slug longer than 256 chars should be truncated."""
        long_slug = "a" * 300
        mock_llm._responses["series_plan"] = _make_plan_response(slug=long_slug)

        result = engine.plan("テスト")

        assert len(result["slug"]) <= 256


# ── Plan review → revise loop ──────────────────────────────────────────

class TestPlanReviewLoop:
    def test_plan_revises_on_low_score(self, engine, mock_llm):
        """Plan should be revised when review score < 7.0."""
        # First review returns low score, second returns high
        mock_llm.add_sequence("series_plan", _make_plan_response())
        mock_llm.add_sequence("series_plan_review", _make_review_response(score=50))
        mock_llm.add_sequence("series_plan_revision", _make_plan_response(title="改訂版"))
        mock_llm.add_sequence("series_plan_review", _make_review_response(score=80))

        result = engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_revision" in kinds
        assert result["title"] == "改訂版"

    def test_plan_revises_on_critical_issues(self, engine, mock_llm):
        """Plan should be revised when there are critical issues."""
        mock_llm.add_sequence("series_plan", _make_plan_response())
        mock_llm.add_sequence("series_plan_review", _make_review_response(
            score=80,
            issues=[{"severity": "critical", "category": "test", "description": "問題"}]
        ))
        mock_llm.add_sequence("series_plan_revision", _make_plan_response(title="修正版"))
        mock_llm.add_sequence("series_plan_review", _make_review_response(score=80))

        result = engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_revision" in kinds
        assert result["title"] == "修正版"

    def test_plan_stops_after_3_retries(self, engine, mock_llm):
        """Plan revision should stop after 3 retries even if still failing."""
        mock_llm.add_sequence("series_plan", _make_plan_response())
        for _ in range(4):  # 1 initial + 3 retries
            mock_llm.add_sequence("series_plan_review", _make_review_response(score=30))
            mock_llm.add_sequence("series_plan_revision", _make_plan_response())

        result = engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        revision_count = kinds.count("series_plan_revision")
        assert revision_count == 3

    def test_plan_no_revision_when_passing(self, engine, mock_llm):
        """Plan should not be revised when score >= 7.0 and no critical issues."""
        mock_llm.add_sequence("series_plan", _make_plan_response())
        mock_llm.add_sequence("series_plan_review", _make_review_response(score=80))

        result = engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_revision" not in kinds


# ── Outline tests ──────────────────────────────────────────────────────

class TestOutline:
    def test_outline_creates_outline(self, engine, mock_llm, tmp_workdir):
        """outline() should create outline.json and set state."""
        # First plan
        engine.plan("テスト")
        mock_llm._call_log.clear()

        result = engine.outline(volume_number=1)

        assert result["title"] == "第1巻"
        assert engine.state.status == "アウトライン済"

        outline_path = tmp_workdir / ".novel-forge" / "volumes" / "vol01" / "outline.json"
        assert outline_path.exists()

    def test_outline_flattens_scenes(self, engine, mock_llm):
        """outline() should flatten nested scenes and auto-number."""
        engine.plan("テスト")
        mock_llm._call_log.clear()

        result = engine.outline(volume_number=1)

        # Scenes should be flat list with numbers
        assert "scenes" in result
        for i, sc in enumerate(result["scenes"], 1):
            assert sc["number"] == i
            assert "chapter_number" in sc

    def test_outline_assigns_chapter_numbers(self, engine, mock_llm):
        """outline() should auto-assign chapter numbers."""
        engine.plan("テスト")
        mock_llm._call_log.clear()

        result = engine.outline(volume_number=1)

        for i, ch in enumerate(result["chapters"], 1):
            assert ch["number"] == i


# ── Outline review → revise loop ──────────────────────────────────────

class TestOutlineReviewLoop:
    def test_outline_revises_on_low_score(self, engine, mock_llm):
        """Outline should be revised when review score < 7.0."""
        engine.plan("テスト")
        mock_llm._call_log.clear()

        # Set default responses (outline generates multiple LLM calls)
        mock_llm._responses["volume_outline"] = _make_outline_response()
        mock_llm._responses["scene_outline"] = {
            "title": "出会い",
            "goal": "主人公を紹介する",
            "outcome": "主人公が旅立つ",
            "conflict": "葛藤なし",
            "pov": "主人公",
            "characters": ["主人公"],
        }
        mock_llm._responses["volume_outline_review"] = _make_review_response(score=50)
        mock_llm._responses["volume_outline_revision"] = _make_outline_response(title="改訂")
        mock_llm._call_log.clear()

        result = engine.outline(volume_number=1)

        kinds = [k for k, _ in mock_llm._call_log]
        assert "volume_outline_revision" in kinds
        assert result["title"] == "改訂"

    def test_outline_stops_after_3_retries(self, engine, mock_llm):
        """Outline revision should stop after 3 retries."""
        engine.plan("テスト")
        mock_llm._call_log.clear()

        # Set default responses (outline generates multiple LLM calls)
        mock_llm._responses["volume_outline"] = _make_outline_response()
        mock_llm._responses["scene_outline"] = {
            "title": "出会い",
            "goal": "主人公を紹介する",
            "outcome": "主人公が旅立つ",
            "conflict": "葛藤なし",
            "pov": "主人公",
            "characters": ["主人公"],
        }
        mock_llm._responses["volume_outline_review"] = _make_review_response(score=30)
        mock_llm._responses["volume_outline_revision"] = _make_outline_response()
        mock_llm._call_log.clear()

        result = engine.outline(volume_number=1)

        kinds = [k for k, _ in mock_llm._call_log]
        assert kinds.count("volume_outline_revision") == 3


# ── Write tests ────────────────────────────────────────────────────────

class TestWrite:
    def test_write_creates_scene_drafts(self, engine, mock_llm, tmp_workdir):
        """write() should create scene draft files."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        mock_llm._call_log.clear()

        results = engine.write(volume_number=1)

        assert len(results) > 0
        for r in results:
            assert "scene_number" in r
            assert "status" in r

    def test_write_creates_chapter_files(self, engine, mock_llm, tmp_workdir):
        """write() should assemble chapter files from scenes."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        mock_llm._call_log.clear()

        engine.write(volume_number=1)

        chapters_dir = tmp_workdir / ".novel-forge" / "volumes" / "vol01" / "chapters"
        assert chapters_dir.exists()
        ch_files = list(chapters_dir.glob("ch*.md"))
        assert len(ch_files) > 0

    def test_write_updates_volume_status(self, engine, mock_llm):
        """write() should set volume status to 初稿済."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        mock_llm._call_log.clear()

        engine.write(volume_number=1)

        vol = engine._current_volume()
        assert vol.status == "初稿済"
        assert engine.state.status == "初稿済"

    def test_write_skips_completed_scenes(self, engine, mock_llm, tmp_workdir):
        """write() should skip scenes already marked as 修正済."""
        engine.plan("テスト")
        engine.outline(volume_number=1)

        # Mark ALL scenes as completed
        vol = engine._current_volume()
        from novel_forge.models import SceneRecord
        outline_path = tmp_workdir / ".novel-forge" / "volumes" / "vol01" / "outline.json"
        outline_dict = json.loads(outline_path.read_text(encoding="utf-8"))
        for sc in outline_dict.get("scenes", []):
            vol.scenes.append(SceneRecord(scene_number=sc["number"], status="修正済"))

        # Create dummy draft files for all scenes
        for sc in outline_dict.get("scenes", []):
            ch_num = sc.get("chapter_number", 1)
            sc_num = sc["number"]
            scene_dir = tmp_workdir / ".novel-forge" / "volumes" / "vol01" / "scenes" / f"ch{ch_num:02d}"
            scene_dir.mkdir(parents=True, exist_ok=True)
            (scene_dir / f"vol01_ch{ch_num:02d}_sc{sc_num:02d}.md").write_text("既存のドラフト", encoding="utf-8")

        mock_llm._call_log.clear()
        results = engine.write(volume_number=1)

        # Should not call scene_draft for already-completed scenes
        kinds = [k for k, _ in mock_llm._call_log]
        assert "scene_draft" not in kinds

    def test_write_calls_summarize_and_update_bible(self, engine, mock_llm):
        """write() should call summarize_and_update_bible after each scene."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        mock_llm._call_log.clear()

        engine.write(volume_number=1)

        kinds = [k for k, _ in mock_llm._call_log]
        assert "scene_summary_and_bible_update" in kinds


# ── Export tests ───────────────────────────────────────────────────────

class TestExport:
    def test_export_creates_manuscript(self, engine, mock_llm, tmp_workdir):
        """export() should create manuscript file."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        engine.write(volume_number=1)
        mock_llm._call_log.clear()

        result = engine.export(volume_number=1)

        assert "manuscript_path" in result
        assert Path(result["manuscript_path"]).exists()

    def test_export_creates_metadata(self, engine, mock_llm, tmp_workdir):
        """export() should create metadata JSON."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        engine.write(volume_number=1)
        mock_llm._call_log.clear()

        result = engine.export(volume_number=1)

        assert "metadata_path" in result
        assert Path(result["metadata_path"]).exists()

    def test_export_creates_readiness_report(self, engine, mock_llm, tmp_workdir):
        """export() should create KDP readiness report."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        engine.write(volume_number=1)
        mock_llm._call_log.clear()

        result = engine.export(volume_number=1)

        assert "report_path" in result
        assert Path(result["report_path"]).exists()

    def test_export_sets_status_exported(self, engine, mock_llm):
        """export() should set status to 出力済."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        engine.write(volume_number=1)
        mock_llm._call_log.clear()

        engine.export(volume_number=1)

        vol = engine._current_volume()
        assert vol.status == "出力済"
        assert engine.state.status == "出力済"

    def test_export_forced_status(self, engine, mock_llm):
        """export() should set 強制出力済 if any scene was force-exported."""
        engine.plan("テスト")
        engine.outline(volume_number=1)
        engine.write(volume_number=1)

        # Force one scene to 強制出力済
        vol = engine._current_volume()
        if vol.scenes:
            vol.scenes[0].status = "強制出力済"

        mock_llm._call_log.clear()
        engine.export(volume_number=1)

        vol = engine._current_volume()
        assert vol.status == "強制出力済"


# ── Resume tests ──────────────────────────────────────────────────────

class TestResume:
    def test_resume_planned(self, engine):
        """resume() should return 'plan' for 計画中 status."""
        result = engine.resume()
        assert result["action"] == "plan"

    def test_resume_outlined(self, engine):
        """resume() should return 'outline' for アウトライン済 status."""
        engine._state.status = "アウトライン済"
        result = engine.resume()
        assert result["action"] == "outline"

    def test_resume_drafting(self, engine):
        """resume() should return 'write' for 執筆中 volume status."""
        vol = VolumeProgress(volume_number=1, status="執筆中", current_chapter=0)
        engine._state.volumes.append(vol)
        result = engine.resume()
        assert result["action"] == "write"

    def test_resume_exported(self, engine):
        """resume() should return 'export' for 出力済 status."""
        engine._state.status = "出力済"
        result = engine.resume()
        assert result["action"] == "export"

    def test_resume_drafting_takes_priority_over_outlined(self, engine):
        """When volume is 執筆中, resume should return 'write' even if state is アウトライン済."""
        engine._state.status = "アウトライン済"
        vol = VolumeProgress(volume_number=1, status="執筆中", current_chapter=0)
        engine._state.volumes.append(vol)
        result = engine.resume()
        assert result["action"] == "write"


# ── ContextBuilder tests ──────────────────────────────────────────────

class TestContextBuilder:
    def test_get_series_plan_summary(self, tmp_workdir):
        """get_series_plan_summary should read series_plan.json and format it."""
        plan_data = {
            "title": "テスト",
            "logline": "あらすじ",
            "genre": "fantasy",
            "target_audience": "10代",
            "themes": ["冒険"],
            "world": {"summary": "魔法世界", "rules": ["魔法あり"]},
            "main_characters": [
                {"name": "主人公", "role": "主人公", "arc": "成長"}
            ],
            "planned_volumes": [
                {"title": "第1巻", "premise": "始まり"}
            ],
        }
        plan_path = tmp_workdir / ".novel-forge" / "series_plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text(json.dumps(plan_data, ensure_ascii=False), encoding="utf-8")

        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        summary = ctx.get_series_plan_summary()
        assert "テスト" in summary
        assert "あらすじ" in summary
        assert "魔法世界" in summary
        assert "主人公" in summary

    def test_get_series_plan_summary_missing_file(self, tmp_workdir):
        """get_series_plan_summary should return empty string if no plan file."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        assert ctx.get_series_plan_summary() == ""

    def test_get_genre(self, tmp_workdir):
        """get_genre should return genre from series_plan.json."""
        plan_data = {"title": "T", "genre": "sf"}
        plan_path = tmp_workdir / ".novel-forge" / "series_plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        assert ctx.get_genre() == "sf"

    def test_get_genre_default(self, tmp_workdir):
        """get_genre should return 'fantasy' if no plan file."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        assert ctx.get_genre() == "fantasy"

    def test_build_context_empty(self, tmp_workdir):
        """build_context should return empty string for empty bible/blackboard."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        result = ctx.build_context()
        assert result == ""

    def test_build_context_with_bible(self, tmp_workdir):
        """build_context should include bible data."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        bible = Bible(
            characters=[CharacterProfile(name="主人公", role="主人公", personality="勇敢")],
            world_rules=["魔法が存在する"],
        )
        bible_storage.save(bible)

        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)
        result = ctx.build_context()
        assert "主人公" in result
        assert "勇敢" in result
        assert "魔法が存在する" in result

    def test_build_continuity_first_scene(self, tmp_workdir):
        """build_continuity should return placeholder for first scene."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        result = ctx.build_continuity(scene_number=1, vol_num=1, load_scene_draft_fn=lambda v, s: "")
        assert "最初のシーン" in result

    def test_build_continuity_with_previous_scene(self, tmp_workdir):
        """build_continuity should include previous scene text."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        def load_draft(vol_num, scene_num):
            if scene_num == 1:
                return "前シーンの本文"
            return ""

        result = ctx.build_continuity(scene_number=2, vol_num=1, load_scene_draft_fn=load_draft)
        assert "前シーンの本文" in result

    def test_build_continuity_with_summaries(self, tmp_workdir):
        """build_continuity should include recent scene summaries."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bb = Blackboard()
        bb.scene_summaries["1"] = "シーン1の要約"
        bb_storage.save(bb)

        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        result = ctx.build_continuity(scene_number=3, vol_num=1, load_scene_draft_fn=lambda v, s: "")
        assert "シーン1の要約" in result

    def test_get_scene_summary(self, tmp_workdir):
        """get_scene_summary should format scene data."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        scene = MagicMock()
        scene.title = "出会い"
        scene.goal = "主人公を紹介する"
        scene.outcome = "旅立つ"
        scene.conflict = "葛藤"
        scene.pov = "主人公"
        scene.characters = ["主人公", "仲間"]

        result = ctx.get_scene_summary(scene)
        assert "出会い" in result
        assert "主人公を紹介する" in result
        assert "旅立つ" in result

    def test_get_outline_summary(self, tmp_workdir):
        """get_outline_summary should format outline data."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        ctx = ContextBuilder(tmp_workdir, bb_storage, bible_storage)

        from novel_forge.models import ChapterOutline, SceneOutline
        outline = VolumeOutline(
            title="第1巻",
            premise="始まり",
            volume_number=1,
            chapters=[
                ChapterOutline(number=1, title="プロローグ", purpose="導入"),
            ],
            scenes=[
                SceneOutline(number=1, chapter_number=1, title="出会い",
                             goal="紹介", outcome="旅立ち",
                             characters=["主人公"]),
            ],
        )

        result = ctx.get_outline_summary(outline)
        assert "第1巻" in result
        assert "プロローグ" in result
        assert "出会い" in result


# ── BibleManager tests ────────────────────────────────────────────────

class TestBibleManager:
    def test_to_text_empty(self, tmp_workdir):
        """to_text should return placeholder for empty bible."""
        storage = BibleStorage(tmp_workdir)
        mgr = type("BibleManager", (), {"_storage": storage})()
        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)

        result = mgr.to_text()
        assert "空です" in result

    def test_to_text_with_characters(self, tmp_workdir):
        """to_text should include character info."""
        storage = BibleStorage(tmp_workdir)
        bible = Bible(characters=[
            CharacterProfile(name="主人公", role="主人公", personality="勇敢", motivation="正義"),
        ])
        storage.save(bible)

        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)

        result = mgr.to_text()
        assert "主人公" in result
        assert "勇敢" in result
        assert "正義" in result

    def test_to_text_with_relationships(self, tmp_workdir):
        """to_text should include relationships."""
        from novel_forge.models import RelationshipItem
        storage = BibleStorage(tmp_workdir)
        bible = Bible(relationships=[
            RelationshipItem(character_a="A", character_b="B", relationship_type="友人", status="良好"),
        ])
        storage.save(bible)

        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)

        result = mgr.to_text()
        assert "A" in result
        assert "B" in result
        assert "友人" in result

    def test_to_text_with_subplots(self, tmp_workdir):
        """to_text should include subplots."""
        from novel_forge.models import SubplotItem
        storage = BibleStorage(tmp_workdir)
        bible = Bible(subplots=[
            SubplotItem(id="sp1", name="陰謀", status="in_progress", progress_note="進行中"),
        ])
        storage.save(bible)

        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)

        result = mgr.to_text()
        assert "陰謀" in result
        assert "進行中" in result

    def test_to_text_with_foreshadowing(self, tmp_workdir):
        """to_text should include foreshadowing."""
        from novel_forge.models import ForeshadowingItem
        storage = BibleStorage(tmp_workdir)
        bible = Bible(foreshadowing=[
            ForeshadowingItem(description="剣の秘密", resolved=False),
            ForeshadowingItem(description="正体", resolved=True),
        ])
        storage.save(bible)

        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)

        result = mgr.to_text()
        assert "剣の秘密" in result
        assert "未回収" in result
        assert "回収済" in result

    def test_finalize_resolves_foreshadowing(self, tmp_workdir):
        """finalize should mark foreshadowing as resolved when mentioned in notes."""
        from novel_forge.models import ForeshadowingItem
        storage = BibleStorage(tmp_workdir)
        bible = Bible(foreshadowing=[
            ForeshadowingItem(description="剣の秘密", resolved=False),
        ])
        storage.save(bible)

        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)
        mgr.finalize(["剣の秘密が明らかになった"])

        updated = storage.load()
        assert updated.foreshadowing[0].resolved is True

    def test_finalize_unmatched_note(self, tmp_workdir):
        """finalize should not resolve unmatched foreshadowing."""
        from novel_forge.models import ForeshadowingItem
        storage = BibleStorage(tmp_workdir)
        bible = Bible(foreshadowing=[
            ForeshadowingItem(description="剣の秘密", resolved=False),
        ])
        storage.save(bible)

        from novel_forge.bible_manager import BibleManager
        mgr = BibleManager(storage)
        mgr.finalize(["別のイベント"])

        updated = storage.load()
        assert updated.foreshadowing[0].resolved is False

    def test_apply_bible_update_new_character(self, tmp_workdir):
        """_apply_bible_update should add new characters."""
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        mgr = BibleManager(storage)

        result = {
            "characters": [
                {"name": "新キャラ", "role": "仲間", "is_new": True,
                 "personality": "明るい", "appearance": "赤い髪"},
            ],
            "foreshadowing": [],
            "relationships": [],
            "subplots": [],
            "glossary": [],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=1)

        bible = storage.load()
        assert len(bible.characters) == 1
        assert bible.characters[0].name == "新キャラ"
        assert bible.characters[0].personality == "明るい"

    def test_apply_bible_update_existing_character(self, tmp_workdir):
        """_apply_bible_update should update existing characters."""
        from novel_forge.models import CharacterProfile
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        bible = Bible(characters=[CharacterProfile(name="主人公", personality="無口")])
        storage.save(bible)

        mgr = BibleManager(storage)
        result = {
            "characters": [
                {"name": "主人公", "personality": "元気", "state": "成長済"},
            ],
            "foreshadowing": [],
            "relationships": [],
            "subplots": [],
            "glossary": [],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=2)

        updated = storage.load()
        assert updated.characters[0].personality == "元気"
        assert updated.characters[0].state == "成長済"

    def test_apply_bible_update_foreshadowing_setup(self, tmp_workdir):
        """_apply_bible_update should add new foreshadowing."""
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        mgr = BibleManager(storage)

        result = {
            "characters": [],
            "foreshadowing": [
                {"type": "setup", "description": "剣の秘密"},
            ],
            "relationships": [],
            "subplots": [],
            "glossary": [],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=1)

        bible = storage.load()
        assert len(bible.foreshadowing) == 1
        assert bible.foreshadowing[0].description == "剣の秘密"
        assert bible.foreshadowing[0].resolved is False

    def test_apply_bible_update_foreshadowing_resolution(self, tmp_workdir):
        """_apply_bible_update should resolve existing foreshadowing."""
        from novel_forge.models import ForeshadowingItem
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        bible = Bible(foreshadowing=[ForeshadowingItem(description="剣の秘密", resolved=False)])
        storage.save(bible)

        mgr = BibleManager(storage)
        result = {
            "characters": [],
            "foreshadowing": [
                {"type": "resolution", "description": "剣の秘密"},
            ],
            "relationships": [],
            "subplots": [],
            "glossary": [],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=2)

        updated = storage.load()
        assert updated.foreshadowing[0].resolved is True

    def test_apply_bible_update_relationship(self, tmp_workdir):
        """_apply_bible_update should add new relationships."""
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        mgr = BibleManager(storage)

        result = {
            "characters": [],
            "foreshadowing": [],
            "relationships": [
                {"character_a": "A", "character_b": "B", "type": "友人",
                 "change_direction": "improved", "trigger_event": "共闘"},
            ],
            "subplots": [],
            "glossary": [],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=1)

        bible = storage.load()
        assert len(bible.relationships) == 1
        assert bible.relationships[0].character_a == "A"
        assert bible.relationships[0].relationship_type == "友人"

    def test_apply_bible_update_subplot(self, tmp_workdir):
        """_apply_bible_update should add new subplots."""
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        mgr = BibleManager(storage)

        result = {
            "characters": [],
            "foreshadowing": [],
            "relationships": [],
            "subplots": [
                {"id": "sp1", "name": "陰謀", "status": "in_progress", "progress_note": "進行中"},
            ],
            "glossary": [],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=1)

        bible = storage.load()
        assert len(bible.subplots) == 1
        assert bible.subplots[0].name == "陰謀"

    def test_apply_bible_update_glossary(self, tmp_workdir):
        """_apply_bible_update should add new glossary items."""
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        mgr = BibleManager(storage)

        result = {
            "characters": [],
            "foreshadowing": [],
            "relationships": [],
            "subplots": [],
            "glossary": [
                {"term": "魔力", "definition": "魔法の源"},
            ],
            "world_rules": [],
        }
        mgr.apply_update(result, scene_number=1)

        bible = storage.load()
        assert len(bible.glossary) == 1
        assert bible.glossary[0].term == "魔力"

    def test_apply_bible_update_world_rules(self, tmp_workdir):
        """_apply_bible_update should add new world rules."""
        from novel_forge.bible_manager import BibleManager
        storage = BibleStorage(tmp_workdir)
        mgr = BibleManager(storage)

        result = {
            "characters": [],
            "foreshadowing": [],
            "relationships": [],
            "subplots": [],
            "glossary": [],
            "world_rules": [
                {"rule": "魔法には代償が必要"},
            ],
        }
        mgr.apply_update(result, scene_number=1)

        bible = storage.load()
        assert len(bible.world_rules) == 1
        assert bible.world_rules[0] == "魔法には代償が必要"


# ── SceneWriter tests ─────────────────────────────────────────────────

class TestSceneWriter:
    def test_assemble_chapter(self, tmp_workdir):
        """assemble_chapter should create chapter file from scene texts."""
        from novel_forge.bible_manager import BibleManager
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        llm = MockLLMClient()
        prompts = MagicMock()
        prompts.render = MagicMock(return_value="prompt")
        quality = QualityGate()

        writer = SceneWriter(
            tmp_workdir, llm, prompts, quality, bb_storage, bible_storage,
        )

        chapter = MagicMock()
        chapter.number = 1
        chapter.title = "プロローグ"

        writer.assemble_chapter(1, chapter, ["シーン1の本文", "シーン2の本文"])

        ch_path = tmp_workdir / ".novel-forge" / "volumes" / "vol01" / "chapters" / "ch01.md"
        assert ch_path.exists()
        content = ch_path.read_text(encoding="utf-8")
        assert "プロローグ" in content
        assert "シーン1の本文" in content
        assert "シーン2の本文" in content

    def test_save_and_load_scene_draft(self, tmp_workdir):
        """save_scene_draft and load_scene_draft should roundtrip."""
        from novel_forge.bible_manager import BibleManager
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        llm = MockLLMClient()
        prompts = MagicMock()
        prompts.render = MagicMock(return_value="prompt")
        quality = QualityGate()

        writer = SceneWriter(
            tmp_workdir, llm, prompts, quality, bb_storage, bible_storage,
        )

        writer.save_scene_draft(1, 1, "テスト本文", chapter_number=1)
        loaded = writer.load_scene_draft(1, 1, chapter_number=1)
        assert loaded == "テスト本文"

    def test_load_scene_draft_missing(self, tmp_workdir):
        """load_scene_draft should return empty string for missing file."""
        bb_storage = BlackboardStorage(tmp_workdir)
        bible_storage = BibleStorage(tmp_workdir)
        llm = MockLLMClient()
        prompts = MagicMock()
        prompts.render = MagicMock(return_value="prompt")
        quality = QualityGate()

        writer = SceneWriter(
            tmp_workdir, llm, prompts, quality, bb_storage, bible_storage,
        )

        result = writer.load_scene_draft(99, 99, chapter_number=1)
        assert result == ""



# ── Quality Gate boundary tests ───────────────────────────────────────

class TestQualityGateBoundary:
    def test_score_exactly_70_passes(self):
        """Score exactly 70.0 should pass."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({"score": 70.0, "issues": []})
        assert result.passed is True

    def test_score_just_below_70_fails(self):
        """Score 69.9 should fail."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({"score": 69.9, "issues": []})
        assert result.passed is False

    def test_score_zero_fails(self):
        """Score 0.0 should fail."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({"score": 0.0, "issues": []})
        assert result.passed is False

    def test_score_100_passes(self):
        """Score 100.0 should pass."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({"score": 100.0, "issues": []})
        assert result.passed is True

    def test_critical_issue_fails_even_with_high_score(self):
        """Critical issue should fail even with score 100."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({
            "score": 100.0,
            "issues": [{"severity": "critical", "description": "重大な問題"}]
        })
        assert result.passed is False

    def test_warning_issue_passes_with_high_score(self):
        """Warning issue should not fail if score is high."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({
            "score": 80.0,
            "issues": [{"severity": "warning", "description": "軽微な問題"}]
        })
        assert result.passed is True

    def test_blocker_issue_fails(self):
        """Blocker issue should fail."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_scene({
            "score": 90.0,
            "issues": [{"severity": "blocker", "description": "ブロッカー"}]
        })
        assert result.passed is False

    def test_volume_check_force_exported_caps_at_50(self):
        """Volume with force_exported scenes should cap score at 50."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_volume([90.0, 95.0], force_exported_count=1)
        assert result["score"] <= 50.0

    def test_volume_check_no_force_exported(self):
        """Volume without force_exported should average scores."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_volume([80.0, 90.0], force_exported_count=0)
        assert result["score"] == 85.0

    def test_volume_check_empty_scores(self):
        """Volume with no scores should return 0."""
        from novel_forge.quality import QualityGate
        qg = QualityGate()
        result = qg.check_volume([], force_exported_count=0)
        assert result["score"] == 0.0


# ── Prompt input completeness tests ───────────────────────────────────

class TestPromptInputCompleteness:
    """Verify that review prompts receive all necessary information from generation prompts."""

    def test_series_plan_review_receives_world_rules(self, engine, mock_llm, tmp_workdir):
        """Series plan review should receive world rules in the plan text."""
        mock_llm.add_sequence("series_plan", _make_plan_response(
            world={"summary": "魔法世界", "rules": ["魔法が存在する", "魔力には限りがある"]}
        ))
        mock_llm.add_sequence("series_plan_review", _make_review_response(score=80))

        engine.plan("テスト")

        # Find the series_plan_review call
        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "series_plan_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "魔法が存在する" in review_prompt

    def test_series_plan_review_receives_character_arc(self, engine, mock_llm, tmp_workdir):
        """Series plan review should receive character arc info."""
        mock_llm.add_sequence("series_plan", _make_plan_response(
            main_characters=[{"name": "主人公", "role": "主人公", "arc": "成長から覚醒へ"}]
        ))
        mock_llm.add_sequence("series_plan_review", _make_review_response(score=80))

        engine.plan("テスト")

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "series_plan_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "成長から覚醒へ" in review_prompt

    def test_outline_review_receives_series_plan(self, engine, mock_llm, tmp_workdir):
        """Outline review should receive series plan context."""
        engine.plan("テスト")
        mock_llm._call_log.clear()

        # Set default responses (outline generates multiple LLM calls)
        mock_llm._responses["volume_outline"] = _make_outline_response()
        mock_llm._responses["scene_outline"] = {
            "title": "出会い",
            "goal": "主人公を紹介する",
            "outcome": "主人公が旅立つ",
            "conflict": "葛藤なし",
            "pov": "主人公",
            "characters": ["主人公"],
        }
        mock_llm._responses["volume_outline_review"] = _make_review_response(score=80)
        mock_llm._call_log.clear()

        engine.outline(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "volume_outline_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        # Should contain series plan info
        assert "テストシリーズ" in review_prompt or "あらすじ" in review_prompt

    def test_outline_review_receives_scene_goals(self, engine, mock_llm, tmp_workdir):
        """Outline review should receive scene goals and outcomes."""
        engine.plan("テスト")
        mock_llm._call_log.clear()

        # Set default responses (outline generates multiple LLM calls)
        mock_llm._responses["volume_outline"] = _make_outline_response()
        mock_llm._responses["scene_outline"] = {
            "title": "出会い",
            "goal": "主人公を紹介する",
            "outcome": "主人公が旅立つ",
            "conflict": "葛藤なし",
            "pov": "主人公",
            "characters": ["主人公"],
        }
        mock_llm._responses["volume_outline_review"] = _make_review_response(score=80)
        mock_llm._call_log.clear()

        engine.outline(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "volume_outline_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "主人公を紹介する" in review_prompt

    def test_scene_review_receives_subplots(self, engine, mock_llm, tmp_workdir):
        """Scene review should receive subplots info."""
        from novel_forge.models import SubplotItem

        engine.plan("テスト")
        engine.outline(volume_number=1)

        # Add a subplot to bible
        bible_storage = BibleStorage(tmp_workdir)
        bible = bible_storage.load()
        bible.subplots.append(SubplotItem(
            id="sp1", name="陰謀", status="in_progress", progress_note="進行中"
        ))
        bible_storage.save(bible)

        mock_llm._call_log.clear()
        engine.write(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "scene_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "陰謀" in review_prompt

    def test_scene_review_receives_relationships(self, engine, mock_llm, tmp_workdir):
        """Scene review should receive character relationships."""
        from novel_forge.models import RelationshipItem

        engine.plan("テスト")
        engine.outline(volume_number=1)

        # Add a relationship to bible
        bible_storage = BibleStorage(tmp_workdir)
        bible = bible_storage.load()
        bible.relationships.append(RelationshipItem(
            character_a="主人公", character_b="仲間",
            relationship_type="友人", status="良好"
        ))
        bible_storage.save(bible)

        mock_llm._call_log.clear()
        engine.write(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "scene_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "主人公" in review_prompt
        assert "仲間" in review_prompt


# ── Config generation test ────────────────────────────────────────────

class TestConfigGeneration:
    def test_ensure_config_creates_config(self, tmp_workdir, mock_llm):
        """plan() should auto-generate config.yaml if missing."""
        prompts = PromptManager(loader=PromptLoader(prompt_dir=tmp_workdir / "prompts"))
        eng = NovelEngine(
            workdir=tmp_workdir,
            model="test-model",
            llm_client=mock_llm,
            prompt_manager=prompts,
            config={"llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 0}},
        )

        config_path = tmp_workdir / "config.yaml"
        assert not config_path.exists()

        eng.plan("テスト")

        assert config_path.exists()

    def test_ensure_config_does_not_overwrite(self, tmp_workdir, mock_llm):
        """plan() should not overwrite existing config.yaml."""
        prompts = PromptManager(loader=PromptLoader(prompt_dir=tmp_workdir / "prompts"))
        eng = NovelEngine(
            workdir=tmp_workdir,
            model="test-model",
            llm_client=mock_llm,
            prompt_manager=prompts,
            config={"llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 0}},
        )

        config_path = tmp_workdir / "config.yaml"
        config_path.write_text("custom: true", encoding="utf-8")

        eng.plan("テスト")

        content = config_path.read_text(encoding="utf-8")
        assert "custom: true" in content
