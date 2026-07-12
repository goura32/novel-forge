"""Extended tests for schemas.py — validation edge cases and schema coverage."""

from __future__ import annotations

import logging

import pytest
from fixtures.factories import design_volume_data, plan_concept_data

from novel_forge.schemas import get_schema, list_schemas, validate, validate_or_raise

# ── list_schemas ────────────────────────────────────────────────────────


class TestListSchemas:
    def test_returns_list(self):
        schemas = list_schemas()
        assert isinstance(schemas, list)

    def test_contains_core_schemas(self):
        schemas = list_schemas()
        expected = [
            "plan_concept",
            "plan_characters",
            "plan_volumes",
            "design_volume",
            "design_chapter",
            "design_scene",
            "write_draft",
            "review_issues",
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
        schema = get_schema("plan_concept")
        assert "properties" in schema
        assert "title" in schema["properties"]

    def test_unknown_schema_raises(self):
        with pytest.raises(FileNotFoundError):
            get_schema("nonexistent_schema")


# ── validate ────────────────────────────────────────────────────────────


class TestValidate:
    def test_valid_series_plan(self):
        data = plan_concept_data()
        errors = validate("plan_concept", data)
        assert len(errors) == 0

    def test_missing_required_field(self):
        data = {"title": "Test"}
        errors = validate("plan_concept", data)
        assert len(errors) > 0

    def test_empty_data(self):
        errors = validate("plan_concept", {})
        assert len(errors) > 0

    def test_unknown_schema_name_returns_error(self):
        errors = validate("nonexistent_schema", {})
        assert errors == ["Schema not found: nonexistent_schema"]

    def test_extra_fields_allowed(self):
        """Schemas should tolerate harmless unknown LLM fields."""
        data = plan_concept_data(extra_field="should be ignored by consumers")
        errors = validate("plan_concept", data)
        assert errors == []

    def test_object_for_array_field_logs_warning(self, caplog):
        data = plan_concept_data()
        data["themes"] = {"unexpected": "object"}

        with caplog.at_level(logging.WARNING, logger="novel_forge.schemas"):
            validate("plan_concept", data)

        assert "Coerced schema array field 'themes' from object to []" in caplog.text

    def test_wrong_type_string_for_array(self):
        data = {
            "title": "Test",
            "slug": "test_series",
            "logline": "Story",
            "genre": "fantasy",  # Should be array
            "target_audience": "10代",
            "themes": ["adventure"],
            "selling_points": ["Unique"],
            "world": {"summary": "World", "rules": []},
        }
        errors = validate("plan_concept", data)
        assert len(errors) > 0

    def test_plan_concept_requires_main_characters_and_locations(self):
        schema = get_schema("plan_concept")
        assert "main_characters" in schema["required"]
        assert "locations" in schema["required"]
        data = {
            "title": "シーン1",
            "content": "これはテストシーンの本文です。" * 200,
        }
        errors = validate("write_draft", data)
        assert len(errors) == 0

    def test_valid_scene_draft_revision(self):
        """Scene revision now uses the same schema as scene_draft."""
        data = {
            "title": "シーン1改訂",
            "content": "改訂された本文です。" * 400,
        }
        errors = validate("write_draft", data)
        assert len(errors) == 0

    def test_valid_review(self):
        data = {"issues": []}
        errors = validate("review_issues", data)
        assert len(errors) == 0

    def test_scene_review_with_issues(self):
        data = {
            "issues": [
                {
                    "severity": "重要",
                    "field": "POV一貫性",
                    "description": "視点が揺れている",
                    "suggestion": "視点を統一する",
                    "before": "揺れている",
                    "after": "統一する",
                }
            ],
        }
        errors = validate("review_issues", data)
        assert len(errors) == 0

    def test_review_allows_empty_before_for_missing_field_issue(self):
        data = {
            "issues": [
                {
                    "severity": "重要",
                    "field": "章設計.結果",
                    "description": "章の結果が記述されていません。",
                    "suggestion": "次章へつながる結果を追加する",
                    "before": "",
                    "after": "主人公が依頼を受け入れ、次章の調査へ向かう動機を得る。",
                }
            ],
        }
        errors = validate("review_issues", data)
        assert errors == []

    def test_review_allows_empty_after_at_schema_level(self):
        data = {
            "issues": [
                {
                    "severity": "重要",
                    "field": "章設計.結果",
                    "description": "章の結果が記述されていません。",
                    "suggestion": "次章へつながる結果を追加する",
                    "before": "",
                    "after": "",
                }
            ],
        }
        errors = validate("review_issues", data)
        assert errors == []

    def test_review_tolerates_legacy_readiness_fields_at_schema_level(self):
        data = {
            "ready_for_publication": True,
            "overall_assessment": "問題ありません。",
            "strengths": ["葛藤は明確"],
            "issues": [],
        }
        errors = validate("review_issues", data)
        assert errors == []

    def test_review_tolerates_legacy_publication_blocking_issue_field_at_schema_level(self):
        data = {
            "issues": [
                {
                    "severity": "重要",
                    "field": "POV一貫性",
                    "description": "視点が揺れている",
                    "suggestion": "視点を統一する",
                    "before": "揺れている",
                    "after": "統一する",
                    "publication_blocking": True,
                }
            ],
        }
        errors = validate("review_issues", data)
        assert errors == []

    def test_review_allows_single_actionable_minor_issue(self):
        data = {
            "issues": [
                {
                    "severity": "軽微",
                    "field": "表現",
                    "description": "表現がやや平板",
                    "suggestion": "描写を増やす",
                    "before": "歩いた",
                    "after": "砂利を踏みしめて歩いた",
                }
            ],
        }
        errors = validate("review_issues", data)
        assert errors == []

    def test_valid_volume_design(self):
        data = design_volume_data()
        errors = validate("design_volume", data)
        assert len(errors) == 0

    def test_valid_chapter_design(self):
        data = {
            "title": "プロローグ 旅立ちの朝 その始まり",
            "purpose": "導入",
            "theme": "未知への挑戦と不安の克服、新たな世界への期待と恐れ",
            "emotional_arc": "不安から希望へ、小さな一歩を踏み出す勇気を得て前進する心情の変化",
            "outcome": "主人公が旅立つ決意を固め、最初の一歩を踏み出し新たな道へ進む",
            "chapter_turning_point": "父親の反対が理解へ変わり、主人公が戻れない一歩を踏み出す。",
            "chapter_hook": "門の外で未知の印が光り、次の出会いを予感させる。",
            "foreshadowing_notes": ["古い地図の印が後の目的地につながる"],
            "subplot_notes": ["家族との和解が主人公の帰還動機になる"],
            "scenes": [
                {
                    "title": "出発の朝 その始まり",
                    "pov": "主人公",
                    "goal": "家族に別れを告げ、旅立ちの準備を整えて家を出る決意をする",
                    "conflict": "不安と期待が入り混じる心情、父親の反対と母親の深い心配",
                    "outcome": "父親の理解を得て、旅立つ決意を新たにして門を出る",
                    "characters": ["主人公", "父親", "母親"],
                    "key_events": ["荷物の最終確認", "父親との対話", "母親の手作り弁当", "門を出る瞬間"],
                    "setting": "主人公の実家、早朝の台所から玄関、そして村道へ続く道",
                    "scene_function": "setup",
                    "emotional_shift": "不安から決意へ",
                    "hook": "台所に置かれた荷物の紐が震えている。",
                    "turning_point": "父親が反対を解き、古い地図を手渡す。",
                    "ending_hook": "門の外で地図と同じ印が光る。"
                },
                {
                    "title": "最初の道 新たな一歩",
                    "pov": "主人公",
                    "goal": "村を出て最初の街道を歩き始め、旅の第一歩を刻む",
                    "conflict": "未知の世界への恐怖と、後ろ髪を引かれる故郷への思い",
                    "outcome": "村の外れで老商人と出会い、旅の心構えを学び前を向く",
                    "characters": ["主人公", "老商人"],
                    "key_events": ["村を出る決意", "街道に出る", "老商人との会話"],
                    "setting": "村はずれの街道、朝もやの中に見える遠い山々",
                    "scene_function": "confrontation",
                    "emotional_shift": "郷愁から前進へ",
                    "hook": "朝もやの向こうで鈴の音が止まった。",
                    "turning_point": "老商人が主人公の地図を見て表情を変える。",
                    "ending_hook": "商人は地図の印を知っていると言い残す。"
                }
            ]
        }
        errors = validate("design_chapter", data)
        assert len(errors) == 0

    def test_chapter_design_coerces_enum_prefix_purpose(self):
        data = {
            "title": "プロローグ 旅立ちの朝 その始まり",
            "purpose": "導入：主人公の日常と世界観を提示する",
            "theme": "未知への挑戦と不安の克服、新たな世界への期待と恐れ",
            "emotional_arc": "不安から希望へ、小さな一歩を踏み出す勇気を得て前進する心情の変化",
            "outcome": "主人公が旅立つ決意を固め、最初の一歩を踏み出し新たな道へ進む",
            "chapter_turning_point": "主人公が戻れない一歩を踏み出す。",
            "chapter_hook": "門の外で未知の印が光る。",
            "foreshadowing_notes": ["古い地図の印"],
            "subplot_notes": ["家族との和解"],
            "scenes": [
                {
                    "title": "出発の朝",
                    "pov": "主人公",
                    "goal": "旅立ちの準備を整える",
                    "conflict": "不安と期待が入り混じる",
                    "outcome": "旅立つ決意を新たにする",
                    "characters": ["主人公"],
                    "key_events": ["荷物の最終確認"],
                    "setting": "主人公の実家、早朝の台所",
                }
            ],
        }

        errors = validate("design_chapter", data)

        assert len(errors) == 0
        assert data["purpose"] == "導入"

    def test_valid_scene_design(self):
        data = {
            "title": "出会いの朝",
            "goal": "主人公が家族に別れを告げ、旅立ちの準備を整えて家を出る",
            "conflict": "不安と期待が入り混じる心情、父親の反対と母親の心配",
            "outcome": "父親の理解を得て、旅立つ決意を新たにして門を出る",
            "pov_character_id": "char_001",
            "character_ids": ["char_001", "char_002", "char_003"],
            "key_events": ["荷物の最終確認", "父親との対話", "母親の弁当", "門を出る"],
            "location_id": "loc_001",
            "hook": "台所に置かれた荷物の紐が震えている。",
            "turning_point": "父親が反対を解き、古い地図を手渡す。",
            "emotional_arc": "不安から決意へ",
            "ending_hook": "門の外で地図と同じ印が光る。",
            "canon_updates": [{"operation": "set_character_state", "target_id": "char_001", "value": "旅立ちの決意を固める"}],
        }
        errors = validate("design_scene", data)
        assert len(errors) == 0

    def test_unknown_schema_returns_error(self):
        """Unknown schema should fail loudly instead of pretending validation passed."""
        errors = validate("nonexistent", {"any": "data"})
        assert errors == ["Schema not found: nonexistent"]


# ── validate_or_raise ──────────────────────────────────────────────────


class TestValidateOrRaise:
    def test_valid_data_no_raise(self):
        data = {
            "title": "Test Series Title That Is Definitely Long Enough To Pass Validation",
            "slug": "test_series",
            "logline": "A test story that is long enough to meet the minimum length requirement of two hundred characters for the logline field in the schema and includes plenty of descriptive text about the protagonist and their journey.",
            "genre": ["fantasy"],
            "target_audience": "20代後半から30代の読者をターゲットにしたファンタジー小説で、冒険と成長の物語を求める層に向けて書かれています。",
            "themes": ["adventure", "friendship", "growth"],
            "selling_points": ["Unique world building with an intricate magic system that affects every aspect of society", "Complex character relationships that evolve naturally throughout the series"],
            "world_summary": "A world where magic exists and is regulated by ancient laws. The story follows a young mage discovering their power and learning to navigate a society where magical ability determines social status.",
            "world_rules": ["magic requires sacrifice of something precious", "ancient laws govern all spellcasting and violations are punished severely"],
            "main_characters": [
                {"name": "リィナ", "role": "主人公", "stance": "味方", "motivation": "失われた記憶を取り戻す", "arc": "無力から自立へ"},
                {"name": "ルーク", "role": "相棒", "stance": "味方", "motivation": "契約の真実を守る", "arc": "歪みから再生へ"},
            ],
            "locations": [
                {"name": "覚醒室", "kind": "building", "current_state": "静寂に包まれた石室", "immutable_constraints": ["外部からの音が届かない"]},
            ],
        }
        # Should not raise
        validate_or_raise("plan_concept", data)

    def test_invalid_data_raises(self):
        data = {"title": "Test"}
        with pytest.raises(Exception, match="Schema validation failed"):
            validate_or_raise("plan_concept", data)


# ── Schema field coverage ──────────────────────────────────────────────


class TestSchemaFieldCoverage:
    """Verify that all expected schemas have the right fields."""

    def test_series_plan_concept_has_world(self):
        schema = get_schema("plan_concept")
        assert "world_summary" in schema["properties"]
        assert "world_rules" in schema["properties"]

    def test_series_plan_concept_has_slug(self):
        schema = get_schema("plan_concept")
        assert "slug" in schema["properties"]

    def test_series_plan_concept_has_title(self):
        schema = get_schema("plan_concept")
        assert "title" in schema["properties"]

    def test_volume_design_has_chapters(self):
        schema = get_schema("design_volume")
        assert "chapters" in schema["properties"]

    def test_chapter_design_has_theme(self):
        schema = get_schema("design_chapter")
        assert "theme" in schema["properties"]

    def test_chapter_design_has_emotional_arc(self):
        schema = get_schema("design_chapter")
        assert "emotional_arc" in schema["properties"]

    def test_scene_design_has_pov_character_id(self):
        schema = get_schema("design_scene")
        assert "pov_character_id" in schema["properties"]

    def test_scene_design_has_character_ids(self):
        schema = get_schema("design_scene")
        assert "character_ids" in schema["properties"]

    def test_scene_review_has_issues(self):
        schema = get_schema("review_issues")
        props = schema["properties"]
        assert "issues" in props
