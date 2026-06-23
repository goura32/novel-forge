"""Tests for json_parser.py — NDJSON parsing, error handling, type coercion."""
from __future__ import annotations

import json

import pytest

from novel_forge.json_parser import (
    JsonParseError,
    _escape_json_string_values,
    _extract_json_text,
    _fix_bracket_quoted_values,
    _fix_missing_colons,
    _fix_single_quoted_values,
    _fix_trailing_comma,
    _fix_unquoted_values,
    coerce_types,
    parse_json_response,
)


# ── _extract_json_text ─────────────────────────────────────────────────

class TestExtractJsonText:
    def test_plain_json(self):
        assert _extract_json_text('{"a": 1}') == '{"a": 1}'

    def test_code_fences(self):
        text = '```json\n{"a": 1}\n```'
        assert _extract_json_text(text) == '{"a": 1}'

    def test_code_fences_no_lang(self):
        text = '```\n{"a": 1}\n```'
        assert _extract_json_text(text) == '{"a": 1}'

    def test_whitespace(self):
        assert _extract_json_text('  {"a": 1}  ') == '{"a": 1}'

    def test_empty(self):
        assert _extract_json_text("") == ""


# ── _escape_json_string_values ─────────────────────────────────────────

class TestEscapeJsonStringValues:
    def test_escapes_newlines_in_strings(self):
        text = '{"key": "line1\nline2"}'
        result = _escape_json_string_values(text)
        assert "\\n" in result
        # Should be valid JSON after escaping
        parsed = json.loads(result)
        assert parsed["key"] == "line1\nline2"

    def test_preserves_already_escaped(self):
        text = '{"key": "line1\\nline2"}'
        result = _escape_json_string_values(text)
        parsed = json.loads(result)
        assert parsed["key"] == "line1\nline2"

    def test_no_strings(self):
        text = '{"a": 1, "b": true}'
        result = _escape_json_string_values(text)
        assert result == text


# ── _fix_bracket_quoted_values ─────────────────────────────────────────

class TestFixBracketQuotedValues:
    def test_bracket_to_double_quote(self):
        text = '{"key": 「value」}'
        result = _fix_bracket_quoted_values(text)
        assert '"value"' in result

    def test_no_brackets(self):
        text = '{"key": "value"}'
        result = _fix_bracket_quoted_values(text)
        assert result == text


# ── _fix_single_quoted_values ──────────────────────────────────────────

class TestFixSingleQuotedValues:
    def test_single_to_double(self):
        text = "{'key': 'value'}"
        result = _fix_single_quoted_values(text)
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_mixed_quotes(self):
        text = '{"key": \'value\'}'
        result = _fix_single_quoted_values(text)
        parsed = json.loads(result)
        assert parsed["key"] == "value"


# ── _fix_unquoted_values ───────────────────────────────────────────────

class TestFixUnquotedValues:
    def test_unquoted_string(self):
        text = '{"key": value}'
        result = _fix_unquoted_values(text)
        parsed = json.loads(result)
        assert parsed["key"] == "value"

    def test_already_quoted(self):
        text = '{"key": "value"}'
        result = _fix_unquoted_values(text)
        assert result == text

    def test_numeric_not_quoted(self):
        text = '{"key": 42}'
        result = _fix_unquoted_values(text)
        # Numeric values should not be quoted
        assert '42' in result


# ── _fix_trailing_comma ────────────────────────────────────────────────

class TestFixTrailingComma:
    def test_trailing_comma_before_brace(self):
        text = '{"a": 1, "b": 2,}'
        result = _fix_trailing_comma(text)
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}

    def test_trailing_comma_before_bracket(self):
        text = '["a", "b",]'
        result = _fix_trailing_comma(text)
        parsed = json.loads(result)
        assert parsed == ["a", "b"]

    def test_no_trailing_comma(self):
        text = '{"a": 1}'
        result = _fix_trailing_comma(text)
        assert result == text


# ── _fix_missing_colons ────────────────────────────────────────────────

class TestFixMissingColons:
    def test_missing_colon(self):
        text = '"key", "value"'
        result = _fix_missing_colons(text)
        assert '"key": "value"' in result


# ── parse_json_response ────────────────────────────────────────────────

class TestParseJsonResponse:
    def test_valid_json(self):
        text = '{"key": "value"}'
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_json_with_code_fences(self):
        text = '```json\n{"a": 1, "b": 2}\n```'
        result = parse_json_response(text)
        assert result == {"a": 1, "b": 2}

    def test_json_with_newlines_in_strings(self):
        text = '{"key": "line1\nline2"}'
        result = parse_json_response(text)
        assert result["key"] == "line1\nline2"

    def test_json_with_single_quotes(self):
        text = "{'key': 'value'}"
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_json_with_trailing_comma(self):
        text = '{"a": 1, "b": 2,}'
        result = parse_json_response(text)
        assert result == {"a": 1, "b": 2}

    def test_json_with_unquoted_values(self):
        text = '{"key": value}'
        result = parse_json_response(text)
        assert result["key"] == "value"

    def test_nested_json(self):
        text = '{"outer": {"inner": "value"}, "list": [1, 2, 3]}'
        result = parse_json_response(text)
        assert result["outer"]["inner"] == "value"
        assert result["list"] == [1, 2, 3]

    def test_empty_string_raises(self):
        with pytest.raises(JsonParseError):
            parse_json_response("")

    def test_non_json_raises(self):
        with pytest.raises(JsonParseError):
            parse_json_response("this is not json at all")

    def test_partial_json_extracts_object(self):
        text = 'Some text before {"key": "value"} and after'
        result = parse_json_response(text)
        assert result == {"key": "value"}

    def test_complex_llm_output(self):
        """Simulates a typical LLM response with explanation + JSON."""
        text = (
            "Here is the requested JSON:\n\n"
            '```json\n{"title": "Test", "items": ["a", "b"]}\n```\n\n'
            "This should work correctly."
        )
        result = parse_json_response(text)
        assert result["title"] == "Test"
        assert result["items"] == ["a", "b"]


# ── coerce_types ────────────────────────────────────────────────────────

class TestCoerceTypes:
    def test_fill_missing_string(self):
        data = {}
        schema = {"properties": {"name": {"type": "string"}}}
        result = coerce_types(data, schema)
        assert result["name"] == ""

    def test_fill_missing_array(self):
        data = {}
        schema = {"properties": {"items": {"type": "array"}}}
        result = coerce_types(data, schema)
        assert result["items"] == []

    def test_fill_missing_object(self):
        data = {}
        schema = {"properties": {"meta": {"type": "object"}}}
        result = coerce_types(data, schema)
        assert result["meta"] == {}

    def test_fill_missing_integer(self):
        data = {}
        schema = {"properties": {"count": {"type": "integer"}}}
        result = coerce_types(data, schema)
        assert result["count"] == 0

    def test_fill_missing_boolean(self):
        data = {}
        schema = {"properties": {"active": {"type": "boolean"}}}
        result = coerce_types(data, schema)
        assert result["active"] is False

    def test_coerce_float_to_int(self):
        data = {"count": 3.7}
        schema = {"properties": {"count": {"type": "integer"}}}
        result = coerce_types(data, schema)
        assert result["count"] == 3
        assert isinstance(result["count"], int)

    def test_coerce_int_to_float(self):
        data = {"score": 5}
        schema = {"properties": {"score": {"type": "number"}}}
        result = coerce_types(data, schema)
        assert result["score"] == 5.0
        assert isinstance(result["score"], float)

    def test_coerce_string_to_bool(self):
        data = {"active": "true"}
        schema = {"properties": {"active": {"type": "boolean"}}}
        result = coerce_types(data, schema)
        assert result["active"] is True

    def test_coerce_non_string_to_string(self):
        data = {"name": 123}
        schema = {"properties": {"name": {"type": "string"}}}
        result = coerce_types(data, schema)
        assert result["name"] == "123"

    def test_coerce_scalar_to_array(self):
        data = {"items": "single"}
        schema = {"properties": {"items": {"type": "array"}}}
        result = coerce_types(data, schema)
        assert result["items"] == ["single"]

    def test_nested_object_coercion(self):
        data = {"meta": {}}
        schema = {
            "properties": {
                "meta": {
                    "type": "object",
                    "properties": {"version": {"type": "string"}},
                }
            }
        }
        result = coerce_types(data, schema)
        assert result["meta"]["version"] == ""

    def test_array_items_coercion(self):
        data = {"chars": [{}]}
        schema = {
            "properties": {
                "chars": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                }
            }
        }
        result = coerce_types(data, schema)
        assert result["chars"][0]["name"] == ""

    def test_no_schema_returns_data_unchanged(self):
        data = {"a": 1}
        result = coerce_types(data, None)  # type: ignore[arg-type]
        assert result == {"a": 1}

    def test_non_dict_data_returns_unchanged(self):
        result = coerce_types("not a dict", {"properties": {}})  # type: ignore[arg-type]
        assert result == "not a dict"

    def test_preserves_existing_values(self):
        data = {"name": "Alice", "count": 42}
        schema = {
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            }
        }
        result = coerce_types(data, schema)
        assert result["name"] == "Alice"
        assert result["count"] == 42


# ── JsonParseError ─────────────────────────────────────────────────────

class TestJsonParseError:
    def test_is_exception(self):
        assert issubclass(JsonParseError, Exception)

    def test_message(self):
        err = JsonParseError("test message")
        assert "test message" in str(err)
