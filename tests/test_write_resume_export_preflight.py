"""Tests for write resume and export preflight."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestWriteResumeCheckpoint:
    """write() should save state per-scene so interruptions don't lose progress."""

    def test_save_called_more_than_once_per_volume(self, tmp_path):
        """write() should checkpoint each completed scene before final volume save."""
        from novel_forge.engine.base import NovelEngineBase
        from novel_forge.models import ProjectState, SceneRecord, VolumeProgress
        from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

        (tmp_path / "series_plan.json").write_text(
            '{"title":"Test","genre":["fantasy"]}', encoding="utf-8"
        )
        engine = NovelEngineBase(
            workdir=tmp_path,
            phase="write",
            storage=StateStorage(tmp_path),
            bb_storage=BlackboardStorage(tmp_path),
            bible_storage=BibleStorage(tmp_path),
        )
        engine._state = ProjectState(series_title="Test", status="計画中", current_volume=1)
        vol = VolumeProgress(volume_number=1, status="計画中")
        for i in range(4):
            vol.scenes.append(SceneRecord(scene_number=i + 1, status="初稿済"))
        engine._state.volumes = [vol]

        design_data = {
            "title": "第1巻",
            "premise": "テスト",
            "chapters": [
                {
                    "number": 1,
                    "title": "第一章",
                    "purpose": "導入",
                    "scenes": [{"chapter_number": 1} for _ in range(4)],
                }
            ],
            "scenes": [
                {
                    "number": i + 1,
                    "chapter_number": 1,
                    "title": f"sc{i + 1}",
                    "goal": "目標",
                    "conflict": "葛藤",
                    "outcome": "結果",
                }
                for i in range(4)
            ],
        }
        engine._save_path(1, "vol01.json", design_data)

        call_count = 0

        def fake_json(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            kind = args[0] if args else kwargs.get("kind", "")
            if kind == "scene_draft":
                return {"title": f"シーン{call_count}", "content": "*" * 500}
            if kind == "review":
                return {
                    "ready_for_publication": True,
                    "overall_assessment": "問題なし",
                    "strengths": [],
                    "issues": [],
                }
            return {
                "summary": "要約",
                "bible_update": {},
            }

        engine._llm = MagicMock()
        engine._llm.complete_json = fake_json
        engine._scene_writer._llm = engine._llm
        engine._log.info = MagicMock()

        save_calls = []

        def track_save():
            save_calls.append([s.status for s in vol.scenes])

        engine._save = track_save  # type: ignore[assignment]

        from novel_forge.engine.write import write as write_fn

        results = write_fn(engine, volume_number=1)

        assert len(results) == 4
        assert len(save_calls) >= 5
        assert save_calls[0][0] == "修正済"
        assert all(status == "修正済" for status in save_calls[-1])


class TestExportPreflight:
    """export() should verify integrity before writing KDP artifacts."""

    def test_export_rejects_missing_scene_draft(self, tmp_path):
        """If a designed scene draft file is missing, export should stop."""
        from novel_forge.engine.base import NovelEngineBase
        from novel_forge.models import ProjectState, SceneRecord, VolumeProgress
        from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

        (tmp_path / "series_plan.json").write_text(
            '{"title":"T","genre":["fantasy"]}', encoding="utf-8"
        )
        vol_dir = tmp_path / "vol01" / "vol01_ch01"
        vol_dir.mkdir(parents=True)

        engine = NovelEngineBase(
            workdir=tmp_path,
            phase="export",
            storage=StateStorage(tmp_path),
            bb_storage=BlackboardStorage(tmp_path),
            bible_storage=BibleStorage(tmp_path),
        )
        engine._state = ProjectState(series_title="Test", status="初稿済", current_volume=1)
        vol = VolumeProgress(volume_number=1, status="初稿済")
        for i in range(4):
            vol.scenes.append(SceneRecord(scene_number=i + 1, status="修正済"))
        engine._state.volumes = [vol]

        # Write only scenes 1-3; scene 4 should be missing.
        for scene_number in range(1, 4):
            (tmp_path / "vol01" / "vol01_ch01" / f"vol01_ch01_sc{scene_number:02d}_v1.md").write_text(
                f"シーン{scene_number}", encoding="utf-8"
            )

        vol_design = {
            "title": "Vol1",
            "premise": "T",
            "chapters": [
                {
                    "number": 1,
                    "scenes": [
                        {"chapter_number": 1, "scene_number": n} for n in range(1, 4)
                    ],
                },
                {"number": 2, "scenes": [{"chapter_number": 2, "scene_number": 4}]},
            ],
            "scenes": [
                {"number": n, "chapter_number": 1, "title": f"シーン{n}"}
                for n in range(1, 4)
            ]
            + [{"number": 4, "chapter_number": 2, "title": "シーン4"}],
        }
        engine._save_path(1, "vol01.json", vol_design)

        from novel_forge.engine.export import export as export_fn

        with pytest.raises(ValueError, match="missing scene draft"):
            export_fn(engine, volume_number=1)

    def test_export_rejects_empty_scene_draft(self, tmp_path):
        """If a designed scene draft file is empty, export should stop."""
        from novel_forge.engine.base import NovelEngineBase
        from novel_forge.models import ProjectState, SceneRecord, VolumeProgress
        from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

        (tmp_path / "series_plan.json").write_text(
            '{"title":"T","genre":["fantasy"]}', encoding="utf-8"
        )
        ch_dir = tmp_path / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01_v1.md").write_text("   \n", encoding="utf-8")

        engine = NovelEngineBase(
            workdir=tmp_path,
            phase="export",
            storage=StateStorage(tmp_path),
            bb_storage=BlackboardStorage(tmp_path),
            bible_storage=BibleStorage(tmp_path),
        )
        engine._state = ProjectState(series_title="Test", status="初稿済", current_volume=1)
        vol = VolumeProgress(volume_number=1, status="初稿済")
        vol.scenes.append(SceneRecord(scene_number=1, status="修正済"))
        engine._state.volumes = [vol]
        engine._save_path(
            1,
            "vol01.json",
            {
                "title": "Vol1",
                "premise": "T",
                "chapters": [{"number": 1, "scenes": [{"chapter_number": 1, "scene_number": 1}]}],
                "scenes": [{"number": 1, "chapter_number": 1, "title": "シーン1"}],
            },
        )

        from novel_forge.engine.export import export as export_fn

        with pytest.raises(ValueError, match="empty scene draft"):
            export_fn(engine, volume_number=1)

    def test_export_rejects_incomplete_scene_status(self, tmp_path):
        """If a scene is not revised or force-exported, export should stop."""
        from novel_forge.engine.base import NovelEngineBase
        from novel_forge.models import ProjectState, SceneRecord, VolumeProgress
        from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

        (tmp_path / "series_plan.json").write_text(
            '{"title":"T","genre":["fantasy"]}', encoding="utf-8"
        )
        ch_dir = tmp_path / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01.md").write_text("第一章", encoding="utf-8")

        engine = NovelEngineBase(
            workdir=tmp_path,
            phase="export",
            storage=StateStorage(tmp_path),
            bb_storage=BlackboardStorage(tmp_path),
            bible_storage=BibleStorage(tmp_path),
        )
        engine._state = ProjectState(series_title="Test", status="初稿済", current_volume=1)
        vol = VolumeProgress(volume_number=1, status="初稿済")
        vol.scenes.append(SceneRecord(scene_number=1, status="初稿済"))
        engine._state.volumes = [vol]
        engine._save_path(
            1,
            "vol01.json",
            {
                "title": "Vol1",
                "premise": "T",
                "chapters": [{"number": 1, "scenes": [{"chapter_number": 1}]}],
                "scenes": [],
            },
        )

        from novel_forge.engine.export import export as export_fn

        with pytest.raises(ValueError, match="incomplete scenes: 1"):
            export_fn(engine, volume_number=1)

    def test_export_rejects_semantically_invalid_volume_design(self, tmp_path):
        """Export preflight should reject duplicate final design scene numbers."""
        from novel_forge.engine.base import NovelEngineBase
        from novel_forge.models import ProjectState, SceneRecord, VolumeProgress
        from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

        (tmp_path / "series_plan.json").write_text(
            '{"title":"T","genre":["fantasy"]}', encoding="utf-8"
        )
        ch_dir = tmp_path / "vol01" / "vol01_ch01"
        ch_dir.mkdir(parents=True)
        (ch_dir / "vol01_ch01_sc01_v1.md").write_text("シーン1", encoding="utf-8")
        (ch_dir / "vol01_ch01_sc02_v1.md").write_text("シーン2", encoding="utf-8")

        engine = NovelEngineBase(
            workdir=tmp_path,
            phase="export",
            storage=StateStorage(tmp_path),
            bb_storage=BlackboardStorage(tmp_path),
            bible_storage=BibleStorage(tmp_path),
        )
        engine._state = ProjectState(series_title="Test", status="初稿済", current_volume=1)
        vol = VolumeProgress(volume_number=1, status="初稿済")
        vol.scenes.extend(
            [
                SceneRecord(scene_number=1, status="修正済"),
                SceneRecord(scene_number=2, status="修正済"),
            ]
        )
        engine._state.volumes = [vol]
        engine._save_path(
            1,
            "vol01.json",
            {
                "title": "Vol1",
                "premise": "T",
                "chapters": [
                    {
                        "number": 1,
                        "scenes": [
                            {"number": 1, "chapter_number": 1},
                            {"number": 2, "chapter_number": 1},
                        ],
                    }
                ],
                "scenes": [
                    {"number": 1, "chapter_number": 1, "title": "シーン1"},
                    {"number": 1, "chapter_number": 1, "title": "シーン2"},
                ],
            },
        )

        from novel_forge.engine.export import export as export_fn

        with pytest.raises(ValueError, match="duplicate scene number: 1"):
            export_fn(engine, volume_number=1)
