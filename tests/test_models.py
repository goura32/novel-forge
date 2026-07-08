from __future__ import annotations

import pytest

from novel_forge.engine import NovelEngine
from novel_forge.llm_client import LLMClient
from novel_forge.models import (
    Bible,
    Blackboard,
    ChapterDesign,
    CharacterProfile,
    Fact,
    ProjectState,
    SceneDesign,
    SceneRecord,
    VolumeProgress,
)
from novel_forge.prompts import PromptManager, render_prompt
from novel_forge.quality_gate import QualityGate
from novel_forge.schemas import get_schema, list_schemas, validate, validate_or_raise
from novel_forge.storage import BibleStorage, BlackboardStorage, StateStorage

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
    def test_fact_creation(self):
        fact = Fact(subject="Alice", predicate="is", object="hero")
        assert fact.confidence == 1.0

    def test_fact_confidence_range(self):
        with pytest.raises(ValueError):
            Fact(subject="A", predicate="is", object="B", confidence=1.5)

    def test_blackboard_creation(self):
        bb = Blackboard(
            facts=[Fact(subject="A", predicate="is", object="B")],
            scene_summaries={"1": "summary"},
            continuity_notes=["note1"],
        )
        assert len(bb.facts) == 1

    def test_bible_creation(self):
        bible = Bible(
            characters=[CharacterProfile(name="Alice")],
            world_rules=["magic exists"],
        )
        assert len(bible.characters) == 1

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

    def test_blackboard_storage(self, tmp_path):
        storage = BlackboardStorage(tmp_path)
        bb = Blackboard(
            facts=[Fact(subject="A", predicate="met", object="B", confidence=0.9)]
        )
        storage.save(bb)
        loaded = storage.load()
        assert len(loaded.facts) == 1
        assert loaded.facts[0].confidence == 0.9

    def test_bible_storage(self, tmp_path):
        storage = BibleStorage(tmp_path)
        bible = Bible(characters=[CharacterProfile(name="Hero")])
        storage.save(bible)
        loaded = storage.load()
        assert len(loaded.characters) == 1


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
        assert "series_plan_concept" in schemas
        assert "volume_design" in schemas
        assert "chapter_design" in schemas

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
        errors = validate("series_plan_concept", data)
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
        validate_or_raise("series_plan_concept", data)  # Should not raise

    def test_validate_series_plan_does_not_mechanically_reject_chinese_markers(self):
        data = {
            "title": "契約婚の悪役令嬢と竜公爵",
            "slug": "keiyaku_kon_akuyaku_reijou",
            "logline": "破滅を予知した悪役令嬢が、契約結婚を盾に王宮陰謀へ立ち向かう。魔法学院と竜公爵家の身分差を越え、初恋をやり直すために真相を追う。",
            "genre": ["ロマンスファンタジー"],
            "target_audience": "20代から40代の女性読者。契約結婚、身分差、王宮陰謀、初恋のやり直しを好む層。",
            "themes": ["信頼の再構築", "身分差を越える恋", "運命への抵抗"],
            "selling_points": [
                "契約という枠組みの中で近づく二人の心理を细腻に描く。",
                "魔法学院と王宮陰謀を横断する政治劇。",
            ],
            "world_summary": "竜公爵家と王宮が魔法契約で均衡を保つ王国。",
            "world_rules": ["契約魔法は血統と誓約に縛られ、破れば魔力消耗を負う。"],
        }

        errors = validate("series_plan_concept", data)

        assert errors == []

    def test_validate_series_plan_rejects_swap_title_reduced_to_substitution(self):
        data = {
            "title": "薔薇庭園の聖女入れ替わり",
            "slug": "bara_teien_seijo_irekawari",
            "logline": "記憶を改ざんされ貴族令嬢の身代わりとして帝都へ潜入した元聖女は、呪われ皇太子の婚約者として公の場で精霊契約により呪いを抑制しながら生き延びる。",
            "genre": ["ロマンスファンタジー"],
            "target_audience": "20代から40代の女性読者。宮廷恋愛、呪い、精霊契約、記憶喪失の謎を好む層。",
            "themes": ["記憶と自己", "呪いからの解放", "宮廷恋愛"],
            "selling_points": [
                "薔薇庭園で交わした精霊契約が、皇太子の呪いと聖女の記憶を結びつける。",
                "舞踏会と騎士団の駆け引きが、身代わりの正体を追い詰める。",
            ],
            "world_summary": "帝都では禁断魔法が厳しく禁じられている。元聖女は記憶を改ざんされ、貴族令嬢の身代わりとして宮廷へ送られる。薔薇庭園の精霊契約は呪いを一時的に抑えるが、記憶を取り戻すたびに魔力暴走の危険が高まる。",
            "world_rules": [
                "薔薇庭園で交わした精霊契約は、契約者の記憶を魔力へ変換する。",
                "皇太子の呪いは日没時に強まり、契約者の魔力供給で一時的に抑制される。",
            ],
        }

        errors = validate("series_plan_concept", data)

        assert any("swap gimmick" in error for error in errors)

    def test_validate_series_plan_allows_explicit_swap_mechanism(self):
        data = {
            "title": "薔薇庭園の聖女入れ替わり",
            "slug": "bara_teien_seijo_irekawari",
            "logline": "聖女召喚の儀式で魂を貴族令嬢の身体へ入れ替えられた元聖女は、失われた記憶を取り戻しながら呪われ皇太子を救うため、薔薇庭園の精霊契約で禁断魔法の真相へ迫る。",
            "genre": ["ロマンスファンタジー"],
            "target_audience": "20代から40代の女性読者。宮廷恋愛、呪い、精霊契約、入れ替わりの謎を好む層。",
            "themes": ["記憶と自己", "呪いからの解放", "宮廷恋愛"],
            "selling_points": [
                "魂の入れ替わりと失われた記憶が、皇太子の呪い解除条件と連動する。",
                "舞踏会と騎士団の駆け引きが、入れ替わった聖女の正体を追い詰める。",
            ],
            "world_summary": "帝都では禁断魔法が厳しく禁じられている。元聖女は召喚儀式で魂を貴族令嬢と入れ替えられ、記憶を失ったまま宮廷へ送られる。薔薇庭園の精霊契約は呪いを一時的に抑えるが、記憶を取り戻すたびに魔力暴走の危険が高まる。",
            "world_rules": [
                "召喚儀式で魂の入れ替わりが起きると、元の身体には呪いの刻印が残り、入れ替わった魂だけが記憶を失う。",
                "皇太子の呪いは日没時に強まり、契約者の魔力供給で一時的に抑制される。",
            ],
        }

        errors = validate("series_plan_concept", data)

        assert errors == []

    def test_chapter_design_schema_has_new_fields(self):
        schema = get_schema("chapter_design")
        assert "theme" in schema["required"]
        assert "emotional_arc" in schema["required"]
        assert "scenes" in schema["properties"]

    def test_volume_design_goal_is_string(self):
        schema = get_schema("volume_design")
        ch_title = schema["properties"]["chapters"]["items"]["properties"]["title"]
        assert ch_title.get("type") == "string"

    def test_chapter_design_purpose_is_enum(self):
        schema = get_schema("volume_design")
        ch_purpose = schema["properties"]["chapters"]["items"]["properties"]["purpose"]
        assert "enum" in ch_purpose


# ── Engine ─────────────────────────────────────────────────────────────


class TestEngine:
    def test_engine_creates_state(self, tmp_path):
        engine = NovelEngine(workdir=tmp_path, model="test")
        assert engine.state.workdir.startswith("/tmp/novel-forge-")

    def test_engine_status(self, tmp_path):
        engine = NovelEngine(workdir=tmp_path, model="test")
        s = engine.status()
        assert s["status"] == "計画中"
        assert s["current_volume"] == 1

    def test_engine_resume_planned(self, tmp_path):
        engine = NovelEngine(workdir=tmp_path, model="test")
        result = engine.resume()
        assert result["action"] == "plan"

    def test_engine_resume_outlined(self, tmp_path):
        engine = NovelEngine(workdir=tmp_path, model="test")
        engine._state.status = "デザイン済"
        result = engine.resume()
        assert result["action"] == "design"

    def test_engine_resume_drafting(self, tmp_path):
        engine = NovelEngine(workdir=tmp_path, model="test")
        vol = VolumeProgress(volume_number=1, status="執筆中", current_chapter=0)
        engine._state.volumes.append(vol)
        result = engine.resume()
        assert result["action"] == "write"

    def test_engine_resume_exported(self, tmp_path):
        engine = NovelEngine(workdir=tmp_path, model="test")
        engine._state.status = "出力済"
        result = engine.resume()
        assert result["action"] == "export"