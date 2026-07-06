"""Tests for BibleManager semantic updates."""

from __future__ import annotations

from novel_forge.bible_manager import BibleManager
from novel_forge.models import Bible, ForeshadowingItem, RelationshipItem, SubplotItem
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
