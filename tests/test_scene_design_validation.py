"""Validation tests for _validate_scene_design quality gates."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from novel_forge.engine.design import _validate_scene_design


def test_scene_design_rejects_stolen_from_guard_phrasing():
    # P18-47: outcomeに「警備員から奪われた古鏡」が含まれ、review non-convergenceの原因。
    data = {
        "title": "テスト",
        "goal": "目標",
        "conflict": "葛藤",
        "outcome": "警備員から奪われた古鏡型の記憶媒体を確認する。",
    }
    errors = _validate_scene_design(data)
    assert "outcome (incoherent stolen-from-guard phrasing)" in errors


def test_scene_design_allows_specific_recovery_action():
    data = {
        "title": "テスト",
        "goal": "目標",
        "conflict": "葛藤",
        "outcome": "主人公が社殿の棚から古鏡を回収した理由を確認する。",
    }
    errors = _validate_scene_design(data)
    assert errors == []
