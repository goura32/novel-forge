"""Extended tests for schemas.py — validation edge cases and schema coverage."""
from __future__ import annotations

import pytest

from novel_forge.schemas import get_schema, list_schemas, validate, validate_or_raise


# ── list_schemas ────────────────────────────────────────────────────────

class TestListSchemas:
    def test_returns_dict(self):
        schemas = list_schemas()
        assert isinstance(schemas, dict)

    def test_contains_core_schemas(self):
        schemas = list_schemas()
        expected = [
            "series_plan_core",
            "series_plan_characters",
            "series_plan_volumes",
            "volume_design",
            "chapter_design",
            "scene_design",
            "scene_draft",
            "scene_revision",
            "scene_review",
            "scene_summary_and_bible_update",
        ]
        for name in expected:
            assert name in schemas, f"Missing schema: {name}"

    def test_each_schema_has_properties(self):
        schemas = list_schemas()
        assert isinstance(schemas, dict), "list_schemas should return dict"
        for name, schema in schemas.items():
            assert isinstance(schema, dict), f"{name} schema should be dict"
            assert "properties" in schema, f"{name} schema should have properties"


# ── get_schema ──────────────────────────────────────────────────────────

class TestGetSchema:
    def test_returns_valid_schema(self):
        schema = get_schema("series_plan_core")
        assert "properties" in schema
        assert "title" in schema["properties"]

    def test_unknown_schema_returns_empty(self):
        schema = get_schema("nonexistent_schema")
        assert schema == {}


# ── validate ────────────────────────────────────────────────────────────

class TestValidate:
    def test_valid_series_plan(self):
        data = {
            "title": "Test Series",
            "slug": "test-series",
            "logline": "A test story",
            "genre": ["fantasy"],
            "target_audience": "10代後半〜30代",
            "themes": ["adventure"],
            "selling_points": ["Unique world"],
            "world": {"summary": "Magic world", "rules": ["magic exists"]},
        }
        errors = validate("series_plan_core", data)
        assert len(errors) == 0

    def test_missing_required_field(self):
        data = {"title": "Test"}
        errors = validate("series_plan_core", data)
        assert len(errors) > 0

    def test_empty_data(self):
        errors = validate("series_plan_core", {})
        assert len(errors) > 0

    def test_extra_fields_allowed(self):
        """JSON Schema should not forbid additional properties by default."""
        data = {
            "title": "Test",
            "slug": "test",
            "logline": "Story",
            "genre": ["fantasy"],
            "target_audience": "10代",
            "themes": ["adventure"],
            "selling_points": ["Unique"],
            "world": {"summary": "World", "rules": []},
            "extra_field": "should be allowed",
        }
        errors = validate("series_plan_core", data)
        assert len(errors) == 0

    def test_wrong_type_string_for_array(self):
        data = {
            "title": "Test",
            "slug": "test",
            "logline": "Story",
            "genre": "fantasy",  # Should be array
            "target_audience": "10代",
            "themes": ["adventure"],
            "selling_points": ["Unique"],
            "world": {"summary": "World", "rules": []},
        }
        errors = validate("series_plan_core", data)
        assert len(errors) > 0

    def test_valid_scene_draft(self):
        data = {
            "title": "シーン1",
            "content": "これはテストシーンの本文です。",
        }
        errors = validate("scene_draft", data)
        assert len(errors) == 0

    def test_valid_scene_revision(self):
        data = {
            "title": "シーン1改訂",
            "content": "改訂された本文です。",
            "changes": ["文体修正"],
        }
        errors = validate("scene_revision", data)
        assert len(errors) == 0

    def test_valid_scene_review(self):
        data = {
            "score": 85.0,
            "issues": [],
            "strengths": ["良い描写"],
            "recommendations": [],
        }
        errors = validate("scene_review", data)
        assert len(errors) == 0

    def test_scene_review_with_issues(self):
        data = {
            "score": 60.0,
            "issues": [
                {"severity": "重要", "category": "pov", "description": "視点が揺れている"}
            ],
            "strengths": [],
            "recommendations": ["視点を統一する"],
        }
        errors = validate("scene_review", data)
        assert len(errors) == 0

    def test_valid_bible_update(self):
        data = {
            "summary": "シーンの要約",
            "facts": [
                {"subject": "主人公", "predicate": "is", "object": "hero", "confidence": 1.0}
            ],
            "continuity_notes": ["ノート1"],
            "characters": [
                {"name": "主人公", "role": "主人公", "is_new": True}
            ],
            "foreshadowing": [
                {"type": "setup", "description": "剣の秘密"}
            ],
            "relationships": [],
            "subplots": [],
            "glossary": [],
            "world_rules": [],
        }
        errors = validate("scene_summary_and_bible_update", data)
        assert len(errors) == 0

    def test_valid_volume_design(self):
        data = {
            "title": "第1巻",
            "premise": "始まりの物語",
            "chapters": [
                {
                    "title": "プロローグ",
                    "purpose": "導入",
                },
            ],
        }
        errors = validate("volume_design", data)
        assert len(errors) == 0

    def test_valid_chapter_design(self):
        data = {
            "number": 1,
            "title": "プロローグ",
            "purpose": "導入",
            "theme": "信頼",
            "emotional_arc": "不安→希望",
        }
        errors = validate("chapter_design", data)
        assert len(errors) == 0

    def test_valid_scene_design(self):
        data = {
            "title": "出会い",
            "goal": "主人公を紹介する",
            "outcome": "旅立つ",
            "conflict": "葛藤なし",
            "pov": "主人公",
            "characters": ["主人公"],
        }
        errors = validate("scene_design", data)
        assert len(errors) == 0

    def test_unknown_schema_returns_no_errors(self):
        """Unknown schema should return empty errors (no validation)."""
        errors = validate("nonexistent", {"any": "data"})
        assert errors == []


# ── validate_or_raise ──────────────────────────────────────────────────

class TestValidateOrRaise:
    def test_valid_data_no_raise(self):
        data = {
            "title": "Test",
            "slug": "test",
            "logline": "Story",
            "genre": ["fantasy"],
            "target_audience": "10代",
            "themes": ["adventure"],
            "selling_points": ["Unique"],
            "world": {"summary": "World", "rules": []},
        }
        # Should not raise
        validate_or_raise("series_plan_core", data)

    def test_invalid_data_raises(self):
        data = {"title": "Test"}
        with pytest.raises(Exception):
            validate_or_raise("series_plan_core", data)


# ── Schema field coverage ──────────────────────────────────────────────

class TestSchemaFieldCoverage:
    """Verify that all expected schemas have the right fields."""

    def test_series_plan_core_has_world(self):
        schema = get_schema("series_plan_core")
        assert "world" in schema["properties"]

    def test_series_plan_core_has_characters(self):
        schema = get_schema("series_plan_core")
        assert "main_characters" in schema["properties"]

    def test_series_plan_core_has_volumes(self):
        schema = get_schema("series_plan_core")
        assert "planned_volumes" in schema["properties"]

    def test_volume_design_has_chapters(self):
        schema = get_schema("volume_design")
        assert "chapters" in schema["properties"]

    def test_chapter_design_has_theme(self):
        schema = get_schema("chapter_design")
        assert "theme" in schema["properties"]

    def test_chapter_design_has_emotional_arc(self):
        schema = get_schema("chapter_design")
        assert "emotional_arc" in schema["properties"]

    def test_scene_design_has_pov(self):
        schema = get_schema("scene_design")
        assert "pov" in schema["properties"]

    def test_scene_design_has_characters(self):
        schema = get_schema("scene_design")
        assert "characters" in schema["properties"]

    def test_scene_review_has_dimensions(self):
        schema = get_schema("scene_review")
        props = schema["properties"]
        assert "dimensions" in props

    def test_bible_update_has_all_fields(self):
        schema = get_schema("scene_summary_and_bible_update")
        props = schema["properties"]
        for field in [
            "summary", "facts", "continuity_notes", "characters",
            "foreshadowing", "relationships", "subplots", "glossary", "world_rules",
        ]:
            assert field in props, f"Missing field in bible_update: {field}"
