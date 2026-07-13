from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

_PROMPT_DIR = resources.files("novel_forge") / "resources" / "prompts"


def render_prompt(template: str, variables: dict[str, str]) -> str:
    """Render only placeholders present in the original template.

    Replacement is single-pass so data inserted for one variable can never be
    interpreted as a placeholder for another variable.
    """
    placeholder = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return str(variables[key]) if key in variables else match.group(0)

    return placeholder.sub(replace, template)


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
    """Build a field-spec text from a JSON Schema, stripping the schema envelope
    ($schema/title/properties/required/description) that triggers model echo.

    Keeps field names, types, required flags, enums, patterns, and nested
    item-object fields so the model loses no constraints while the prompt no
    longer contains a copyable schema object.
    """
    required_top: set[str] = set(schema.get("required", []))

    def extract_props(obj: Any, required_set: set[str] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if not isinstance(obj, dict):
            return result
        required_set = required_set or set()
        for prop_name, prop_def in obj.get("properties", {}).items():
            if not isinstance(prop_def, dict):
                continue
            entry: dict[str, Any] = {
                "type": prop_def.get("type", "object" if "properties" in prop_def else "string"),
                "required": prop_name in required_set,
                "description": prop_def.get("description", ""),
            }
            if "enum" in prop_def:
                entry["enum"] = prop_def["enum"]
            if "pattern" in prop_def:
                entry["pattern"] = prop_def["pattern"]
            if prop_def.get("type") == "array" and "items" in prop_def:
                items = prop_def["items"]
                if isinstance(items, dict) and "properties" in items:
                    entry["items"] = extract_props(items, set(items.get("required", [])))
            elif "properties" in prop_def:
                entry["fields"] = extract_props(prop_def, set(prop_def.get("required", [])))
            result[prop_name] = entry
        return result

    simplified = extract_props(schema, required_top)
    return json.dumps(simplified, ensure_ascii=False, indent=2)