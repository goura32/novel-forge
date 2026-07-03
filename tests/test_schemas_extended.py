"""Extended tests for schemas.py — validation edge cases and schema coverage."""

from __future__ import annotations

import pytest

from novel_forge.schemas import get_schema, list_schemas, validate, validate_or_raise

# ── list_schemas ────────────────────────────────────────────────────────


class TestListSchemas:
    def test_returns_list(self):
        schemas = list_schemas()
        assert isinstance(schemas, list)

    def test_contains_core_schemas(self):
        schemas = list_schemas()
        expected = [
            "series_plan_concept",
            "series_plan_characters",
            "series_plan_volumes",
            "volume_design",
            "chapter_design",
            "scene_design",
            "scene_draft",
            "review",
            "scene_summary_and_bible_update",
        ]
        for name in expected:
            assert name in schemas, f"Missing schema: {name}"

    def test_each_schema_has_properties(self):
        schemas = list_schemas()
        assert isinstance(schemas, list), "list_schemas should return list"
        for name in schemas:
            schema = get_schema(name)
            assert isinstance(schema, dict), f"{name} schema should be dict"
            assert "properties" in schema, f"{name} schema should have properties"


# ── get_schema ──────────────────────────────────────────────────────────


class TestGetSchema:
    def test_returns_valid_schema(self):
        schema = get_schema("series_plan_concept")
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
            "world_summary": "Magic world",
            "world_rules": ["magic exists"],
        }
        errors = validate("series_plan_concept", data)
        assert len(errors) == 0

    def test_missing_required_field(self):
        data = {"title": "Test"}
        errors = validate("series_plan_concept", data)
        assert len(errors) > 0

    def test_empty_data(self):
        errors = validate("series_plan_concept", {})
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
            "world_summary": "World",
            "world_rules": [],
            "extra_field": "should be allowed",
        }
        errors = validate("series_plan_concept", data)
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
        errors = validate("series_plan_concept", data)
        assert len(errors) > 0

    def test_valid_scene_draft(self):
        data = {
            "title": "シーン1",
            "content": "これはテストシーンの本文です。" * 200,
        }
        errors = validate("scene_draft", data)
        assert len(errors) == 0

    def test_valid_scene_draft_revision(self):
        """Scene revision now uses the same schema as scene_draft."""
        data = {
            "title": "シーン1改訂",
            "content": "改訂された本文です。" * 400,
        }
        errors = validate("scene_draft", data)
        assert len(errors) == 0

    def test_valid_scene_review(self):
        data = {
            "issues": [],
            "revision_needed": False,
            "ready_for_publication": True,
        }
        errors = validate("scene_review", data)
        assert len(errors) == 0

    def test_scene_review_with_issues(self):
        data = {
            "issues": [
                {
                    "severity": "重要",
                    "field": "content",
                    "category": "POV一貫性",
                    "description": "視点が揺れている",
                    "suggestion": "視点を統一する",
                    "before": "揺れている",
                    "after": "統一する",
                }
            ],
        }
        errors = validate("scene_review", data)
        assert len(errors) == 0

    def test_valid_bible_update(self):
        data = {
            "summary": "シーンの要約",
            "facts": [],
            "continuity_notes": [],
            "characters": [],
            "foreshadowing": [],
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
                {
                    "title": "事件の発生",
                    "purpose": "展開",
                },
                {
                    "title": "決戦",
                    "purpose": "収束",
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
            "outcome": "主人公が旅立つ決意を固める",
            "scenes": [
                {
                    "title": "出発の朝",
                    "goal": "決意を示す",
                    "outcome": "荷物をまとめる",
                    "pov": "主人公",
                }
            ],
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
            "world_summary": "World",
            "world_rules": [],
        }
        # Should not raise
        validate_or_raise("series_plan_concept", data)

    def test_invalid_data_raises(self):
        data = {"title": "Test"}
        with pytest.raises(Exception, match="Schema validation failed"):
            validate_or_raise("series_plan_concept", data)


# ── Schema field coverage ──────────────────────────────────────────────


class TestSchemaFieldCoverage:
    """Verify that all expected schemas have the right fields."""

    def test_series_plan_concept_has_world(self):
        schema = get_schema("series_plan_concept")
        assert "world_summary" in schema["properties"]
        assert "world_rules" in schema["properties"]

    def test_series_plan_concept_has_slug(self):
        schema = get_schema("series_plan_concept")
        assert "slug" in schema["properties"]

    def test_series_plan_concept_has_title(self):
        schema = get_schema("series_plan_concept")
        assert "title" in schema["properties"]

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

    def test_scene_review_has_issues(self):
        schema = get_schema("review")
        props = schema["properties"]
        assert "issues" in props

    def test_bible_update_has_all_fields(self):
        schema = get_schema("scene_summary_and_bible_update")
        props = schema["properties"]
        for field in [
            "summary",
            "facts",
            "continuity_notes",
            "characters",
            "foreshadowing",
            "relationships",
            "subplots",
            "glossary",
            "world_rules",
        ]:
            assert field in props, f"Missing field in bible_update: {field}"
