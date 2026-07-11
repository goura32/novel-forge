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
        """Render an explicitly named non-task template (for example system.md)."""
        if name not in self._cache:
            path = self._dir / name
            if not path.is_file():
                raise FileNotFoundError(f"Prompt not found: {path}")
            self._cache[name] = path.read_text(encoding="utf-8")
        return render_prompt(self._cache[name], variables)

    def render_task(self, task_id: str, variables: dict[str, str]) -> str:
        """Render a task via TaskRegistry; schema resolution is never inferred."""
        from novel_forge.task_registry import DEFAULT_TASK_REGISTRY

        spec = DEFAULT_TASK_REGISTRY.get(task_id)
        values = dict(variables)
        values.setdefault("schema", _build_simplified_schema(DEFAULT_TASK_REGISTRY.load_schema(task_id)))
        return self.render(spec.prompt, values)


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