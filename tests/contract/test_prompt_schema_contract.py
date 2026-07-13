"""Prompt/schema contract smoke tests.

These tests intentionally start small: they guard the shared contract shape while
future prompt/schema quality work adds stricter semantic assertions.
"""

from __future__ import annotations

import json
from pathlib import Path

from novel_forge.prompts import PromptManager

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "src" / "novel_forge" / "resources" / "prompts"
SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "src" / "novel_forge" / "resources" / "schemas"


def _schema_description_issues(node: object, path: tuple[str, ...] = ()) -> list[str]:
    issues: list[str] = []
    if isinstance(node, dict):
        node_type = node.get("type")
        if isinstance(node_type, str):
            node_types = {node_type}
        elif isinstance(node_type, list):
            node_types = set(node_type)
        else:
            node_types = set()
        if path and node_types & {"object", "array", "string", "integer", "number", "boolean"}:
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
                "## 出力仕様",
            ]
            data_section_required = ["## レビュー対象", "## 改訂対象", "## 入力情報", "### 指摘対象", "### 改訂対象", "### 入力情報"]
            has_any_data_section = any(s in text for s in data_section_required)
            if not has_any_data_section:
                prompt_issues.append("missing review/target/input section")
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



def test_scene_contract_prompt_requires_object_writer_view_fields() -> None:
    text = (PROMPTS_DIR / "pnca_scene_contract.md").read_text(encoding="utf-8")

    assert "`writer_view` は object" in text
    assert "`narrative_contract` は object" in text
    assert "単一の文字列にしてはならない" in text


def test_all_task_prompts_have_schema_placeholder() -> None:
    prompt_paths = [p for p in PROMPTS_DIR.glob("*.md") if p.name != "system.md"]

    assert prompt_paths, "expected prompt templates"
    missing = [p.name for p in prompt_paths if "{schema}" not in p.read_text(encoding="utf-8")]

    assert missing == []


def test_input_info_sections_use_subsections_with_line_start_placeholders() -> None:
    issues: dict[str, list[str]] = {}
    for prompt_path in sorted(p for p in PROMPTS_DIR.glob("*.md") if p.name != "system.md"):
        lines = prompt_path.read_text(encoding="utf-8").splitlines()
        data_sections = ["## レビュー対象", "## 改訂対象", "## 入力情報", "## 補足情報", "### 指摘対象", "### 改訂対象", "### 入力情報"]
        # find which data section header exists first before ## 出力仕様
        output_spec_idx = lines.index("## 出力仕様")
        found_section_start = None
        for section_header in data_sections:
            if section_header in lines:
                idx = lines.index(section_header)
                if idx < output_spec_idx and (
                    found_section_start is None or idx > found_section_start
                ):
                    found_section_start = idx
        if found_section_start is None:
            issues[prompt_path.name] = ["missing review/target/input section (no subsection header found)"]
            continue
        start = found_section_start + 1
        end = output_spec_idx
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

    assert "review_issues" in schema_names
    assert "scene_review" not in schema_names
    assert all(not name.endswith("_review") for name in schema_names)


def test_revision_tasks_render_explicit_target_schema() -> None:
    """TaskRegistry, not a filename heuristic, owns prompt/schema pairing."""
    manager = PromptManager(PROMPTS_DIR)
    variables = {
        "writer_context": "{}", "draft": "本文", "summary": "{}", "review": "{}",
        "previous_summary": "{}",
    }
    cases = {
        "design.chapter.revise": ["title", "purpose", "theme"],
        "design.scene.revise": ["title", "goal", "conflict", "outcome"],
        "design.volume.revise": ["title", "premise", "chapters"],
        "write.draft.revise": ["content"],
        "write.summary.revise": ["summary", "end_state"],
    }
    for task_id, expected_fields in cases.items():
        rendered = manager.render_task(task_id, variables)
        for field in expected_fields:
            assert field in rendered, f"{task_id} should include target schema field {field}"
        assert "ready_for_publication" not in rendered
        assert "overall_assessment" not in rendered


def test_quality_schema_fields_exist_for_generation_pipeline() -> None:
    review = json.loads((SCHEMAS_DIR / "review_issues.json").read_text(encoding="utf-8"))
    scene = json.loads((SCHEMAS_DIR / "design_scene.json").read_text(encoding="utf-8"))
    chapter = json.loads((SCHEMAS_DIR / "design_chapter.json").read_text(encoding="utf-8"))

    assert set(review["properties"]) == {"issues"}
    issue_properties = review["properties"]["issues"]["items"]["properties"]
    assert "publication_blocking" not in issue_properties
    assert {"hook", "turning_point", "emotional_arc", "ending_hook"} <= set(scene["properties"])
    assert {"pov_character_id", "character_ids", "location_id", "canon_patch"} <= set(scene["required"])
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
        if schema_path.name == "design_scene.json":
            schema_issues = []
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}


def test_schemas_avoid_strict_unknown_field_rejection() -> None:
    """Avoid additionalProperties=false because local LLMs often emit harmless extras."""
    issues: dict[str, list[str]] = {}
    for schema_path in sorted(SCHEMAS_DIR.glob("*.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_issues = _schema_paths_with_keyword(schema, "additionalProperties")
        if schema_path.name == "design_scene.json":
            assert schema_issues
            continue
        if schema_issues:
            issues[schema_path.name] = schema_issues

    assert issues == {}


EMPTY_STRING_ALLOWED_PATHS = {
    ("review_issues.json", "issues.[].before"),
}


EMPTY_ARRAY_ALLOWED_PATHS = {
    ("plan_characters.json", "main_characters"),
    ("design_chapter.json", "foreshadowing_notes"),
    ("design_chapter.json", "subplot_notes"),
    ("review_issues.json", "issues"),
    ("write_summary.json", "characters"),
    ("write_summary.json", "facts"),
    ("pnca_scene_render.json", "coverage.evidence"),
    ("pnca_scene_revise.json", "coverage.evidence"),
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
