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


def _escape_json_string_values(text: str) -> str:
    """Replace unescaped newlines inside JSON string values with \\n."""
    result = []
    i = 0
    n = len(text)
    in_string = False
    escape_next = False
    while i < n:
        ch = text[i]
        if in_string:
            if escape_next:
                result.append(ch)
                escape_next = False
            elif ch == '\\':
                result.append(ch)
                escape_next = True
            elif ch == '"':
                result.append(ch)
                in_string = False
            elif ch == '\n':
                result.append('\\')
                result.append('n')
            else:
                result.append(ch)
        else:
            if ch == '"':
                in_string = True
            result.append(ch)
        i += 1
    return ''.join(result)


def _fix_bracket_quoted_values(s: str) -> str:
    """Replace 「...」-quoted values (after ': ') with "..."-quoted values."""
    result = []
    i = 0
    n = len(s)
    while i < n:
        if (i + 2 < n and s[i] == ':' and s[i + 1] == ' '
                and s[i + 2] == '\u300c'):
            result.append(': ')
            i += 2
            start = i
            j = i
            last_period = -1
            depth = 0
            while j < n:
                if s[j] == '\u300c':
                    depth += 1
                elif s[j] == '\u300d':
                    depth -= 1
                elif s[j] == '。' and depth == 0:
                    last_period = j
                elif s[j] == ',' and depth == 0:
                    break
                elif s[j] == '\n' and depth == 0:
                    break
                j += 1
            end = last_period + 1 if last_period >= 0 else j
            value = s[start:end]
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            result.append('"')
            result.append(escaped)
            result.append('"')
            i = end
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _fix_single_quoted_values(s: str) -> str:
    """Replace single-quoted string values with double-quoted values."""
    result = []
    i = 0
    n = len(s)
    while i < n:
        if (s[i] == "'" and i > 0 and s[i - 1] in (':', ',')):
            j = i + 1
            while j < n:
                if s[j] == "'" and s[j - 1] != '\\':
                    break
                j += 1
            if j < n:
                value = s[i + 1:j]
                escaped = value.replace('\\', '\\\\').replace('"', '\\"')
                result.append('"')
                result.append(escaped)
                result.append('"')
                i = j + 1
                continue
        result.append(s[i])
        i += 1
    return ''.join(result)


def _fix_unquoted_values(s: str) -> str:
    """Wrap bare unquoted string values in double quotes.

    Handles patterns like: "key": value (where value is not quoted)
    The value ends at ,\n or \n at the same nesting level.
    """
    result = []
    i = 0
    n = len(s)
    while i < n:
        if (s[i] == ':' and i + 1 < n and s[i + 1] == ' '
                and i + 2 < n
                and s[i + 2] not in ('"', "'", '{', '[', '}', ']', 'n', 't', 'f')):
            # Check if this is inside a string value (skip if so)
            quote_count = 0
            for k in range(i):
                if s[k] == '"' and (k == 0 or s[k - 1] != '\\'):
                    quote_count += 1
            if quote_count % 2 == 1:
                result.append(s[i])
                i += 1
                continue
            result.append('": "')
            i += 2  # skip ': '
            start = i
            j = i
            depth_brace = 0
            depth_bracket = 0
            last_period = -1
            while j < n:
                if s[j] == '{':
                    depth_brace += 1
                elif s[j] == '}':
                    depth_brace -= 1
                elif s[j] == '[':
                    depth_bracket += 1
                elif s[j] == ']':
                    depth_bracket -= 1
                elif depth_brace == 0 and depth_bracket == 0:
                    if s[j] == '。':
                        last_period = j
                    elif s[j] == ',':
                        break
                    elif s[j] == '\n':
                        break
                j += 1
            end = last_period + 1 if last_period >= 0 else j
            if end < n and s[end] == '"':
                end += 1
            value = s[start:end].rstrip()
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            result.append(escaped)
            result.append('"')
            i = end
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


def _fix_missing_colons(s: str) -> str:
    """Fix missing colons: "key", "value" -> "key": "value"."""
    return re.sub(r'"\s*,\s*"([^"]*)"', r'": "\1"', s)


def parse_json_response(text: str) -> Any:
    """Parse JSON from LLM response with progressive fallback fixes."""
    text = _extract_json_text(text)

    # Attempt 1: Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Fix literal newlines in string values
    fixed = _escape_json_string_values(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 3-6: Progressive structural fixes
    fix_chain = [
        _fix_bracket_quoted_values,
        _fix_single_quoted_values,
        _fix_unquoted_values,
        _fix_missing_colons,
    ]
    patched = fixed
    for fix_fn in fix_chain:
        patched = fix_fn(patched)
        try:
            return json.loads(patched)
        except json.JSONDecodeError:
            continue

    # Last resort: extract JSON object boundaries
    start = patched.find("{")
    end = patched.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(patched[start : end + 1])
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
