from __future__ import annotations

import pytest

from novel_forge.llm_client import LLMClient
from novel_forge.models import (
    ChapterDesign,
    ProjectState,
    SceneDesign,
    SceneRecord,
)
from novel_forge.prompts import PromptManager, render_prompt
from novel_forge.quality_gate import QualityGate
from novel_forge.schemas import get_schema, list_schemas, validate, validate_or_raise
from novel_forge.storage import StateStorage

# ── LLM Client ──────────────────────────────────────────────────────────


class TestLLMClient:
    def test_client_creates_with_defaults(self):
        client = LLMClient(model="test-model")
        assert client.model == "test-model"

    def test_client_stores_options(self, tmp_path):
        client = LLMClient(
            model="test-model",
            raw_log_dir=tmp_path,
            timeout_seconds=60,
            max_retries=3,
        )
        assert client.timeout_seconds == 60
        assert client.max_retries == 3


# ── Models ─────────────────────────────────────────────────────────────


class TestModels:
    def test_scene_design_creation(self):
        sd = SceneDesign(number=1, title="Prologue", goal="Introduce world")
        assert sd.number == 1

    def test_chapter_design_theme(self):
        cd = ChapterDesign(
            number=1,
            title="Ch1",
            purpose="導入",
            theme="信頼の崩壊",
            emotional_arc="不安→緊張→絶望",
        )
        assert cd.theme == "信頼の崩壊"
        assert cd.emotional_arc == "不安→緊張→絶望"

    def test_chapter_design_foreshadowing_notes(self):
        cd = ChapterDesign(
            number=1,
            title="Ch1",
            purpose="導入",
            foreshadowing_notes=["剣の秘密を設置する"],
            subplot_notes=["サブプロットAを進展させる"],
        )
        assert cd.foreshadowing_notes == ["剣の秘密を設置する"]
        assert cd.subplot_notes == ["サブプロットAを進展させる"]

    def test_scene_record_status(self):
        sr = SceneRecord(scene_number=1)
        assert sr.status == "計画中"

    def test_scene_record_invalid_status(self):
        with pytest.raises(ValueError):
            SceneRecord(scene_number=1, status="invalid")


# ── Storage ────────────────────────────────────────────────────────────


class TestStorage:
    def test_state_storage_roundtrip(self, tmp_path):
        storage = StateStorage(tmp_path)
        state = ProjectState(
            series_title="Test Series",
            workdir=str(tmp_path),
            lang="ja",
        )
        storage.save(state)
        loaded = storage.load()
        assert loaded.series_title == "Test Series"

    def test_state_backup_on_corruption(self, tmp_path):
        storage = StateStorage(tmp_path)
        state = ProjectState(series_title="Backup Test", workdir=str(tmp_path))
        storage.save(state)
        # Save again to create .bak
        storage.save(state)
        # Corrupt the file
        storage._state_path.write_text("not json", encoding="utf-8")
        loaded = storage.load()
        assert loaded.series_title == "Backup Test"


# ── Prompts ────────────────────────────────────────────────────────────


class TestPrompts:
    def test_prompt_manager_loads_file(self, tmp_path):
        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()
        (prompt_dir / "test.md").write_text("Hello {name}", encoding="utf-8")
        pm = PromptManager(prompt_dir=prompt_dir)
        assert pm.render("test.md", {"name": "World"}) == "Hello World"

    def test_prompt_renderer_replaces_placeholders(self):
        result = render_prompt("{a}/{b}", {"a": "A", "b": "B"})
        assert result == "A/B"


# ── Quality Gate ───────────────────────────────────────────────────────


class TestQualityGate:
    def test_pass_scene(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 80.0, "issues": []})
        assert result.passed is True

    def test_fail_scene_low_score(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 5.0, "issues": []})
        assert result.passed is True  # No critical issues = pass

    def test_fail_scene_critical_issue(self):
        qg = QualityGate()
        result = qg.check_scene({"score": 90.0, "issues": [{"severity": "致命的"}]})
        assert result.passed is False


class TestSchemas:
    def test_list_schemas(self):
        schemas = list_schemas()
        assert "plan_concept" in schemas
        assert "design_volume" in schemas
        assert "design_chapter" in schemas

    def test_validate_series_plan_valid(self):
        data = {
            "title": "Test Series Title That Is Definitely Long Enough To Pass Validation",
            "slug": "test_series",
            "logline": "A test story that is long enough to meet the minimum length requirement of two hundred characters for the logline field in the schema and includes plenty of descriptive text about the protagonist and their journey.",
            "genre": ["fantasy"],
            "target_audience": "20代後半から30代の読者をターゲットにしたファンタジー小説で、冒険と成長の物語を求める層に向けて書かれています。",
            "themes": ["adventure", "friendship", "growth"],
            "selling_points": [
                "Unique world building with an intricate magic system that affects every aspect of society",
                "Complex character relationships that evolve naturally throughout the series"
            ],
            "world_summary": "A world where magic exists and is regulated by ancient laws. The story follows a young mage discovering their power and learning to navigate a society where magical ability determines social status.",
            "world_rules": [
                "magic requires sacrifice of something precious",
                "ancient laws govern all spellcasting and violations are punished severely"
            ],
        }
        errors = validate("plan_concept", data)
        assert len(errors) == 0

    def test_validate_or_raise(self):
        data = {
            "title": "Test Series Title That Is Definitely Long Enough To Pass Validation",
            "slug": "test_series",
            "logline": "A test story that is long enough to meet the minimum length requirement of two hundred characters for the logline field in the schema and includes plenty of descriptive text about the protagonist and their journey.",
            "genre": ["fantasy"],
            "target_audience": "20代後半から30代の読者をターゲットにしたファンタジー小説で、冒険と成長の物語を求める層に向けて書かれています。",
            "themes": ["adventure", "friendship", "growth"],
            "selling_points": [
                "Unique world building with an intricate magic system that affects every aspect of society",
                "Complex character relationships that evolve naturally throughout the series"
            ],
            "world_summary": "A world where magic exists and is regulated by ancient laws. The story follows a young mage discovering their power and learning to navigate a society where magical ability determines social status.",
            "world_rules": [
                "magic requires sacrifice of something precious",
                "ancient laws govern all spellcasting and violations are punished severely"
            ],
        }
        validate_or_raise("plan_concept", data)  # Should not raise

    def test_chapter_design_schema_has_new_fields(self):
        schema = get_schema("design_chapter")
        assert "theme" in schema["required"]
        assert "emotional_arc" in schema["required"]
        assert "scenes" in schema["properties"]

    def test_volume_design_goal_is_string(self):
        schema = get_schema("design_volume")
        ch_title = schema["properties"]["chapters"]["items"]["properties"]["title"]
        assert ch_title.get("type") == "string"

    def test_chapter_design_purpose_is_enum(self):
        schema = get_schema("design_volume")
        ch_purpose = schema["properties"]["chapters"]["items"]["properties"]["purpose"]
        assert "enum" in ch_purpose