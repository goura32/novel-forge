"""Tests for BibleManager read-only serialization (v2: apply_* removed, §10)."""

from __future__ import annotations

from novel_forge.bible_manager import BibleManager
from novel_forge.models import Bible, CharacterProfile, ForeshadowingItem, SubplotItem
from novel_forge.storage import BibleStorage


def test_completed_japanese_subplot_is_not_incomplete(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible(subplots=[SubplotItem(id="sp1", name="陰謀", status="完了")]))
    manager = BibleManager(storage)

    assert manager.get_incomplete_subplots() == []


def test_to_text_slice_scene_includes_characters_and_unresolved(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible(
        characters=[CharacterProfile(name="カスミ", state="負傷")],
        foreshadowing=[ForeshadowingItem(description="青い結晶", resolved=False)],
        world_rules=["魔法は石を媒体とする"],
    ))
    manager = BibleManager(storage)

    text = manager.to_text_slice("scene", {"vol_num": 1, "ch_num": 1, "sc_num": 1, "character_names": ["カスミ"]})
    assert "カスミ" in text
    assert "青い結晶" in text
    assert "魔法は石を媒体とする" in text


def test_to_text_slice_volume_only_active_subplots(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible(subplots=[
        SubplotItem(id="sp1", name="進行中の筋", status="進行中"),
        SubplotItem(id="sp2", name="完了済みの筋", status="完了"),
    ]))
    manager = BibleManager(storage)

    text = manager.to_text_slice("volume", {"vol_num": 1})
    assert "進行中の筋" in text
    assert "完了済みの筋" not in text
