"""Public NovelEngine design/write must obey the Series Bible v2 boundary."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from novel_forge.canon.models import Canon
from novel_forge.canon.public_runtime import V2ProjectRuntime
from novel_forge.canon.store import BibleFactory, CanonEventStore
from novel_forge.engine import NovelEngine


class RecordingLLM:
    """Minimal fake that records the exact public writer boundary."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _is_schema_echo(result: dict[str, Any]) -> bool:
        return False

    def complete_json(
        self,
        kind: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any] | None = None,
        seed_offset: int = 0,
    ) -> dict[str, Any]:
        del system_prompt, schema, seed_offset
        self.calls.append((kind, user_prompt))
        if kind == "volume_design":
            return {
                "title": "第一巻",
                "premise": "導入",
                "chapters": [{"title": "第一章", "purpose": "導入"}],
            }
        if kind == "chapter_design":
            return {
                "title": "第一章",
                "purpose": "導入",
                "theme": "選択",
                "emotional_arc": "ためらいから決意へ",
                "outcome": "封筒を持ち帰る",
                "scenes": [{
                    "title": "封筒",
                    "pov": "澪",
                    "goal": "封筒を確認する",
                    "conflict": "閉館時刻が迫る",
                    "outcome": "封筒を持ち帰る",
                    "characters": ["澪"],
                    "key_events": ["返却台で封筒を見つける"],
                    "setting": "市立図書館",
                }],
            }
        if kind == "scene_design":
            return {
                "number": 1,
                "chapter_number": 1,
                "title": "封筒",
                "goal": "封筒を確認する",
                "conflict": "閉館時刻が迫る",
                "outcome": "封筒を持ち帰る",
            }
        if kind == "scene_draft":
            return {"title": "封筒", "content": "澪は返却台の封筒をそっと手に取った。"}
        if kind == "review":
            return {"issues": []}
        raise AssertionError(f"unexpected LLM kind: {kind}")


def _seeded_engine(tmp_path: Path) -> tuple[NovelEngine, RecordingLLM]:
    llm = RecordingLLM()
    engine = NovelEngine(workdir=tmp_path)
    engine._llm = llm  # type: ignore[assignment]
    engine._slug = "v2_series"
    engine._move_to_final_dir()
    plan = {
        "title": "v2 series",
        "genre": ["mystery"],
        "planned_volumes": [{"number": 1, "title": "第一巻", "premise": "導入"}],
        "main_characters": [{"name": "澪", "role": "主人公", "state": "雨宿り中"}],
        "locations": [{"name": "市立図書館", "kind": "building", "current_state": "閉館準備中", "immutable_constraints": ["閉館後は閲覧室に入れない"]}],
        "world_rules": ["封筒の差出人は開封まで確認できない"],
    }
    (engine._series_dir / "series_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    CanonEventStore(engine._series_dir / "canon").write_seed(BibleFactory.create_seed(plan))
    engine._state.current_volume = 1
    return engine, llm


def test_public_design_and_write_persist_v2_artifacts_and_keep_writer_boundary(tmp_path: Path) -> None:
    engine, llm = _seeded_engine(tmp_path)

    design = engine.design(1)

    artifact = engine._series_dir / "vol01" / "v2_design.json"
    assert artifact.exists(), "public design must persist v2 typed artifacts"
    saved = json.loads(artifact.read_text(encoding="utf-8"))
    assert saved["version"] == 2
    assert saved["scenes"][0]["writer_context"]
    assert design["version"] == 2

    engine.write(1)

    draft_prompts = [prompt for kind, prompt in llm.calls if kind == "scene_draft"]
    assert len(draft_prompts) == 1
    prompt = draft_prompts[0]
    assert "ULTRA_SECRET_PROPOSITION" not in prompt
    assert "canon_events.jsonl" not in prompt
    assert "bible_seed.json" not in prompt
    assert "直前シーン要約" in prompt
    assert (engine._series_dir / "vol01" / "scene_summaries.json").exists()


def test_scene_artifact_resolves_declared_pov_before_character_list(tmp_path: Path) -> None:
    canon = Canon.model_validate({
        "schema_version": 2,
        "series": {"id": "series", "title": "test"},
        "characters": [
            {"id": "char_001", "identity": {"kind": "named", "display_name": "先頭人物"}, "importance": "core", "tracking_level": "full", "narrative_function": "相棒", "continuity_card": {"current_state": "待機中"}},
            {"id": "char_002", "identity": {"kind": "named", "display_name": "POV人物"}, "importance": "core", "tracking_level": "full", "narrative_function": "主人公", "continuity_card": {"current_state": "調査中"}},
        ],
        "locations": [{"id": "loc_001", "name": "図書館", "kind": "building", "immutable_constraints": ["夜は閉館する"], "current_state": "閉館前"}],
    })
    runtime = V2ProjectRuntime(tmp_path)

    scene = runtime.scene_artifact(
        volume=1,
        chapter=1,
        scene=1,
        raw={"pov": "POV人物", "characters": ["先頭人物"], "setting": "図書館", "title": "確認"},
        canon=canon,
    )

    assert scene.context_scope is not None
    assert scene.context_scope.pov_character is not None
    assert scene.context_scope.pov_character.id == "char_002"


def test_scene_artifact_falls_back_to_canon_location_for_unknown_generated_setting(tmp_path: Path) -> None:
    canon = BibleFactory.create_seed({
        "title": "T",
        "main_characters": [{"name": "澪", "role": "主人公"}],
        "locations": [{"name": "図書館", "kind": "building", "current_state": "閉館前", "immutable_constraints": ["夜は閉館する"]}],
    })
    runtime = V2ProjectRuntime(tmp_path)

    scene = runtime.scene_artifact(
        volume=1, chapter=1, scene=1,
        raw={"pov": "澪", "setting": "存在しない港", "title": "確認"}, canon=canon,
    )

    assert scene.context_scope is not None
    assert scene.context_scope.setting is not None
    assert scene.context_scope.setting.id == canon.locations[0].id


def test_scene_artifact_rejects_secret_or_stable_id_in_writer_bound_fields(tmp_path: Path) -> None:
    canon = BibleFactory.create_seed({
        "title": "T",
        "main_characters": [
            {"name": "観測者", "role": "主人公"},
            {"name": "秘密の保持者", "role": "脇役"},
        ],
        "locations": [{"name": "図書館", "kind": "building", "current_state": "閉館前", "immutable_constraints": ["夜は閉館する"]}],
        "knowledge": [{
            "id": "know_secret", "proposition": "ULTRA_SECRET_PROPOSITION", "truth_status": "confirmed",
            "visibility": "secret", "holders": [{"holder": {"kind": "character", "id": "char_002"}, "state": "knows"}],
        }],
    })
    runtime = V2ProjectRuntime(tmp_path)

    with pytest.raises(ValueError, match="writer boundary"):
        runtime.scene_artifact(
            volume=1, chapter=1, scene=1,
            raw={
                "pov": "観測者", "setting": "図書館", "title": "確認",
                "goal": "ULTRA_SECRET_PROPOSITION char_001 を確認する",
            },
            canon=canon,
        )

def test_write_checkpoints_each_summary_before_a_later_scene_failure(tmp_path: Path) -> None:
    engine, llm = _seeded_engine(tmp_path)
    engine.design(1)
    artifact_path = engine._series_dir / "vol01" / "v2_design.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    second = copy.deepcopy(artifact["scenes"][0])
    second["scene_id"] = "vol01_ch01_sc002"
    second["scene_number"] = 2
    second["source_location"]["ordinal"] = 2
    artifact["scenes"].append(second)
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False), encoding="utf-8")

    complete_json = llm.complete_json
    draft_count = 0

    def fail_on_second_draft(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal draft_count
        if args[0] == "scene_draft":
            draft_count += 1
            if draft_count == 2:
                raise RuntimeError("simulated interruption")
        return complete_json(*args, **kwargs)

    llm.complete_json = fail_on_second_draft  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="simulated interruption"):
        engine.write(1)

    summaries = json.loads((engine._series_dir / "vol01" / "scene_summaries.json").read_text(encoding="utf-8"))
    assert summaries["vol01_ch01_sc001"] == "澪は返却台の封筒をそっと手に取った。"

    llm.complete_json = complete_json  # type: ignore[method-assign]
    engine.write(1)
    resumed_drafts = [prompt for kind, prompt in llm.calls if kind == "scene_draft"]
    assert "澪は返却台の封筒をそっと手に取った。" in resumed_drafts[-1]


def test_writer_boundary_allows_plain_text_mentioning_bible(tmp_path: Path) -> None:
    canon = BibleFactory.create_seed({
        "title": "T",
        "main_characters": [{"name": "澪", "role": "主人公"}],
        "locations": [{"name": "図書館", "kind": "building", "current_state": "閉館前", "immutable_constraints": ["夜は閉館する"]}],
    })
    runtime = V2ProjectRuntime(tmp_path)
    scene = runtime.scene_artifact(
        volume=1, chapter=1, scene=1,
        raw={"pov": "澪", "setting": "図書館", "title": "確認", "goal": "古い聖書(bible)を調べる"},
        canon=canon,
    )
    payload = runtime.writer_payload(scene)
    assert "bible" in payload["scene_brief"]["goal"]


def test_public_v2_design_and_write_do_not_import_v1_runtime_collaborators() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "novel_forge" / "engine"
    forbidden = ("BibleManager", "BibleStorage", "BlackboardStorage", "ContextBuilder", "SceneWriter")
    for name in ("design.py", "write.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden), name
