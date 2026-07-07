"""Tests for scene_writer.py — load_scene_draft, assemble_chapter."""

from types import SimpleNamespace

import pytest

from novel_forge.llm_client import LLMError
from novel_forge.quality_gate import QualityGate
from novel_forge.storage import BibleStorage, BlackboardStorage


class TestLoadSceneDraft:
    """Tests for SceneWriter.load_scene_draft with version=0 support."""

    def _make_writer(self, tmp_path):
        from novel_forge.llm_client import LLMClient
        from novel_forge.prompts import PromptManager
        from novel_forge.scene_writer import SceneWriter

        series_dir = tmp_path / "series"
        series_dir.mkdir()
        bb = BlackboardStorage(series_dir)
        bible = BibleStorage(series_dir)
        return SceneWriter(
            workdir=tmp_path,
            llm_client=LLMClient(api_url="http://localhost:11434/api/chat", model="test"),
            prompt_manager=PromptManager(),
            quality=QualityGate(max_retries=2),
            blackboard_storage=bb,
            bible_storage=bible,
            series_dir=series_dir,
        )

    def test_load_v1(self, tmp_path):
        writer = self._make_writer(tmp_path)
        ch_dir = writer._series_dir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01_v1.md").write_text("draft v1", encoding="utf-8")
        result = writer.load_scene_draft(1, 1, 1)
        assert result == "draft v1"

    def test_load_v2_over_v1(self, tmp_path):
        writer = self._make_writer(tmp_path)
        ch_dir = writer._series_dir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01_v1.md").write_text("draft v1", encoding="utf-8")
        (ch_dir / "vol01_ch01_sc01_v2.md").write_text("draft v2", encoding="utf-8")
        result = writer.load_scene_draft(1, 1, 1)
        assert result == "draft v2"

    def test_load_version0_plain(self, tmp_path):
        """version=0 (no suffix) file should be loaded as fallback."""
        writer = self._make_writer(tmp_path)
        ch_dir = writer._series_dir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01.md").write_text("final draft", encoding="utf-8")
        result = writer.load_scene_draft(1, 1, 1)
        assert result == "final draft"

    def test_load_prefers_v1_over_plain(self, tmp_path):
        """v1 should be preferred over version=0 plain file."""
        writer = self._make_writer(tmp_path)
        ch_dir = writer._series_dir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01.md").write_text("plain", encoding="utf-8")
        (ch_dir / "vol01_ch01_sc01_v1.md").write_text("versioned", encoding="utf-8")
        result = writer.load_scene_draft(1, 1, 1)
        assert result == "versioned"

    def test_load_missing_returns_empty(self, tmp_path):
        writer = self._make_writer(tmp_path)
        result = writer.load_scene_draft(1, 99, 1)
        assert result == ""

    def test_load_missing_dir_returns_empty(self, tmp_path):
        writer = self._make_writer(tmp_path)
        result = writer.load_scene_draft(1, 1, 99)
        assert result == ""


class TestSceneReviewRetry:
    """Tests for SceneWriter review API retry behavior."""

    def test_review_api_retry_count_uses_transport_retries(self, tmp_path):
        """Scene review should not keep its own fixed retry count."""
        from novel_forge.scene_writer import SceneWriter

        class FakeLLM:
            transport_retries = 2

            def __init__(self):
                self.calls = 0

            def complete_json(self, *_args, **_kwargs):
                self.calls += 1
                raise LLMError("temporary transport failure")

        class FakePrompts:
            def render(self, name, values):
                return f"{name}:{sorted(values)}"

        llm = FakeLLM()
        series_dir = tmp_path / "series"
        series_dir.mkdir()
        writer = SceneWriter(
            workdir=tmp_path,
            llm_client=llm,
            prompt_manager=FakePrompts(),
            quality=QualityGate(max_retries=2),
            blackboard_storage=BlackboardStorage(series_dir),
            bible_storage=BibleStorage(series_dir),
            series_dir=series_dir,
        )
        ctx = SimpleNamespace(
            lang="ja",
            get_series_plan_summary_fn=lambda: "series",
            get_outline_summary_fn=lambda _design: "outline",
            build_context_fn=lambda: "context",
        )

        with pytest.raises(LLMError, match="temporary transport failure"):
            writer._call_review_api("draft", SimpleNamespace(), SimpleNamespace(), ctx)

        assert llm.calls == 2

