"""Tests for context_builder.py — context/continuity building for scene writing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from novel_forge.context_builder import ContextBuilder
from novel_forge.models import (
    Blackboard,
    ChapterOutline,
    SceneOutline,
    VolumeOutline,
)
from novel_forge.storage import BibleStorage, BlackboardStorage

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def series_dir(tmp_path):
    d = tmp_path / "series"
    d.mkdir()
    return d


@pytest.fixture
def bb_storage(series_dir):
    return BlackboardStorage(series_dir)


@pytest.fixture
def bible_storage(series_dir):
    return BibleStorage(series_dir)


@pytest.fixture
def builder(series_dir, bb_storage, bible_storage):
    return ContextBuilder(series_dir, bb_storage, bible_storage)


def _save_plan(series_dir: Path, data: dict) -> None:
    plan_path = series_dir / "series_plan.json"
    plan_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ── get_series_plan_summary ────────────────────────────────────────────


class TestGetSeriesPlanSummary:
    def test_returns_formatted_summary(self, builder, series_dir):
        _save_plan(
            series_dir,
            {
                "title": "テストシリーズ",
                "logline": "テストのあらすじ",
                "genre": ["fantasy"],
                "target_audience": "10代",
                "themes": ["冒険"],
                "world_summary": "魔法世界",
                "world_rules": ["魔法あり"],
                "main_characters": [{"name": "主人公", "role": "主人公", "arc": "成長"}],
                "planned_volumes": [{"title": "第1巻", "premise": "始まり"}],
            },
        )

        result = builder.get_series_plan_summary()
        assert "テストシリーズ" in result
        assert "テストのあらすじ" in result
        assert "魔法世界" in result
        assert "主人公" in result
        assert "第1巻" in result

    def test_empty_when_no_plan(self, builder):
        result = builder.get_series_plan_summary()
        assert result == ""

    def test_partial_data(self, builder, series_dir):
        _save_plan(series_dir, {"title": "最小限"})
        result = builder.get_series_plan_summary()
        assert "最小限" in result


# ── get_genre ───────────────────────────────────────────────────────────


class TestGetGenre:
    def test_returns_genre(self, builder, series_dir):
        _save_plan(series_dir, {"title": "T", "genre": "sf"})
        assert builder.get_genre() == "sf"

    def test_default_fantasy(self, builder):
        assert builder.get_genre() == "fantasy"

    def test_string_genre(self, builder, series_dir):
        _save_plan(series_dir, {"title": "T", "genre": "romance"})
        assert builder.get_genre() == "romance"


# ── get_scene_summary ──────────────────────────────────────────────────


class TestGetSceneSummary:
    def test_basic_scene(self, builder):
        scene = MagicMock()
        scene.title = "出会い"
        scene.goal = "主人公を紹介する"
        scene.outcome = "旅立つ"
        scene.conflict = "葛藤なし"
        scene.pov = "主人公"
        scene.characters = ["主人公", "仲間"]
        scene.key_events = []
        scene.setting = ""

        result = builder.get_scene_summary(scene)
        assert "出会い" in result
        assert "主人公を紹介する" in result
        assert "旅立つ" in result
        assert "葛藤なし" in result
        assert "主人公" in result
        assert "仲間" in result

    def test_scene_with_state_prefix(self, builder):
        scene = MagicMock()
        scene.title = "戦闘"
        scene.goal = "State: 疲労状態 | 敵と戦う"
        scene.outcome = "勝利"
        scene.conflict = "激しい"
        scene.pov = "主人公"
        scene.characters = []
        scene.key_events = []
        scene.setting = ""

        result = builder.get_scene_summary(scene)
        # State: prefix should be stripped from goal
        assert "疲労状態" in result
        assert "State:" not in result

    def test_scene_with_key_events(self, builder):
        scene = MagicMock()
        scene.title = "イベント"
        scene.goal = "目標"
        scene.outcome = "結果"
        scene.conflict = "なし"
        scene.pov = "主人公"
        scene.characters = []
        scene.key_events = ["イベント1", "イベント2"]
        scene.setting = "城"

        result = builder.get_scene_summary(scene)
        assert "イベント1" in result
        assert "イベント2" in result
        assert "城" in result

    def test_scene_empty_characters(self, builder):
        scene = MagicMock()
        scene.title = "独白"
        scene.goal = "内省"
        scene.outcome = "決意"
        scene.conflict = "内面"
        scene.pov = "主人公"
        scene.characters = []
        scene.key_events = []
        scene.setting = ""

        result = builder.get_scene_summary(scene)
        assert "なし" in result


# ── get_outline_summary ────────────────────────────────────────────────


class TestGetOutlineSummary:
    def test_volume_outline(self, builder):
        outline = VolumeOutline(
            title="第1巻",
            premise="始まりの物語",
            volume_number=1,
            chapters=[
                ChapterOutline(number=1, title="プロローグ", purpose="導入"),
                ChapterOutline(number=2, title="転換", purpose="転換"),
            ],
            scenes=[
                SceneOutline(
                    number=1,
                    chapter_number=1,
                    title="出会い",
                    goal="紹介",
                    outcome="旅立ち",
                    characters=["主人公"],
                ),
                SceneOutline(
                    number=2,
                    chapter_number=1,
                    title="別れ",
                    goal="別れ",
                    outcome="孤独",
                    characters=["主人公", "仲間"],
                ),
            ],
        )

        result = builder.get_outline_summary(outline)
        assert "第1巻" in result
        assert "始まりの物語" in result
        assert "プロローグ" in result
        assert "転換" in result
        assert "出会い" in result
        assert "別れ" in result

    def test_scene_with_state_in_goal(self, builder):
        outline = VolumeOutline(
            title="第1巻",
            premise="test",
            volume_number=1,
            chapters=[ChapterOutline(number=1, title="Ch1", purpose="導入")],
            scenes=[
                SceneOutline(
                    number=1,
                    chapter_number=1,
                    title="シーン1",
                    goal="State: 緊張 | 目標",
                    outcome="結果",
                    characters=[],
                ),
            ],
        )

        result = builder.get_outline_summary(outline)
        assert "緊張" in result
        assert "State:" not in result


# ── build_continuity ───────────────────────────────────────────────────


class TestBuildContinuity:
    def test_first_scene_returns_placeholder(self, builder):
        result = builder.build_continuity(
            scene_number=1,
            vol_num=1,
            load_scene_draft_fn=lambda v, s: "",
        )
        assert "最初のシーン" in result

    def test_with_previous_scene_summary(self, builder, bb_storage):
        bb = Blackboard(scene_summaries={"1": "シーン1の要約"})
        bb_storage.save(bb)

        result = builder.build_continuity(
            scene_number=2,
            vol_num=1,
            load_scene_draft_fn=lambda v, s: "",
        )
        assert "前シーンの要約" in result
        assert "シーン1の要約" in result

    def test_with_recent_summaries(self, builder, bb_storage):
        bb = Blackboard(
            scene_summaries={
                "1": "要約1",
                "2": "要約2",
                "3": "要約3",
            }
        )
        bb_storage.save(bb)

        result = builder.build_continuity(
            scene_number=4,
            vol_num=1,
            load_scene_draft_fn=lambda v, s: "",
        )
        assert "直近シーン要約" in result
        assert "要約1" in result
        assert "要約2" in result
        assert "要約3" in result

    def test_with_previous_scene_draft(self, builder, bb_storage):
        bb = Blackboard()
        bb_storage.save(bb)

        result = builder.build_continuity(
            scene_number=2,
            vol_num=1,
            load_scene_draft_fn=lambda v, s: "前シーンの本文" if s == 1 else "",
        )
        assert "前シーン全文" in result
        assert "前シーンの本文" in result

    def test_scene_number_1_no_previous(self, builder, bb_storage):
        bb = Blackboard(scene_summaries={"1": "要約1"})
        bb_storage.save(bb)

        result = builder.build_continuity(
            scene_number=1,
            vol_num=1,
            load_scene_draft_fn=lambda v, s: "",
        )
        # Scene 1 should not have previous scene content
        assert "前シーン" not in result
        assert "最初のシーン" in result
