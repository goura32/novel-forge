"""Tests for json_parser.py — parsing and validation."""

from __future__ import annotations

import pytest

from novel_forge.json_parser import (
    JsonParseError,
    ValidationError,
    _extract_json_text,
    _coerce_array_fields,
    parse_json_response,
    validate,
    validate_or_raise,
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


# ── _coerce_array_fields ───────────────────────────────────────────────


class TestCoerceArrayFields:
    def test_object_to_array(self):
        data = {"items": {"a": "b"}}
        schema = {"properties": {"items": {"type": "array"}}}
        _coerce_array_fields(data, schema)
        assert data["items"] == []

    def test_already_array_unchanged(self):
        data = {"items": ["a", "b"]}
        schema = {"properties": {"items": {"type": "array"}}}
        _coerce_array_fields(data, schema)
        assert data["items"] == ["a", "b"]

    def test_non_array_field_unchanged(self):
        data = {"name": "Alice"}
        schema = {"properties": {"name": {"type": "string"}}}
        _coerce_array_fields(data, schema)
        assert data["name"] == "Alice"


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


# ── validate / validate_or_raise ───────────────────────────────────────


class TestValidate:
    def test_valid_data_passes(self):
        data = {"title": "Test", "slug": "test_series", "logline": "A story", "genre": ["fantasy"], "themes": ["love"], "selling_points": ["unique"], "world_summary": "World", "world_rules": ["rule1"], "target_audience": "adults"}
        errors = validate("series_plan_concept", data)
        assert errors == []

    def test_missing_required_field(self):
        data = {"title": "Test"}
        errors = validate("series_plan_concept", data)
        assert any("required field missing" in e for e in errors)

    def test_wrong_type(self):
        data = {"title": "Test", "slug": "test", "logline": "A", "genre": "not-array", "themes": [], "selling_points": [], "world_summary": "W", "world_rules": [], "target_audience": "A"}
        errors = validate("series_plan_concept", data)
        assert any("expected array" in e for e in errors)

    def test_enum_validation(self):
        data = {"chapters": [{"title": "Ch1", "purpose": "invalid"}]}
        errors = validate("volume_design", data)
        assert any("not in enum" in e for e in errors)

    def test_min_items(self):
        # After schema relaxation: minItems constraints moved to description.
        # This test now verifies that validation passes without minItems enforcement.
        data = {"chapters": [{"title": "Ch1", "purpose": "導入"}]}
        errors = validate("volume_design", data)
        # Should not have minItems errors (constraint removed from schema)
        assert not any("minItems" in e for e in errors)

    def test_unknown_schema_returns_empty(self):
        errors = validate("nonexistent_schema", {"a": 1})
        assert errors == []

    def test_validate_or_raise_valid(self):
        data = {"title": "Test", "slug": "test", "logline": "A", "genre": ["f"], "themes": ["t"], "selling_points": ["s"], "world_summary": "W", "world_rules": ["r"], "target_audience": "A"}
        validate_or_raise("series_plan_concept", data)  # Should not raise

    def test_validate_or_raise_invalid(self):
        data = {"title": "Test"}
        with pytest.raises(ValidationError):
            validate_or_raise("series_plan_concept", data)


# ── JsonParseError ─────────────────────────────────────────────────────


class TestJsonParseError:
    def test_is_exception(self):
        assert issubclass(JsonParseError, Exception)

    def test_message(self):
        err = JsonParseError("test message")
        assert "test message" in str(err)


# ── ValidationError ────────────────────────────────────────────────────


class TestValidationError:
    def test_is_exception(self):
        assert issubclass(ValidationError, Exception)