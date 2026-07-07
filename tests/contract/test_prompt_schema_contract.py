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
            required_sections = [
                "## 目的",
                "## 応答方針",
                "## 実行指示",
                "## 入力情報",
                "## 出力仕様",
            ]
            for section in required_sections:
                if section not in text:
                    prompt_issues.append(f"missing {section} section")
            if "## 役割" in text:
                prompt_issues.append("contains legacy role section")
            if "## 出力構造" in text:
                prompt_issues.append("contains legacy output schema section")
            expected_output_spec = "下記のスキーマに適合する JSON のみ出力すること。\n\n{schema}"
            if expected_output_spec not in text:
                prompt_issues.append("missing unified output spec")
        if prompt_issues:
            issues[prompt_path.name] = prompt_issues

    assert issues == {}


def test_all_task_prompts_have_schema_placeholder() -> None:
    prompt_paths = [p for p in PROMPTS_DIR.glob("*.md") if p.name != "system.md"]

    assert prompt_paths, "expected prompt templates"
    missing = [p.name for p in prompt_paths if "{schema}" not in p.read_text(encoding="utf-8")]

    assert missing == []


def test_input_info_sections_use_subsections_with_line_start_placeholders() -> None:
    issues: dict[str, list[str]] = {}
    for prompt_path in sorted(p for p in PROMPTS_DIR.glob("*.md") if p.name != "system.md"):
        lines = prompt_path.read_text(encoding="utf-8").splitlines()
        start = lines.index("## 入力情報") + 1
        end = lines.index("## 出力仕様")
        section = lines[start:end]
        prompt_issues: list[str] = []
        has_subsection = False
        index = 0
        while index < len(section):
            stripped = section[index].strip()
            if not stripped:
                index += 1
                continue
            if stripped.startswith("- "):
                prompt_issues.append(f"flat input item is not allowed: {stripped}")
                index += 1
                continue
            if not stripped.startswith("### "):
                prompt_issues.append(f"unexpected input line: {stripped}")
                index += 1
                continue
            has_subsection = True
            next_index = index + 1
            while next_index < len(section) and not section[next_index].strip():
                next_index += 1
            if next_index >= len(section):
                prompt_issues.append(f"missing placeholder under {stripped}")
            else:
                placeholder_line = section[next_index]
                if not placeholder_line.startswith("{"):
                    prompt_issues.append(
                        f"placeholder must start at line head under {stripped}: {placeholder_line}"
                    )
            index = next_index + 1
        if not has_subsection:
            prompt_issues.append("missing input subsections")
        if prompt_issues:
            issues[prompt_path.name] = prompt_issues

    assert issues == {}


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

    assert set(review["properties"]) == {"issues"}
    issue_properties = review["properties"]["issues"]["items"]["properties"]
    assert "publication_blocking" not in issue_properties
    assert {"hook", "turning_point", "emotional_arc", "ending_hook"} <= set(scene["properties"])
    assert {"chapter_turning_point", "chapter_hook", "foreshadowing_notes", "subplot_notes"} <= set(chapter["properties"])


def _schema_paths_with_keyword(
    node: object,
    target_keyword: str,
    path: tuple[str, ...] = (),
) -> list[str]:
    issues: list[str] = []
    if isinstance(node, dict):
        if target_keyword in node:
            issues.append(".".join(path) or "$")

        properties = node.get("properties")
        if isinstance(properties, dict):
            for key, value in properties.items():
                issues.extend(_schema_paths_with_keyword(value, target_keyword, (*path, key)))
        items = node.get("items")
        if items is not None:
            issues.extend(_schema_paths_with_keyword(items, target_keyword, (*path, "[]")))
        for combinator in ("oneOf", "anyOf", "allOf"):
            subschemas = node.get(combinator)
            if isinstance(subschemas, list):
                for index, subschema in enumerate(subschemas):
                    issues.extend(
                        _schema_paths_with_keyword(
                            subschema,
                            target_keyword,
                            (*path, f"{combinator}[{index}]"),
                        )
                    )
    return issues


def test_all_schema_fields_have_actionable_descriptions() -> None:
    """Descriptions are prompt guidance for local LLMs, not optional comments."""
    issues: dict[str, list[str]] = {}
    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_issues = _schema_description_issues(schema)
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}


def test_schemas_avoid_strict_unknown_field_rejection() -> None:
    """Avoid additionalProperties=false because local LLMs often emit harmless extras."""
    issues: dict[str, list[str]] = {}
    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_issues = _schema_paths_with_keyword(schema, "additionalProperties")
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}


EMPTY_STRING_ALLOWED_PATHS = {
    ("review.json", "issues.[].before"),
}


EMPTY_ARRAY_ALLOWED_PATHS = {
    ("bible.json", "characters"),
    ("bible.json", "glossary"),
    ("bible.json", "foreshadowing"),
    ("bible.json", "world_rules"),
    ("bible.json", "relationships"),
    ("bible.json", "subplots"),
    ("blackboard.json", "facts"),
    ("chapter_design.json", "foreshadowing_notes"),
    ("chapter_design.json", "subplot_notes"),
    ("review.json", "issues"),
    ("scene_summary.json", "characters"),
    ("scene_summary.json", "facts"),
    ("scene_summary_and_bible_update.json", "facts"),
    ("scene_summary_and_bible_update.json", "continuity_notes"),
    ("scene_summary_and_bible_update.json", "characters"),
    ("scene_summary_and_bible_update.json", "foreshadowing"),
    ("scene_summary_and_bible_update.json", "relationships"),
    ("scene_summary_and_bible_update.json", "subplots"),
    ("scene_summary_and_bible_update.json", "world_rules"),
}


def _schema_paths_with_min_length(
    node: object,
    path: tuple[str, ...] = (),
) -> list[str]:
    issues: list[str] = []
    if isinstance(node, dict):
        path_text = ".".join(path) or "$"
        if "minLength" in node:
            issues.append(f"{path_text}: minLength should be described, not schema-enforced")

        properties = node.get("properties")
        if isinstance(properties, dict):
            for key, value in properties.items():
                issues.extend(_schema_paths_with_min_length(value, (*path, key)))
        items = node.get("items")
        if items is not None:
            issues.extend(_schema_paths_with_min_length(items, (*path, "[]")))
        for combinator in ("oneOf", "anyOf", "allOf"):
            subschemas = node.get(combinator)
            if isinstance(subschemas, list):
                for index, subschema in enumerate(subschemas):
                    issues.extend(
                        _schema_paths_with_min_length(
                            subschema,
                            (*path, f"{combinator}[{index}]"),
                        )
                    )
    return issues


def _missing_min_items_constraints(
    node: object,
    schema_name: str,
    path: tuple[str, ...] = (),
    required: bool = False,
) -> list[str]:
    issues: list[str] = []
    if isinstance(node, dict):
        path_text = ".".join(path) or "$"
        if (
            required
            and
            node.get("type") == "array"
            and (schema_name, path_text) not in EMPTY_ARRAY_ALLOWED_PATHS
            and int(node.get("minItems", 0)) < 1
        ):
            issues.append(f"{path_text}: important array missing minItems>=1")

        properties = node.get("properties")
        required_keys = node.get("required")
        if isinstance(properties, dict):
            required_names = set(required_keys) if isinstance(required_keys, list) else set()
            for key, value in properties.items():
                issues.extend(
                    _missing_min_items_constraints(
                        value,
                        schema_name,
                        (*path, key),
                        required=key in required_names,
                    )
                )
        items = node.get("items")
        if items is not None:
            issues.extend(
                _missing_min_items_constraints(
                    items,
                    schema_name,
                    (*path, "[]"),
                    required=required,
                )
            )
        for combinator in ("oneOf", "anyOf", "allOf"):
            subschemas = node.get(combinator)
            if isinstance(subschemas, list):
                for index, subschema in enumerate(subschemas):
                    issues.extend(
                        _missing_min_items_constraints(
                            subschema,
                            schema_name,
                            (*path, f"{combinator}[{index}]"),
                            required=required,
                        )
                    )
    return issues


def test_string_fields_avoid_min_length_constraints() -> None:
    """Avoid minLength because descriptions guide content while schema stays LLM-friendly."""
    issues: dict[str, list[str]] = {}
    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_issues = _schema_paths_with_min_length(schema)
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}


def test_required_arrays_have_minimum_content_constraints() -> None:
    """Required arrays that drive downstream generation should still avoid empty placeholders."""
    issues: dict[str, list[str]] = {}
    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_issues = _missing_min_items_constraints(schema, schema_path.name)
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}
