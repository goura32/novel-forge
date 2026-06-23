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
            elif ch == "\\":
                result.append(ch)
                escape_next = True
            elif ch == '"':
                result.append(ch)
                in_string = False
            elif ch == "\n":
                result.append("\\n")
            else:
                result.append(ch)
        else:
            if ch == '"':
                in_string = True
            result.append(ch)
        i += 1
    return "".join(result)


def _fix_bracket_quoted_values(s: str) -> str:
    """Replace 「...」-quoted values (after ': ') with "..."-quoted values."""
    return re.sub(
        r': \u300c([^\u300d]*)\u300d',
        lambda m: ': "' + m.group(1).replace("\\", "\\\\").replace('"', '\\"') + '"',
        s,
    )


def _fix_single_quoted_values(s: str) -> str:
    """Replace single-quoted string values with double-quoted values."""
    result = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "'" and i > 0 and s[i - 1] in (':', ','):
            j = i + 1
            while j < n:
                if s[j] == "'" and s[j - 1] != '\\':
                    break
                j += 1
            if j < n:
                value = s[i + 1:j]
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                result.append('"')
                result.append(escaped)
                result.append('"')
                i = j + 1
                continue
        result.append(s[i])
        i += 1
    return "".join(result)


def _fix_unquoted_values(s: str) -> str:
    """Wrap bare unquoted string values in double quotes."""
    return re.sub(
        r':\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        lambda m: ': "' + m.group(1) + '"' if m.group(1) not in ('true', 'false', 'null') else m.group(0),
        s,
    )


def _fix_trailing_comma(s: str) -> str:
    """Remove trailing commas before } or ]."""
    return re.sub(r',\s*([}\]])', r'\1', s)


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

    # Attempt 2: Escape newlines in strings
    fixed = _escape_json_string_values(text)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 3: Fix bracket-quoted values
    fixed = _fix_bracket_quoted_values(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 4: Fix single-quoted values
    fixed = _fix_single_quoted_values(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 5: Fix unquoted values
    fixed = _fix_unquoted_values(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 6: Fix trailing commas
    fixed = _fix_trailing_comma(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 7: Fix missing colons
    fixed = _fix_missing_colons(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 8: Bracket + trailing comma
    fixed = _fix_bracket_quoted_values(text)
    fixed = _fix_trailing_comma(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 9: Bracket + single quote + trailing comma
    fixed = _fix_bracket_quoted_values(text)
    fixed = _fix_single_quoted_values(fixed)
    fixed = _fix_trailing_comma(fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise JsonParseError(f"Failed to parse JSON from response: {text[:200]}...")


def coerce_types(data: dict, schema: dict) -> dict:
    """Coerce data types to match schema."""
    if not schema or not data:
        return data
    result = {}
    props = schema.get("properties", {})
    for key, value in data.items():
        if key in props:
            prop_schema = props[key]
            expected_type = prop_schema.get("type")
            if expected_type == "string":
                if isinstance(value, (dict, list)):
                    result[key] = str(value).replace("'", '"')
                else:
                    result[key] = str(value) if value is not None else ""
            elif expected_type == "array":
                if isinstance(value, str):
                    items = [v.strip() for v in re.split(r'[、,]', value) if v.strip()]
                    result[key] = items
                elif isinstance(value, list):
                    result[key] = [coerce_types(item, prop_schema.get("items", {})) if isinstance(item, dict) else item for item in value]
                else:
                    result[key] = [value] if value is not None else []
            elif expected_type == "object":
                if isinstance(value, dict):
                    result[key] = coerce_types(value, prop_schema)
                else:
                    result[key] = value
            elif expected_type == "integer":
                try:
                    result[key] = int(value)
                except (ValueError, TypeError):
                    result[key] = 0
            elif expected_type == "number":
                try:
                    result[key] = float(value)
                except (ValueError, TypeError):
                    result[key] = 0.0
            elif expected_type == "boolean":
                if isinstance(value, str):
                    result[key] = value.lower() in ("true", "1", "yes")
                else:
                    result[key] = bool(value)
            else:
                result[key] = value
        else:
            result[key] = value
    return result


class JsonParseError(Exception):
    pass
