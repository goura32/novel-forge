from __future__ import annotations

import json
import re
from typing import Any


def _extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response.

    Ollama format=json ensures valid JSON output, so direct parsing is sufficient.
    Fallback: extract JSON object boundaries if direct parse fails.
    """
    text = _extract_json_text(text)

    # Direct parse (primary path for format=json)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract JSON object boundaries
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise JsonParseError(f"Failed to parse JSON from response: {text[:200]}...")


def coerce_types(data: dict, schema: dict) -> dict:
    """Coerce types in parsed JSON to match schema expectations.

    Also fills missing fields with default values based on their type:
    - string -> ""
    - array -> []
    - object -> {}
    - integer/number -> 0
    - boolean -> false
    """
    if not schema or not isinstance(data, dict):
        return data

    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key not in data:
            # Fill missing field with default value based on type
            expected_type = prop_schema.get("type")
            if expected_type == "string":
                data[key] = ""
            elif expected_type == "array":
                data[key] = []
            elif expected_type == "object":
                data[key] = {}
                # Recursively fill nested object defaults
                if "properties" in prop_schema:
                    coerce_types(data[key], prop_schema)
            elif expected_type in ("integer", "number"):
                data[key] = 0
            elif expected_type == "boolean":
                data[key] = False
            continue

        value = data[key]
        expected_type = prop_schema.get("type")

        if expected_type == "integer" and isinstance(value, float):
            data[key] = int(value)
        elif expected_type == "number" and isinstance(value, int):
            data[key] = float(value)
        elif expected_type == "string" and not isinstance(value, str):
            data[key] = str(value)
        elif expected_type == "boolean" and isinstance(value, str):
            data[key] = value.lower() in ("true", "1", "yes")
        elif expected_type == "array" and not isinstance(value, list):
            data[key] = [value] if value else []
        elif expected_type == "object" and not isinstance(value, dict):
            pass  # Cannot coerce non-dict to dict — skip to avoid data loss
        elif expected_type == "object" and isinstance(value, dict) and "properties" in prop_schema:
            # Recursively coerce nested objects
            coerce_types(value, prop_schema)

    # Also handle array items (e.g. main_characters[], planned_volumes[])
    for key, prop_schema in properties.items():
        if key in data and isinstance(data[key], list) and prop_schema.get("type") == "array":
            items_schema = prop_schema.get("items", {})
            if items_schema.get("type") == "object" and "properties" in items_schema:
                for item in data[key]:
                    if isinstance(item, dict):
                        coerce_types(item, items_schema)

    return data


class JsonParseError(Exception):
    pass
