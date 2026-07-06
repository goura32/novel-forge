from __future__ import annotations

import json
import re
from typing import Any, cast

from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.json_parser")


class JsonParseError(Exception):
    """Raised when JSON parsing fails."""


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


def _quote_unquoted_japanese_string_values(text: str) -> str:
    """Repair a common LLM JSON slip: `"key":日本語文,` without quotes.

    Limit the repair to values beginning with Japanese punctuation/scripts so we do
    not accidentally rewrite valid JSON literals such as true, false, null, or
    numbers.
    """

    def repl(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        value = match.group("value").strip()
        suffix = match.group("suffix")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{prefix}"{escaped}"{suffix}'

    return re.sub(
        r'(?P<prefix>:\s*)(?P<value>[「『（\u3040-\u30ff\u3400-\u9fff][^,}\]\n]*?)(?P<suffix>\s*(?:,\s*"|[}\]]))',
        repl,
        text,
    )


def _escape_literal_newlines_in_strings(text: str) -> str:
    """Escape raw newline characters that appear inside JSON strings.

    Real LLM output sometimes returns `"field": "` followed by a literal line
    break. JSON requires that newline to be encoded as `\\n`; whitespace outside
    strings must remain untouched.
    """

    repaired: list[str] = []
    in_string = False
    escaped = False
    changed = False

    for char in text:
        if escaped:
            repaired.append(char)
            escaped = False
            continue
        if char == "\\" and in_string:
            repaired.append(char)
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            repaired.append(char)
            continue
        if in_string and char == "\n":
            repaired.append("\\n")
            changed = True
            continue
        if in_string and char == "\r":
            repaired.append("\\r")
            changed = True
            continue
        repaired.append(char)

    return "".join(repaired) if changed else text


def _loads_with_repairs(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = _escape_literal_newlines_in_strings(text)
        repaired = _quote_unquoted_japanese_string_values(repaired)
        if repaired != text:
            return json.loads(repaired)
        raise


def parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response.

    Ollama streaming format returns NDJSON (one JSON object per line).
    Each line has a "content" field that must be concatenated.
    The final assembled JSON is then parsed.
    """
    text = _extract_json_text(text)

    # Try direct parse first (single JSON object)
    try:
        return _loads_with_repairs(text)
    except json.JSONDecodeError:
        pass

    # NDJSON streaming format: parse each line and concatenate content
    lines = text.strip().split("\n")
    content_parts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            chunk = obj.get("message", {}).get("content", "") if isinstance(obj, dict) else ""
            if chunk:
                content_parts.append(chunk)
        except json.JSONDecodeError:
            continue

    if content_parts:
        full_content = "".join(content_parts)
        try:
            return _loads_with_repairs(full_content)
        except json.JSONDecodeError:
            pass

    # Fallback: extract JSON object boundaries from text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return _loads_with_repairs(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise JsonParseError(f"Failed to parse JSON from response: {text[:200]}...")


def _coerce_array_fields(data: dict, schema: dict) -> None:
    """Coerce fields that should be arrays but LLM returned objects.

    Modifies data in-place.
    """
    if not isinstance(data, dict) or not schema:
        return

    properties = schema.get("properties", {})
    for key, prop_schema in properties.items():
        if key not in data:
            continue
        expected_type = prop_schema.get("type")
        if expected_type == "array" and isinstance(data[key], dict):
            _log.warning("Coerced schema array field '%s' from object to []", key)
            data[key] = []


def _validate_with_schema(schema: dict, data: Any, path: str = "") -> list[str]:
    """Recursively validate data against JSON schema. Returns list of errors."""
    errors = []

    if "type" in schema:
        expected_type = schema["type"]
        type_errors = _check_type(data, expected_type, path)
        errors.extend(type_errors)

    if "properties" in schema and isinstance(data, dict):
        required_fields = schema.get("required", [])
        for prop_name, prop_schema in schema["properties"].items():
            prop_path = f"{path}.{prop_name}" if path else prop_name
            if prop_name in data:
                errors.extend(_validate_with_schema(prop_schema, data[prop_name], prop_path))
            elif prop_name in required_fields:
                errors.append(f"{prop_path}: required field missing")

    if "items" in schema and isinstance(data, list):
        items_schema = schema["items"]
        for i, item in enumerate(data):
            errors.extend(_validate_with_schema(items_schema, item, f"{path}[{i}]"))

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: value '{data}' not in enum {schema['enum']}")

    if "minLength" in schema and isinstance(data, str) and len(data) < schema["minLength"]:
        errors.append(f"{path}: string length {len(data)} < minLength {schema['minLength']}")

    if "maxLength" in schema and isinstance(data, str) and len(data) > schema["maxLength"]:
        errors.append(f"{path}: string length {len(data)} > maxLength {schema['maxLength']}")

    if "minItems" in schema and isinstance(data, list) and len(data) < schema["minItems"]:
        errors.append(f"{path}: array length {len(data)} < minItems {schema['minItems']}")

    if "maxItems" in schema and isinstance(data, list) and len(data) > schema["maxItems"]:
        errors.append(f"{path}: array length {len(data)} > maxItems {schema['maxItems']}")

    if "pattern" in schema and isinstance(data, str) and not re.match(schema["pattern"], data):
        errors.append(f"{path}: value '{data}' does not match pattern {schema['pattern']}")

    return errors


def _check_type(data: Any, expected_type: str, path: str) -> list[str]:
    """Check if data matches expected JSON schema type."""
    errors = []

    if expected_type == "string" and not isinstance(data, str):
        errors.append(f"{path}: expected string, got {type(data).__name__}")
    elif expected_type == "integer" and not isinstance(data, int):
        errors.append(f"{path}: expected integer, got {type(data).__name__}")
    elif expected_type == "number" and not isinstance(data, (int, float)):
        errors.append(f"{path}: expected number, got {type(data).__name__}")
    elif expected_type == "boolean" and not isinstance(data, bool):
        errors.append(f"{path}: expected boolean, got {type(data).__name__}")
    elif expected_type == "array" and not isinstance(data, list):
        errors.append(f"{path}: expected array, got {type(data).__name__}")
    elif expected_type == "object" and not isinstance(data, dict):
        errors.append(f"{path}: expected object, got {type(data).__name__}")

    return errors


_SCHEMA_DIR = __import__("pathlib").Path(__file__).parent.parent.parent / "schemas"


def _load_schema(name: str) -> dict:
    path = _SCHEMA_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with path.open(encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


def validate(name: str, data: dict[str, Any]) -> list[str]:
    """Schema validation. Returns list of errors."""
    try:
        schema = _load_schema(name)
    except FileNotFoundError:
        _log.error("Schema not found: %s", name)
        return [f"Schema not found: {name}"]
    # Apply pre-validation coercion for common LLM output quirks
    _coerce_array_fields(data, schema)
    return _validate_with_schema(schema, data)


def validate_or_raise(name: str, data: dict[str, Any]) -> None:
    errors = validate(name, data)
    if errors:
        raise ValidationError(f"Schema validation failed for '{name}:\n" + "\n".join(errors))


def get_schema(name: str) -> dict[str, Any]:
    return _load_schema(name)


def list_schemas() -> list[str]:
    return [p.stem for p in _SCHEMA_DIR.glob("*.json")]


class ValidationError(Exception):
    """Raised when schema validation fails."""
    pass