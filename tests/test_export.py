"""Tests for engine/export.py — manuscript assembly, KDP metadata, readiness report."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from novel_forge.models import (
    Bible,
    Blackboard,
    CharacterProfile,
    ForeshadowingItem,
    SceneRecord,
    SubplotItem,
    VolumeProgress,
)


# ── ExportMixin のテスト (engine/export.py) ─────────────────────────────

class TestExportMixin:
    """Test ExportMixin methods via a minimal mock engine."""

    @pytest.fixture
    def mock_engine(self, tmp_path):
        """Create a minimal engine-like object with ExportMixin methods."""
        from novel_forge.bible_manager import BibleManager
        from novel_forge.storage import BibleStorage, BlackboardStorage

        engine = MagicMock()
        engine._workdir = tmp_path
        engine._series_dir = tmp_path / "series"
        engine._series_dir.mkdir(parents=True, exist_ok=True)
        engine._lang = "ja"

        # State
        engine._state = MagicMock()
        engine._state.series_title = "テストシリーズ"
        engine._state.current_volume = 1
        engine._state.status = "初稿済"

        # Volume
        vol = VolumeProgress(volume_number=1, status="初稿済")
        vol.scenes = [
            SceneRecord(scene_number=1, status="修正済"),
            SceneRecord(scene_number=2, status="修正済"),
        ]
        engine._current_volume = MagicMock(return_value=vol)

        # Storage
        bb_storage = BlackboardStorage(engine._series_dir)
        bible_storage = BibleStorage(engine._series_dir)
        engine._bb_storage = bb_storage
        engine._bible_mgr = BibleManager(bible_storage)

        # Bible with foreshadowing and subplots
        bible = Bible(
            foreshadowing=[
                ForeshadowingItem(description="剣の秘密", resolved=True),
                ForeshadowingItem(description="正体", resolved=False),
            ],
            subplots=[
                SubplotItem(id="sp1", name="陰謀", status="進行中", progress_note="進行中"),
            ],
        )
        bible_storage.save(bible)

        # Series plan
        plan_path = engine._series_dir / "series_plan.json"
        plan_path.write_text(
            json.dumps({"title": "テストシリーズ", "genre": ["fantasy"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        # Chapter files
        ch_dir = engine._series_dir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True, exist_ok=True)
        (ch_dir / "vol01_ch01.md").write_text("# 第1章\n\n本文です。", encoding="utf-8")

        # Bind real methods
        from novel_forge.engine.export import ExportMixin
        engine.export = ExportMixin.export.__get__(engine)
        engine._assemble_manuscript = ExportMixin._assemble_manuscript.__get__(engine)
        engine._generate_kdp_metadata = ExportMixin._generate_kdp_metadata.__get__(engine)
        engine._generate_readiness_report = ExportMixin._generate_readiness_report.__get__(engine)

        return engine

    def test_assemble_manuscript(self, mock_engine):
        """_assemble_manuscript should join chapter files with separator."""
        result = mock_engine._assemble_manuscript(1)
        assert "本文です" in result
        assert "---" in result

    def test_assemble_manuscript_saves_file(self, mock_engine):
        """_assemble_manuscript should save to exports/."""
        mock_engine._assemble_manuscript(1)
        export_path = mock_engine._workdir / "exports" / "vol01_manuscript.md"
        assert export_path.exists()

    def test_generate_kdp_metadata(self, mock_engine):
        """_generate_kdp_metadata should create metadata JSON."""
        result = mock_engine._generate_kdp_metadata(1)
        assert result["title"] == "テストシリーズ"
        assert result["volume"] == 1
        assert result["language"] == "ja"

    def test_generate_kdp_metadata_saves_file(self, mock_engine):
        mock_engine._generate_kdp_metadata(1)
        meta_path = mock_engine._workdir / "exports" / "vol01_metadata.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["title"] == "テストシリーズ"

    def test_generate_readiness_report(self, mock_engine):
        """_generate_readiness_report should include summary and warnings."""
        result = mock_engine._generate_readiness_report(1)
        assert "テストシリーズ" in result
        assert "KDP 準備完了レポート" in result
        # Unresolved foreshadowing
        assert "正体" in result
        # Incomplete subplots
        assert "陰謀" in result

    def test_generate_readiness_report_no_warnings_when_clean(self, mock_engine):
        """Report should not have warnings when everything is resolved."""
        # Resolve all foreshadowing and complete subplots
        bible = mock_engine._bible_storage.load()
        for fh in bible.foreshadowing:
            fh.resolved = True
        for sp in bible.subplots:
            sp.status = "completed"
        mock_engine._bible_storage.save(bible)

        # Reset scenes to all revised
        vol = mock_engine._current_volume()
        for s in vol.scenes:
            s.status = "修正済"

        result = mock_engine._generate_readiness_report(1)
        assert "未回収伏線" not in result
        assert "未完了サブプロット" not in result

    def test_generate_readiness_report_force_exported_warning(self, mock_engine):
        """Report should warn about force-exported scenes."""
        vol = mock_engine._current_volume()
        vol.scenes[0].status = "強制出力済"

        result = mock_engine._generate_readiness_report(1)
        assert "⚠️ 警告" in result
        assert "シーン 1" in result

    def test_export_returns_paths(self, mock_engine):
        """export() should return dict with manuscript/metadata/report paths."""
        result = mock_engine.export(1)
        assert "manuscript_path" in result
        assert "metadata_path" in result
        assert "report_path" in result

    def test_export_sets_status(self, mock_engine):
        """export() should set volume status to 出力済."""
        mock_engine.export(1)
        vol = mock_engine._current_volume()
        assert vol.status == "出力済"

    def test_export_force_exported_status(self, mock_engine):
        """export() should set 強制出力済 if any scene is force-exported."""
        vol = mock_engine._current_volume()
        vol.scenes[0].status = "強制出力済"
        mock_engine.export(1)
        vol = mock_engine._current_volume()
        assert vol.status == "強制出力済"


# ── Resume tests (export.py) ───────────────────────────────────────────

class TestResume:
    """Test resume() method via mock engine."""

    @pytest.fixture
    def mock_engine(self, tmp_path):
        from novel_forge.engine.export import ExportMixin

        engine = MagicMock()
        engine._state = MagicMock()
        engine._state.status = "計画中"
        engine._state.current_volume = 1

        vol = VolumeProgress(volume_number=1, status="計画中")
        engine._current_volume = MagicMock(return_value=vol)

        engine.resume = ExportMixin.resume.__get__(engine)
        return engine

    def test_resume_when_drafting(self, mock_engine):
        mock_engine._state.status = "計画中"
        result = mock_engine.resume()
        assert result["action"] == "plan"

    def test_resume_when_outlined(self, mock_engine):
        mock_engine._state.status = "デザイン済"
        result = mock_engine.resume()
        assert result["action"] == "design"

    def test_resume_when_exported(self, mock_engine):
        mock_engine._state.status = "出力済"
        result = mock_engine.resume()
        assert result["action"] == "export"

    def test_resume_when_force_exported(self, mock_engine):
        mock_engine._state.status = "強制出力済"
        result = mock_engine.resume()
        assert result["action"] == "export"

    def test_resume_volume_writing_takes_priority(self, mock_engine):
        """Volume 執筆中 should take priority over state デザイン済."""
        mock_engine._state.status = "デザイン済"
        vol = mock_engine._current_volume()
        vol.status = "執筆中"
        result = mock_engine.resume()
        assert result["action"] == "write"


# ── Status tests (export.py) ───────────────────────────────────────────

class TestStatus:
    """Test status() method."""

    @pytest.fixture
    def mock_engine(self, tmp_path):
        from novel_forge.engine.export import ExportMixin

        engine = MagicMock()
        engine._state = MagicMock()
        engine._state.series_title = "テスト"
        engine._state.status = "執筆中"
        engine._state.current_volume = 1

        vol = VolumeProgress(volume_number=1, status="執筆中", word_count=5000, target_word_count=8000)
        vol.scenes = [
            SceneRecord(scene_number=1, status="修正済"),
            SceneRecord(scene_number=2, status="執筆中"),
        ]
        engine._current_volume = MagicMock(return_value=vol)

        engine.status = ExportMixin.status.__get__(engine)
        return engine

    def test_status_returns_all_fields(self, mock_engine):
        result = mock_engine.status()
        assert result["series_title"] == "テスト"
        assert result["status"] == "執筆中"
        assert result["current_volume"] == 1
        assert result["volume_status"] == "執筆中"
        assert result["word_count"] == 5000
        assert result["target_word_count"] == 8000
        assert result["scenes_total"] == 2
        assert result["scenes_revised"] == 1
        assert result["scenes_force_exported"] == 0
