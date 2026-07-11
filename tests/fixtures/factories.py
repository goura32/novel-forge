"""Reusable valid test data factories for schema and workflow tests."""

from __future__ import annotations

from typing import Any


def plan_concept_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Test Series Title That Is Definitely Long Enough To Pass Validation",
        "slug": "test_series",
        "logline": "A test story that is long enough to meet the minimum length requirement of two hundred characters for the logline field in the schema and includes plenty of descriptive text about the protagonist and their journey.",
        "genre": ["fantasy"],
        "target_audience": "20代後半から30代の読者をターゲットにしたファンタジー小説で、冒険と成長の物語を求める層に向けて書かれています。",
        "themes": ["adventure", "friendship", "growth"],
        "selling_points": [
            "Unique world building with an intricate magic system that affects every aspect of society",
            "Complex character relationships that evolve naturally throughout the series",
        ],
        "world_summary": "A world where magic exists and is regulated by ancient laws. The story follows a young mage discovering their power and learning to navigate a society where magical ability determines social status.",
        "world_rules": [
            "magic requires sacrifice of something precious",
            "ancient laws govern all spellcasting and violations are punished severely",
        ],
    }
    data.update(overrides)
    return data


def design_volume_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "第一巻 旅立ちの朝",
        "premise": "主人公が故郷を出て、仲間との出会いと最初の試練を通じて自分の使命を知る巻。物語全体の導入として世界観、対立軸、主要人物の関係性を提示し、終盤で次巻へ続く新たな危機を示す。",
        "chapters": [
            {"title": "プロローグ 旅立ちの朝", "purpose": "導入"},
            {"title": "第一章 出会いと別れ", "purpose": "展開"},
            {"title": "第二章 試練の森", "purpose": "転換"},
            {"title": "第三章 決戦", "purpose": "収束"},
        ],
    }
    data.update(overrides)
    return data


def review_issues_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"issues": []}
    data.update(overrides)
    return data
