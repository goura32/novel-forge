"""Tests for engine/export.py — manuscript assembly, KDP metadata, readiness report."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from novel_forge.models import SceneRecord, VolumeProgress

# ── ExportMixin のテスト (engine/export.py) ─────────────────────────────


class TestExportMixin:
    """Test ExportMixin methods via a minimal mock engine."""

    @pytest.fixture
    def mock_engine(self, tmp_path):
        """Create a minimal engine-like object with ExportMixin methods."""
        engine = MagicMock()
        engine._workdir = tmp_path
        engine._series_dir = tmp_path / "series"
        engine._series_dir.mkdir(parents=True, exist_ok=True)
        engine._slug = "test_engine"
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

        # v2 Canon seed with foreshadowing and subplots (the single source of truth)
        canon_dir = engine._series_dir / "canon"
        canon_dir.mkdir(parents=True, exist_ok=True)
        from novel_forge.canon.models import Canon
        from novel_forge.canon.store import BibleFactory

        canon_seed = Canon.model_validate({
            "schema_version": 2,
            "series": {"id": "series", "title": "テストシリーズ"},
            "foreshadowing": [
                {"id": "fh_001", "description": "剣の秘密", "status": "resolved"},
                {"id": "fh_002", "description": "正体", "status": "planted"},
            ],
            "subplots": [
                {
                    "id": "sp_001",
                    "name": "陰謀",
                    "status": "active",
                    "dramatic_question": "誰が陰謀を巡らせているか",
                    "stakes": "王国の命運",
                    "current_state": "進行中",
                },
            ],
        })
        BibleFactory.write_seed(canon_dir, canon_seed)

        # Series plan
        plan_path = engine._series_dir / "series_plan.json"
        plan_path.write_text(
            json.dumps({"title": "テストシリーズ", "genre": ["fantasy"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        # Chapter files
        ch_dir = engine._series_dir / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True, exist_ok=True)
        (ch_dir / "vol01_ch01_sc01_v1.md").write_text("# 第1章\n\n本文です。", encoding="utf-8")
        engine._load_path = MagicMock(
            return_value={
                "title": "第1巻",
                "premise": "テスト",
                "chapters": [{"number": 1, "scenes": [{"chapter_number": 1}]}],
                "scenes": [{"number": 1, "chapter_number": 1, "title": "シーン1"}],
            }
        )

        # Bind real methods
        from novel_forge.engine.export import (
            _assemble_manuscript,
            _generate_kdp_metadata,
            _generate_readiness_report,
            _write_export,
            export,
        )

        engine.export = export.__get__(engine)
        engine._assemble_manuscript = _assemble_manuscript.__get__(engine)
        engine._write_export = _write_export.__get__(engine)
        engine._generate_kdp_metadata = _generate_kdp_metadata.__get__(engine)
        engine._generate_readiness_report = _generate_readiness_report.__get__(engine)

        return engine

    def test_assemble_manuscript(self, mock_engine):
        """_assemble_manuscript should join chapter files with separator."""
        result = mock_engine._assemble_manuscript(1)
        assert "本文です" in result
        # With only 1 chapter, no separator is needed
        assert "第1章" in result

    def test_assemble_manuscript_saves_file(self, mock_engine):
        """_assemble_manuscript should save to exports/."""
        mock_engine._assemble_manuscript(1)
        export_path = mock_engine._series_dir / "exports" / "test_engine_vol01.md"
        assert export_path.exists()

    def test_generate_kdp_metadata(self, mock_engine):
        """_generate_kdp_metadata should create metadata JSON."""
        result = mock_engine._generate_kdp_metadata(1)
        assert result["title"] == "テストシリーズ"
        assert result["volume"] == 1
        assert result["language"] == "ja"

    def test_generate_kdp_metadata_saves_file(self, mock_engine):
        mock_engine._generate_kdp_metadata(1)
        meta_path = mock_engine._series_dir / "exports" / "test_engine_vol01_metadata.json"
        assert meta_path.exists()
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        assert data["title"] == "テストシリーズ"

    def test_generate_readiness_report(self, mock_engine):
        """_generate_readiness_report should include summary and warnings.

        The warnings must be derived from the v2 Canon seed (canon/bible_seed.json),
        not a legacy bible.json — the planted foreshadowing '正体' and active
        subplot '陰謀' are seeded into the v2 Canon in the mock_engine fixture.
        """
        result = mock_engine._generate_readiness_report(1)
        assert "テストシリーズ" in result
        assert "KDP 人間確認レポート" in result
        assert "機械的な合否判定を行いません" in result
        # Unresolved foreshadowing (v2 Canon, status=planted)
        assert "正体" in result
        # Incomplete subplots (v2 Canon, status=active)
        assert "陰謀" in result

    def test_generate_readiness_report_no_warnings_when_clean(self, mock_engine):
        """Report should not have warnings when everything is resolved."""
        # All foreshadowing resolved, subplots completed — rewrite v2 Canon seed.
        from novel_forge.canon.models import Canon
        from novel_forge.canon.store import BibleFactory

        canon_dir = mock_engine._series_dir / "canon"
        canon_seed = Canon.model_validate({
            "schema_version": 2,
            "series": {"id": "series", "title": "テストシリーズ"},
            "foreshadowing": [
                {"id": "fh_001", "description": "剣の秘密", "status": "resolved"},
                {"id": "fh_002", "description": "正体", "status": "resolved"},
            ],
            "subplots": [],
        })
        BibleFactory.write_seed(canon_dir, canon_seed)

        # Reset scenes to all revised
        vol = mock_engine._current_volume()
        for s in vol.scenes:
            s.status = "修正済"

        result = mock_engine._generate_readiness_report(1)
        assert "未回収伏線" not in result
        assert "未完了サブプロット" not in result

    def test_generate_readiness_report_lists_human_review_issues(self, mock_engine):
        """Report is for human review, not a machine pass/fail decision."""
        vol = mock_engine._current_volume()
        vol.scenes[0].status = "強制出力済"
        vol.scenes[0].quality_gate = {
            "passed": False,
            "issues": [
                {
                    "severity": "critical",
                    "field": "pov.consistency",
                    "description": "POV が不自然に切り替わる可能性がある。",
                    "suggestion": "視点を統一する。",
                }
            ],
        }

        result = mock_engine._generate_readiness_report(1)

        assert "KDP 人間確認レポート" in result
        assert "機械的な合否判定を行いません" in result
        assert "最終レビュー指摘事項" in result
        assert "シーン 1 — 指摘 1件" in result
        assert "pov.consistency" in result
        assert "視点を統一する。" in result
        assert "シーン 2 — 指摘なし" in result
        assert "品質ゲート不合格" not in result
        assert "force_exported" not in result

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

    def test_export_keeps_output_status_with_review_notes(self, mock_engine):
        """Export status is not a machine quality verdict."""
        vol = mock_engine._current_volume()
        vol.scenes[0].status = "強制出力済"
        mock_engine.export(1)
        vol = mock_engine._current_volume()
        assert vol.status == "出力済"


# ── Resume tests (export.py) ───────────────────────────────────────────


class TestResume:
    """Test resume() method via mock engine."""

    @pytest.fixture
    def mock_engine(self, tmp_path):
        from novel_forge.engine.export import resume

        engine = MagicMock()
        engine._state = MagicMock()
        engine._state.status = "計画中"
        engine._state.current_volume = 1

        vol = VolumeProgress(volume_number=1, status="計画中")
        engine._current_volume = MagicMock(return_value=vol)

        engine.resume = resume.__get__(engine)
        return engine

    def test_resume_when_drafting(self, mock_engine):
        mock_engine._state.status = "計画中"
        result = mock_engine.resume()
        assert result["action"] == "plan"

    def test_resume_when_outlined(self, mock_engine):
        mock_engine._state.status = "デザイン済"
        result = mock_engine.resume()
        assert result["action"] == "design"

    def test_resume_when_planned(self, mock_engine):
        mock_engine._state.status = "企画済"
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
        from novel_forge.engine.export import status

        engine = MagicMock()
        engine._state = MagicMock()
        engine._state.series_title = "テスト"
        engine._state.status = "執筆中"
        engine._state.current_volume = 1

        vol = VolumeProgress(
            volume_number=1, status="執筆中", word_count=5000, target_word_count=8000
        )
        vol.scenes = [
            SceneRecord(scene_number=1, status="修正済"),
            SceneRecord(scene_number=2, status="初稿済"),
        ]
        engine._current_volume = MagicMock(return_value=vol)

        engine.status = status.__get__(engine)
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
