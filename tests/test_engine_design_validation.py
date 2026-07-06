"""Validation tests for design-stage semantic quality gates."""

from __future__ import annotations

from novel_forge.engine.design import (
    _normalize_design_purpose,
    _validate_chapter_design,
)


def _valid_chapter_design(**overrides):
    data = {
        "title": "社殿に響く不協和音",
        "purpose": "展開",
        "theme": "記憶の欠落と現在の危機が交錯する。",
        "emotional_arc": "安心から不安、そして次へ進む覚悟へ変化する。",
        "outcome": "主人公は残影と対峙し、自身の過去へ向かう決意を固める。",
        "chapter_turning_point": "外部の修復から自己の再生へ目的が変わる。",
        "chapter_hook": "音律キーの破片に刻まれた黒市の印を見つけ、次章で黒市へ向かう。",
        "foreshadowing_notes": ["音律キーが熱を持つ理由"],
        "subplot_notes": ["相棒の兄探しが黒市へつながる"],
        "scenes": [
            {
                "title": "調律局の介入と警告",
                "pov": "蓮",
                "goal": "主人公を社殿から引き揚げる。",
                "conflict": "追手と不協和音が同時に迫る。",
                "outcome": "音律キーの破片に刻まれた黒市の印を見つける。",
                "characters": ["千鳥", "蓮"],
                "key_events": ["追手の介入", "黒市の印の発見"],
                "setting": "古社の本殿",
            }
        ],
    }
    data.update(overrides)
    return data


def test_chapter_design_rejects_vague_next_clue_placeholders():
    data = _valid_chapter_design(
        chapter_hook="千鳥が手にした社殿奥のアイテム（次章へ繋がる重要手掛かり）と、残影が遺したような言葉の意味を追う。",
        scenes=[
            {
                "title": "調律局の介入と警告",
                "pov": "蓮",
                "goal": "主人公を社殿から引き揚げる。",
                "conflict": "追手と不協和音が同時に迫る。",
                "outcome": "社殿の奥に埋もれた何か（次への手がかり）を見つけて取り出す。",
                "characters": ["千鳥", "蓮"],
                "key_events": ["追手の介入", "謎の発見"],
                "setting": "古社の本殿",
            }
        ],
    )

    errors = _validate_chapter_design(data)

    assert "chapter_hook (vague placeholder)" in errors
    assert "scenes[0].outcome (vague placeholder)" in errors


def test_chapter_design_accepts_specific_next_clue_details():
    errors = _validate_chapter_design(_valid_chapter_design())

    assert errors == []


def test_normalize_design_purpose_accepts_embedded_enum_label():
    assert _normalize_design_purpose("中盤の転換") == "転換"


def test_normalize_design_purpose_leaves_unknown_text_unchanged():
    assert _normalize_design_purpose("主人公が葛藤する") == "主人公が葛藤する"
