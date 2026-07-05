"""Semantic validators for schema-valid but structurally inconsistent artifacts."""

from __future__ import annotations

from novel_forge.semantic_validators import validate_volume_design_semantics


def _valid_final_volume_design() -> dict:
    return {
        "title": "第一巻 旅立ちの朝",
        "premise": "主人公が故郷を出て、仲間との出会いと最初の試練を通じて自分の使命を知る巻。",
        "chapters": [
            {"number": 1, "title": "第一章", "scenes": [{"number": 1, "chapter_number": 1}]},
            {"number": 2, "title": "第二章", "scenes": [{"number": 2, "chapter_number": 2}]},
        ],
        "scenes": [
            {"number": 1, "chapter_number": 1, "title": "シーン1"},
            {"number": 2, "chapter_number": 2, "title": "シーン2"},
        ],
    }


def test_final_volume_design_semantics_accepts_unique_chapters_and_scenes() -> None:
    errors = validate_volume_design_semantics(_valid_final_volume_design())

    assert errors == []


def test_final_volume_design_semantics_rejects_duplicate_chapter_numbers() -> None:
    data = _valid_final_volume_design()
    data["chapters"][1]["number"] = 1

    errors = validate_volume_design_semantics(data)

    assert "duplicate chapter number: 1" in errors


def test_final_volume_design_semantics_rejects_duplicate_scene_numbers() -> None:
    data = _valid_final_volume_design()
    data["scenes"][1]["number"] = 1

    errors = validate_volume_design_semantics(data)

    assert "duplicate scene number: 1" in errors


def test_final_volume_design_semantics_rejects_scene_chapter_mismatch() -> None:
    data = _valid_final_volume_design()
    data["chapters"][1]["scenes"][0]["chapter_number"] = 1

    errors = validate_volume_design_semantics(data)

    assert "chapter 2 contains scene 2 with chapter_number=1" in errors


def test_final_volume_design_semantics_rejects_scene_references_missing_from_top_level() -> None:
    data = _valid_final_volume_design()
    data["scenes"] = data["scenes"][:1]

    errors = validate_volume_design_semantics(data)

    assert "chapter 2 references scene 2 missing from top-level scenes" in errors
