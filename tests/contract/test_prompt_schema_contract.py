"""Prompt/schema contract smoke tests.

These tests intentionally start small: they guard the shared contract shape while
future prompt/schema quality work adds stricter semantic assertions.
"""

from __future__ import annotations

import json
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def test_all_task_prompts_have_schema_placeholder() -> None:
    prompt_paths = [p for p in PROMPTS_DIR.glob("*.md") if p.name != "system.md"]

    assert prompt_paths, "expected prompt templates"
    missing = [p.name for p in prompt_paths if "{schema}" not in p.read_text(encoding="utf-8")]

    assert missing == []


def test_unified_review_schema_exists_without_specific_review_schemas() -> None:
    schema_names = {p.stem for p in SCHEMAS_DIR.glob("*.json")}

    assert "review" in schema_names
    assert "scene_review" not in schema_names
    assert all(not name.endswith("_review") for name in schema_names)


def test_quality_schema_fields_exist_for_generation_pipeline() -> None:
    review = json.loads((SCHEMAS_DIR / "review.json").read_text(encoding="utf-8"))
    scene = json.loads((SCHEMAS_DIR / "scene_design.json").read_text(encoding="utf-8"))
    chapter = json.loads((SCHEMAS_DIR / "chapter_design.json").read_text(encoding="utf-8"))

    assert {"ready_for_publication", "overall_assessment", "strengths"} <= set(review["properties"])
    assert {"hook", "turning_point", "emotional_arc", "ending_hook"} <= set(scene["properties"])
    assert {"chapter_turning_point", "chapter_hook", "foreshadowing_notes", "subplot_notes"} <= set(chapter["properties"])
