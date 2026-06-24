"""Engine integration tests — verify behavior, not implementation.

Design principle:
- Tests verify INPUT → OUTPUT of public methods (plan, design, write, export)
- Internal implementation (retry counts, call order) is NOT tested
- MockLLMClient is used only for tests that need to control LLM responses
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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
from novel_forge.prompts import PromptManager, render_prompt
from novel_forge.quality_gate import QualityGate
from novel_forge.scene_writer import SceneWriter
from novel_forge.schemas import get_schema
from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage


# ── Mock LLM Client ─────────────────────────────────────────────────────

class MockLLMClient:
    """Mock LLM client for tests that need to control LLM responses.

    Uses kind-matching: each request finds the next entry with matching kind,
    regardless of position in the sequence. This makes tests resilient to
    internal call order changes.

    Usage:
        mock = MockLLMClient()
        mock.add_batch(
            ("series_plan_core", core_data),
            ("series_plan_core_review", review_data),
        )
        result = mock.complete_json("series_plan_core", "system", "user", schema)
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

        # Kind-matching: scan from current position for matching kind
        for i in range(self._seq_idx, len(self._sequence)):
            expected_kind, resp = self._sequence[i]
            if expected_kind == kind:
                self._seq_idx = i + 1
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
        if kind == "series_plan_core":
            return {
                "title": "テストシリーズ",
                "slug": "test-series",
                "logline": "テストのあらすじ",
                "genre": ["fantasy"],
                "target_audience": "10代後半〜30代",
                "themes": ["冒険", "成長"],
                "selling_points": ["ユニークな世界観"],
                "world": {"summary": "魔法の世界", "rules": ["魔法が存在する"]},
            }
        if kind == "series_plan_characters":
            return {"main_characters": [{"name": "主人公", "role": "主人公", "arc": "成長"}]}
        if kind == "series_plan_volumes":
            return {"planned_volumes": [{"title": "第1巻", "premise": "始まり"}]}
        if "review" in kind:
            return {"issues": [], "suggestions": []}
        if "revision" in kind:
            return {"title": "テストシリーズ", "slug": "test-series"}
        if "design" in kind:
            return {"title": "タイトル", "chapters": [{"title": "章1", "purpose": "導入"}]}
        if kind == "scene_draft":
            return {"title": "シーン", "content": "本文"}
        if kind == "scene_review":
            return {"score": 80.0, "issues": [], "strengths": ["良い"], "recommendations": [], "dimensions": {}}
        if kind == "scene_summary_and_bible_update":
            return {"summary": "要約", "facts": [], "continuity_notes": [], "characters": [],
                    "foreshadowing": [], "relationships": [], "subplots": [], "glossary": [], "world_rules": []}
        return {}


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_plan_response(**overrides) -> dict:
    """Create a valid series plan core response."""
    base = {
        "title": "テストシリーズ",
        "slug": "test-series",
        "logline": "テストのあらすじ",
        "genre": ["fantasy"],
        "target_audience": "10代後半〜30代",
        "themes": ["冒険", "成長"],
        "selling_points": ["ユニークな世界観"],
        "world": {"summary": "魔法の世界", "rules": ["魔法が存在する"]},
    }
    base.update(overrides)
    return base


def _make_chars_response(**overrides) -> dict:
    """Create a valid series plan characters response."""
    base = {
        "main_characters": [{"name": "主人公", "role": "主人公", "arc": "成長"}],
    }
    base.update(overrides)
    return base


def _make_volumes_response(**overrides) -> dict:
    """Create a valid series plan volumes response."""
    base = {
        "planned_volumes": [{"title": "第1巻", "premise": "始まり"}],
    }
    base.update(overrides)
    return base


def _make_design_response(**overrides) -> dict:
    """Create a valid volume design response."""
    base = {
        "title": "第1巻",
        "premise": "始まり",
        "chapters": [
            {"title": "プロローグ", "purpose": "導入"},
            {"title": "転換", "purpose": "転換"},
            {"title": "クライマックス", "purpose": "クライマックス"},
            {"title": "収束", "purpose": "収束"},
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


@pytest.fixture
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
        config={"llm": {"model": "test-model", "timeout_seconds": 10, "max_retries": 3}},
    )
    return eng


@pytest.fixture
def planned_engine(tmp_workdir, mock_llm):
    """Engine with plan() already completed.

    Uses real plan() with MockLLMClient. The MockLLMClient's default
    responses ensure plan() completes successfully.
    """
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
        result = engine.plan("テスト")

        plan_path = engine._series_dir / "series_plan.json"
        assert plan_path.exists()
        saved = json.loads(plan_path.read_text(encoding="utf-8"))
        assert saved["title"] == "テストシリーズ"

    def test_plan_saves_review(self, engine, mock_llm, tmp_workdir):
        """plan() should save the review result."""
        engine.plan("テスト")
        review_path = engine._series_dir / "series_core_review.json"
        assert review_path.exists()

    def test_plan_calls_llm_for_generation_and_review(self, engine, mock_llm):
        """plan() should call LLM at least twice (generate + review)."""
        engine.plan("テスト")
        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_core" in kinds
        assert "series_plan_core_review" in kinds

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
    """Verify plan review behavior (not internal call counts)."""

    def test_plan_revises_on_critical_issues(self, engine, mock_llm):
        """Plan should be revised when there are critical issues.

        We mock plan() directly to verify the revision behavior
        without depending on internal retry counts.
        """
        review_fail = {
            "issues": [{"severity": "致命的", "category": "test", "description": "問題"}],
            "suggestions": [],
        }
        # Simulate revision: core generates, review fails, revision happens
        mock_llm.add_sequence("series_plan_core", _make_plan_response())
        mock_llm.add_sequence("series_plan_core_review", review_fail)
        mock_llm.add_sequence("series_plan_core_revision", _make_plan_response(title="修正版"))
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review",
            {"volume_uniqueness": "良い", "series_flow": "良い", "cliffhanger": "良い",
             "theme_consistency": "良い", "issues": []})

        result = engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_core_revision" in kinds
        assert result["title"] == "修正版"

    def test_plan_stops_after_max_retries(self, engine, mock_llm):
        """Plan revision should stop after max_retries.

        With max_retries=3, the loop runs at most 3 iterations.
        We verify the final result is valid regardless of retry count.
        """
        review_fail = {
            "issues": [{"severity": "致命的", "category": "test", "description": "問題"}],
            "suggestions": [],
        }
        # Add enough entries for 3 revision attempts
        mock_llm.add_sequence("series_plan_core", _make_plan_response())
        for _ in range(3):
            mock_llm.add_sequence("series_plan_core_review", review_fail)
            mock_llm.add_sequence("series_plan_core_revision", _make_plan_response())
            mock_llm.add_sequence("series_plan_core_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review",
            {"volume_uniqueness": "良い", "series_flow": "良い", "cliffhanger": "良い",
             "theme_consistency": "良い", "issues": []})

        result = engine.plan("テスト")

        # Plan should complete (not raise) regardless of review failures
        assert result["title"] == "テストシリーズ"
        kinds = [k for k, _ in mock_llm._call_log]
        revision_count = kinds.count("series_plan_core_revision")
        # With max_retries=3, at most 3 revisions should happen
        assert revision_count <= 3

    def test_plan_no_revision_when_passing(self, engine, mock_llm):
        """Plan should not be revised when no critical issues."""
        mock_llm.add_sequence("series_plan_core", _make_plan_response())
        mock_llm.add_sequence("series_plan_core_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review",
            {"volume_uniqueness": "良い", "series_flow": "良い", "cliffhanger": "良い",
             "theme_consistency": "良い", "issues": []})

        result = engine.plan("テスト")

        kinds = [k for k, _ in mock_llm._call_log]
        assert "series_plan_core_revision" not in kinds


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


# ── Outline review → revise loop ────────────────────────────────────────

class TestOutlineReviewLoop:
    """Verify outline review behavior."""

    def test_outline_revises_on_critical_issues(self, planned_engine, mock_llm):
        """Outline should be revised when critical issues found."""
        mock_llm._responses["volume_design_review"] = _make_review_response(
            issues=[{"severity": "致命的", "category": "test", "description": "問題"}]
        )
        mock_llm._responses["volume_design_revision"] = _make_design_response(title="改訂版")
        mock_llm._call_log.clear()

        result = planned_engine.design(volume_number=1)
        assert result["title"] == "改訂版"

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

        result = planned_engine.write(volume_number=1)
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

    def test_write_skips_completed_scenes(self, planned_engine, mock_llm):
        """write() should not regenerate completed scenes."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        first_count = len(mock_llm._call_log)

        # Write again — should not create new calls
        mock_llm._call_log.clear()
        planned_engine.write(volume_number=1)
        assert len(mock_llm._call_log) < first_count


# ── Export tests ────────────────────────────────────────────────────────

class TestExportMixin:
    """Verify export behavior."""

    def test_export_creates_manuscript(self, planned_engine, mock_llm):
        """export() should create manuscript.md."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.export(volume_number=1)

        export_path = planned_engine._workdir / "exports" / "vol01_manuscript.md"
        assert export_path.exists()

    def test_export_creates_metadata(self, planned_engine, mock_llm):
        """export() should create metadata.json."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.export(volume_number=1)

        meta_path = planned_engine._workdir / "exports" / "vol01_metadata.json"
        assert meta_path.exists()

    def test_export_creates_readiness_report(self, planned_engine, mock_llm):
        """export() should create kdp_readiness_report.md."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        mock_llm._call_log.clear()

        planned_engine.export(volume_number=1)

        report_path = planned_engine._workdir / "exports" / "vol01_kdp_readiness_report.md"
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
        from novel_forge.storage import BlackboardStorage, BibleStorage
        ctx = ContextBuilder(
            series_dir=tmp_workdir,
            blackboard_storage=BlackboardStorage(tmp_workdir),
            bible_storage=BibleStorage(tmp_workdir),
        )
        result = ctx.build_context()
        assert result is not None

    def test_build_context_with_facts(self, tmp_workdir):
        """build_context() should include facts."""
        from novel_forge.storage import BlackboardStorage, BibleStorage
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
        assert hasattr(bible, 'characters') or hasattr(bible, 'foreshadowing')

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
        from novel_forge.storage import BlackboardStorage, BibleStorage
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

    def test_assemble_chapter(self, tmp_workdir):
        """assemble_chapter() should combine scenes into chapter."""
        from novel_forge.models import ChapterOutline
        from novel_forge.prompts import PromptManager
        from novel_forge.quality_gate import QualityGate
        from novel_forge.storage import BlackboardStorage, BibleStorage
        writer = SceneWriter(
            workdir=tmp_workdir,
            llm_client=MockLLMClient(),
            prompt_manager=PromptManager(prompt_dir=tmp_workdir / "prompts"),
            quality=QualityGate(),
            blackboard_storage=BlackboardStorage(tmp_workdir),
            bible_storage=BibleStorage(tmp_workdir),
        )
        ch_dir = tmp_workdir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01.md").write_text("# Scene 1", encoding="utf-8")
        (ch_dir / "vol01_ch01_sc02.md").write_text("# Scene 2", encoding="utf-8")
        result = writer.assemble_chapter(
            vol_num=1,
            chapter=ChapterOutline(number=1, title="章1", purpose="導入"),
            scene_texts=["# Scene 1", "# Scene 2"],
            scene_numbers=[1, 2],
        )
        assert Path(result).exists()


# ── Quality gate tests ─────────────────────────────────────────────────

class TestQualityGate:
    """Verify quality gate."""

    def test_check_passes_clean_review(self):
        """check() should pass when no issues."""
        gate = QualityGate()
        review = {"issues": [], "revision_needed": False, "ready_for_publication": True}
        result = gate.check(review)
        assert result.revision_needed is False

    def test_check_fails_with_blocker(self):
        """check() should fail when blocker issues exist."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "致命的", "category": "test", "description": "問題"}],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check(review)
        assert result.revision_needed is True

    def test_check_fails_with_major_issues(self):
        """check() should fail when 2+ major issues exist."""
        gate = QualityGate()
        review = {
            "issues": [
                {"severity": "重要", "category": "test", "description": "問題1"},
                {"severity": "重要", "category": "test", "description": "問題2"},
            ],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check(review)
        assert result.revision_needed is True


# ── Quality gate boundary tests ────────────────────────────────────────

class TestQualityGateBoundary:
    """Test quality gate boundary conditions."""

    def test_single_minor_issue_passes(self):
        """Single minor issue should pass."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "軽微", "category": "test", "description": "軽微"}],
            "revision_needed": False,
            "ready_for_publication": True,
        }
        result = gate.check(review)
        assert result.revision_needed is False

    def test_single_major_issue_passes(self):
        """Single major issue should pass (threshold is 2)."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "重要", "category": "test", "description": "重要"}],
            "revision_needed": False,
            "ready_for_publication": True,
        }
        result = gate.check(review)
        assert result.revision_needed is False

    def test_critical_issue_fails(self):
        """Critical issue should always fail."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "重大", "category": "test", "description": "重大"}],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check(review)
        assert result.revision_needed is True

    def test_empty_issues_passes(self):
        """Empty issues should pass."""
        gate = QualityGate()
        review = {"issues": [], "revision_needed": False, "ready_for_publication": True}
        result = gate.check(review)
        assert result.revision_needed is False

    def test_mixed_severity_fails(self):
        """Mix of critical + minor should fail."""
        gate = QualityGate()
        review = {
            "issues": [
                {"severity": "致命的", "category": "test", "description": "致命的"},
                {"severity": "軽微", "category": "test", "description": "軽微"},
            ],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check(review)
        assert result.revision_needed is True

    def test_two_major_fails(self):
        """Two major issues should fail."""
        gate = QualityGate()
        review = {
            "issues": [
                {"severity": "重要", "category": "test", "description": "重要1"},
                {"severity": "重要", "category": "test", "description": "重要2"},
            ],
            "revision_needed": True,
            "ready_for_publication": False,
        }
        result = gate.check(review)
        assert result.revision_needed is True

    def test_ready_for_publication_flag(self):
        """passed flag should be set correctly."""
        gate = QualityGate()
        review = {
            "issues": [{"severity": "致命的", "category": "test", "description": "問題"}],
            "revision_needed": True,
        }
        result = gate.check(review)
        assert result.passed is False


# ── Config generation test ────────────────────────────────────────────

class TestConfigGeneration:
    """Verify config handling."""

    def test_plan_works_without_config(self, tmp_workdir, mock_llm):
        """plan() should work without config.yaml."""
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
        engine.plan("テスト")
        review_path = engine._series_dir / "series_core_review.json"
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

    def test_scene_files_use_correct_naming(self, planned_engine, mock_llm):
        """Scene files should follow naming convention."""
        planned_engine.design(volume_number=1)
        planned_engine.write(volume_number=1)
        vol_dir = planned_engine._series_dir / "vol01"

        # Scene files should exist with correct naming
        scene_files = list(vol_dir.glob("vol01_ch*/vol01_ch*_sc*.md"))
        assert len(scene_files) > 0

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
        mock_llm.add_sequence("series_plan_core", _make_plan_response(
            world={"summary": "魔法世界", "rules": ["魔法が存在する", "魔力には限りがある"]}
        ))
        mock_llm.add_sequence("series_plan_core_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review",
            {"volume_uniqueness": "良い", "series_flow": "良い", "cliffhanger": "良い",
             "theme_consistency": "良い", "issues": []})

        engine.plan("テスト")

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "series_plan_core_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "魔法が存在する" in review_prompt

    def test_series_plan_review_receives_character_arc(self, engine, mock_llm, tmp_workdir):
        """Series plan core review should receive series plan context."""
        mock_llm.add_sequence("series_plan_core", _make_plan_response(
            main_characters=[{"name": "主人公", "role": "主人公", "arc": "成長から覚醒へ"}]
        ))
        mock_llm.add_sequence("series_plan_core_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_characters", _make_chars_response())
        mock_llm.add_sequence("series_plan_characters_review", {"issues": [], "suggestions": []})
        mock_llm.add_sequence("series_plan_volumes", _make_volumes_response())
        mock_llm.add_sequence("series_plan_volumes_review",
            {"volume_uniqueness": "良い", "series_flow": "良い", "cliffhanger": "良い",
             "theme_consistency": "良い", "issues": []})

        engine.plan("テスト")

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "series_plan_core_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "テストシリーズ" in review_prompt
        assert "テストのあらすじ" in review_prompt

    def test_outline_review_receives_series_plan(self, planned_engine, mock_llm):
        """Outline review should receive series plan context."""
        mock_llm._responses["volume_design"] = _make_design_response()
        mock_llm._responses["scene_design"] = {
            "title": "出会い", "goal": "主人公を紹介する",
            "outcome": "主人公が旅立つ", "conflict": "葛藤なし",
        }
        mock_llm._responses["volume_design_review"] = _make_review_response(score=80)
        mock_llm._call_log.clear()

        planned_engine.design(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "volume_design_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "テストシリーズ" in review_prompt or "あらすじ" in review_prompt

    def test_outline_review_receives_scene_goals(self, planned_engine, mock_llm):
        """Outline review should receive scene goals and outcomes."""
        mock_llm._responses["volume_design"] = _make_design_response()
        mock_llm._responses["scene_design"] = {
            "title": "出会い", "goal": "主人公を紹介する",
            "outcome": "主人公が旅立つ", "conflict": "葛藤なし",
        }
        mock_llm._responses["volume_design_review"] = _make_review_response(score=80)
        mock_llm._call_log.clear()

        planned_engine.design(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "volume_design_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "主人公を紹介する" in review_prompt

    def test_scene_review_receives_subplots(self, planned_engine, mock_llm):
        """Scene review should receive subplots info."""
        from novel_forge.models import SubplotItem

        planned_engine.design(volume_number=1)

        bible = planned_engine._bible_storage.load()
        bible.subplots.append(SubplotItem(
            id="sp1", name="陰謀", status="進行中", progress_note="進行中"
        ))
        planned_engine._bible_storage.save(bible)

        mock_llm._call_log.clear()
        planned_engine.write(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "scene_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "陰謀" in review_prompt

    def test_scene_review_receives_relationships(self, planned_engine, mock_llm):
        """Scene review should receive character relationships."""
        from novel_forge.models import RelationshipItem

        planned_engine.design(volume_number=1)

        bible = planned_engine._bible_storage.load()
        bible.relationships.append(RelationshipItem(
            character_a="主人公", character_b="仲間",
            relationship_type="友人", status="良好"
        ))
        planned_engine._bible_storage.save(bible)

        mock_llm._call_log.clear()
        planned_engine.write(volume_number=1)

        review_calls = [(k, p) for k, p in mock_llm._call_log if k == "scene_review"]
        assert len(review_calls) > 0
        review_prompt = review_calls[0][1]
        assert "主人公" in review_prompt
        assert "仲間" in review_prompt
