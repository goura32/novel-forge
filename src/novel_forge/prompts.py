from __future__ import annotations

import json
from pathlib import Path

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


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
    """Loads and renders prompt templates from the prompts/ directory."""

    def __init__(self, prompt_dir: Path | None = None):
        self._dir = prompt_dir or _PROMPT_DIR
        self._cache: dict[str, str] = {}

    def render(self, name: str, variables: dict[str, str]) -> str:
        if name not in self._cache:
            path = self._dir / name
            if not path.exists():
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
            # まず元の名前で試す
            schema_dict = get_schema(schema_name)
            if not schema_dict:
                # _review, _revision を除去して再試行
                for suffix in ["_review", "_revision"]:
                    if schema_name.endswith(suffix):
                        schema_name = schema_name[:-len(suffix)]
                        break
                schema_dict = get_schema(schema_name)
            # レビュープロンプトの場合は統一 review スキーマを使用
            if not schema_dict and ("_review" in name or "_revision" in name):
                schema_dict = get_schema("review")
            # schema構造そのものを返さないよう、descriptionを中心とした構造化テキストを生成
            if schema_dict:
                schema_json = _build_simplified_schema(schema_dict)
            else:
                schema_json = "{}"
            result = result.replace("{schema}", schema_json)
        return render_prompt(result, variables)


def _build_simplified_schema(schema: dict) -> str:
    """Build a simplified schema text focusing on descriptions for both top-level and nested properties."""
    def extract_props(obj, indent=0) -> dict:
        result = {}
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