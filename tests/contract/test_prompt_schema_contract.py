"""Prompt/schema contract smoke tests.

These tests intentionally start small: they guard the shared contract shape while
future prompt/schema quality work adds stricter semantic assertions.
"""

from __future__ import annotations

import json
from pathlib import Path

from novel_forge.prompts import PromptManager

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def _schema_description_issues(node: object, path: tuple[str, ...] = ()) -> list[str]:
    issues: list[str] = []
    if isinstance(node, dict):
        node_type = node.get("type")
        if path and node_type in {"object", "array", "string", "integer", "number", "boolean"}:
            description = str(node.get("description", "")).strip()
            if len(description) < 12:
                issues.append(".".join(path))

        properties = node.get("properties")
        if isinstance(properties, dict):
            for key, value in properties.items():
                issues.extend(_schema_description_issues(value, (*path, key)))
        items = node.get("items")
        if items is not None:
            issues.extend(_schema_description_issues(items, (*path, "[]")))
    return issues


def test_all_prompt_templates_have_consistent_basic_structure() -> None:
    issues: dict[str, list[str]] = {}
    for prompt_path in sorted(PROMPTS_DIR.glob("*.md")):
        text = prompt_path.read_text(encoding="utf-8")
        prompt_issues: list[str] = []
        if not prompt_path.name.replace(".md", "").replace("_", "").isalnum():
            prompt_issues.append("filename must be lowercase snake_case")
        if not text.lstrip().startswith("# "):
            prompt_issues.append("missing top-level title")
        if prompt_path.name != "system.md":
            if "## 役割" not in text:
                prompt_issues.append("missing role section")
            if "## 出力構造" not in text:
                prompt_issues.append("missing output schema section")
            if "{schema}" not in text:
                prompt_issues.append("missing {schema} placeholder")
        if prompt_issues:
            issues[prompt_path.name] = prompt_issues

    assert issues == {}


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


def test_revision_prompts_inject_target_schema_not_review_schema() -> None:
    manager = PromptManager(PROMPTS_DIR)
    variables = {
        "current_chapter": "{}",
        "current_scene": "{}",
        "current_volume": "{}",
        "current_plan": "{}",
        "current_characters": "{}",
        "current_volumes": "{}",
        "review": "レビュー",
        "series_plan": "{}",
        "previous_design": "{}",
        "scene": "本文",
        "concept_text": "企画",
        "keywords": "keyword",
        "lang": "ja",
    }
    cases = {
        "chapter_design_revision.md": ["title", "purpose", "theme"],
        "scene_design_revision.md": ["title", "goal", "conflict", "outcome"],
        "volume_design_revision.md": ["title", "premise", "chapters"],
        "series_plan_concept_revision.md": ["title", "slug", "logline"],
        "series_plan_characters_revision.md": ["main_characters"],
        "series_plan_volumes_revision.md": ["planned_volumes"],
        "scene_revision.md": ["title", "content"],
    }

    for prompt_name, expected_fields in cases.items():
        rendered = manager.render(prompt_name, variables)
        for field in expected_fields:
            assert field in rendered, f"{prompt_name} should include target schema field {field}"
        assert "ready_for_publication" not in rendered
        assert "overall_assessment" not in rendered


def test_quality_schema_fields_exist_for_generation_pipeline() -> None:
    review = json.loads((SCHEMAS_DIR / "review.json").read_text(encoding="utf-8"))
    scene = json.loads((SCHEMAS_DIR / "scene_design.json").read_text(encoding="utf-8"))
    chapter = json.loads((SCHEMAS_DIR / "chapter_design.json").read_text(encoding="utf-8"))

    assert {"ready_for_publication", "overall_assessment", "strengths"} <= set(review["properties"])
    assert {"hook", "turning_point", "emotional_arc", "ending_hook"} <= set(scene["properties"])
    assert {"chapter_turning_point", "chapter_hook", "foreshadowing_notes", "subplot_notes"} <= set(chapter["properties"])


def test_all_schema_fields_have_actionable_descriptions() -> None:
    """Descriptions are prompt guidance for local LLMs, not optional comments."""
    issues: dict[str, list[str]] = {}
    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_issues = _schema_description_issues(schema)
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}
