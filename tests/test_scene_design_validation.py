"""Validation tests for _validate_scene_design quality gates."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from novel_forge.engine.design import _validate_scene_design


def test_scene_design_rejects_outputer_thief_action():
    # context: P18-47 final scene_design outcome had "警備員から奪われた古鏡" which caused review non-convergence.
    data = {
        "title": "テスト",
        "goal": "目標",
        "conflict": "葛藤",
        "outcome": "警備員から奪われた古鏡型の記憶媒体に、響自身の手記が含まれていることを確認する。",
    }

    errors = _validate_scene_design(data)

    # Thief action in outcome should produce validation error.
    assert any("outcome" in e and ("夺" in e or "収" in e or "奪" in e or "盗" in e) for e in errors), (
        f"Expected validation error for thief action in outcome, got: {errors}"
    )
