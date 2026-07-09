"""Tests for BibleManager semantic updates."""

from __future__ import annotations

from novel_forge.bible_manager import BibleManager
from novel_forge.models import Bible, CharacterProfile, ForeshadowingItem, RelationshipItem, SubplotItem
from novel_forge.storage import BibleStorage


def test_completed_japanese_subplot_is_not_incomplete(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible(subplots=[SubplotItem(id="sp1", name="陰謀", status="完了")]))
    manager = BibleManager(storage)

    assert manager.get_incomplete_subplots() == []


def test_apply_update_resolves_japanese_foreshadowing_type(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible(foreshadowing=[ForeshadowingItem(description="剣の秘密", resolved=False)]))
    manager = BibleManager(storage)

    manager.apply_update({"foreshadowing": [{"type": "回収", "description": "剣の秘密"}]}, scene_number=3)

    assert manager.bible.foreshadowing[0].resolved is True


def test_apply_update_maps_relationship_type_alias(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible())
    manager = BibleManager(storage)

    manager.apply_update(
        {
            "relationships": [
                {
                    "character_a": "アリス",
                    "character_b": "ボブ",
                    "type": "師弟",
                    "change_direction": "信頼が深まる",
                }
            ]
        },
        scene_number=2,
    )

    rel = manager.bible.relationships[0]
    assert isinstance(rel, RelationshipItem)
    assert rel.relationship_type == "師弟"


def test_apply_update_accepts_world_rules_as_strings(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible())
    manager = BibleManager(storage)

    manager.apply_update({"world_rules": ["魔法は代償なしには使えない"]}, scene_number=1)

    assert manager.bible.world_rules == ["魔法は代償なしには使えない"]


def test_apply_update_keeps_legacy_world_rule_object_compatibility(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible())
    manager = BibleManager(storage)

    manager.apply_update({"world_rules": [{"rule": "契約は満月の夜だけ成立する"}]}, scene_number=1)

    assert manager.bible.world_rules == ["契約は満月の夜だけ成立する"]


# ── apply_design_update (intentional, idempotent) ─────────────


def test_apply_design_update_scene_plant_and_resolve(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible())
    manager = BibleManager(storage)

    # シーン設計が伏線を setup
    manager.apply_design_update(
        "scene",
        {"characters": ["カスミ"], "notes": "疲労が頂点", "foreshadowing": ["薬炉の灰に青い結晶"]},
        {"vol_num": 1, "ch_num": 1, "sc_num": 1},
    )
    assert len(manager.bible.foreshadowing) == 1
    assert manager.bible.foreshadowing[0].resolved is False
    assert any(c.name == "カスミ" for c in manager.bible.characters)

    # 同一シーンを再設計 → 冪等（重複しない）
    manager.apply_design_update(
        "scene",
        {"characters": ["カスミ"], "notes": "疲労が頂点", "foreshadowing": ["薬炉の灰に青い結晶"]},
        {"vol_num": 1, "ch_num": 1, "sc_num": 1},
    )
    assert len(manager.bible.foreshadowing) == 1

    # 別シーンで明示的に回収
    manager.apply_design_update(
        "scene",
        {"characters": [], "notes": "", "resolves_foreshadowing": ["薬炉の灰に青い結晶"]},
        {"vol_num": 1, "ch_num": 2, "sc_num": 3},
    )
    assert manager.bible.foreshadowing[0].resolved is True


def test_apply_design_update_chapter_idempotent(tmp_path) -> None:
    storage = BibleStorage(tmp_path)
    storage.save(Bible())
    manager = BibleManager(storage)

    manager.apply_design_update(
        "chapter",
        {"foreshadowing_notes": ["密航船の船頭の正体"], "subplot_notes": ["王都の陰謀"]},
        {"vol_num": 1, "ch_num": 1},
    )
    manager.apply_design_update(
        "chapter",
        {"foreshadowing_notes": ["密航船の船頭の正体"], "subplot_notes": ["王都の陰謀"]},
        {"vol_num": 1, "ch_num": 1},
    )
    assert len(manager.bible.foreshadowing) == 1
    assert len(manager.bible.subplots) == 1


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
