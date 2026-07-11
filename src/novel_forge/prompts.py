from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

_PROMPT_DIR = resources.files("novel_forge") / "resources" / "prompts"


def render_prompt(template: str, variables: dict[str, str]) -> str:
    """Render a template by replacing {key} placeholders with values.

    Placeholders use single-brace format: {key}
    Keys are sorted by length (longest first) to avoid partial matches.
    """
    result = template
    for key in sorted(variables, key=len, reverse=True):
        result = result.replace(f"{{{key}}}", str(variables[key]))
    return result


class PromptManager:
    """Loads and renders prompt templates from packaged prompt resources."""

    def __init__(self, prompt_dir: Path | None = None):
        self._dir = prompt_dir or _PROMPT_DIR
        self._cache: dict[str, str] = {}

    def render(self, name: str, variables: dict[str, str]) -> str:
        if name not in self._cache:
            path = self._dir / name
            if not path.is_file():
                raise FileNotFoundError(f"Prompt not found: {path}")
            self._cache[name] = path.read_text(encoding="utf-8")
        # {schema} が含まれている場合、スキーマを自動的に取得して置換
        result = self._cache[name]
        if "{schema}" in result:
            from novel_forge.schemas import get_schema
            # プロンプト名からスキーマ名を推定
            schema_name = name
            if schema_name.endswith(".md"):
                schema_name = schema_name[:-3]
            schema_dict = get_schema(_infer_schema_name(schema_name))
            # schema構造そのものを返さないよう、descriptionを中心とした構造化テキストを生成
            schema_json = _build_simplified_schema(schema_dict) if schema_dict else "{}"
            result = result.replace("{schema}", schema_json)
        return render_prompt(result, variables)


def _infer_schema_name(prompt_stem: str) -> str:
    """Infer output schema name from a prompt template stem.

    task_registry convention: prompt filename = "{resource_stem}_{operation}.md"
      - operation in (generate, revise) -> schema stem = resource_stem
      - operation == review            -> schema = review_issues
    v2 continuity-handoff files keep their externally compatible schemas:
      - scene_draft_v2    -> write_draft
      - scene_review_v2   -> review_issues
      - scene_revision_v2 -> write_draft
    """
    v2_map = {
        "scene_draft_v2": "write_draft",
        "scene_review_v2": "review_issues",
        "scene_revision_v2": "write_draft",
    }
    if prompt_stem in v2_map:
        return v2_map[prompt_stem]
    if prompt_stem.endswith("_review"):
        return "review_issues"
    if prompt_stem.endswith("_revise"):
        return prompt_stem[: -len("_revise")]
    if prompt_stem.endswith("_generate"):
        return prompt_stem[: -len("_generate")]
    return prompt_stem


def _build_simplified_schema(schema: dict[str, Any]) -> str:
    """Build a simplified schema text focusing on descriptions for both top-level and nested properties."""
    def extract_props(obj: Any, indent: int = 0) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not isinstance(obj, dict):
            return result
        for prop_name, prop_def in obj.get("properties", {}).items():
            entry = {"description": prop_def.get("description", "")}
            # Include type if available
            if "type" in prop_def:
                entry["type"] = prop_def["type"]
            # Handle nested items (arrays of objects)
            if prop_def.get("type") == "array" and "items" in prop_def:
                items = prop_def["items"]
                if isinstance(items, dict) and "properties" in items:
                    entry["items_properties"] = extract_props(items, indent + 2)
            result[prop_name] = entry
        return result

    simplified = extract_props(schema)
    return json.dumps(simplified, ensure_ascii=False, indent=2)