"""§5–§6 design artifact + projection connection tests (Phase 3 core)."""

from __future__ import annotations

from novel_forge.canon.design import (
    CastCharacter,
    CastLocalRole,
    ChapterDesign,
    ContextScope,
    DesignIntent,
    RelationshipContext,
    SceneDesign,
    VolumeDesign,
    WriterContext,
)
from novel_forge.canon.models import EntityRef
from novel_forge.canon.projection import (
    attach_writer_context,
    build_scene_projection,
    projection_to_writer_context,
)
from novel_forge.canon.store import BibleFactory


def _make_canon() -> object:
    plan = {
        "series": {
            "id": "series",
            "title": "石都の声",
            "logline": "妹の声を追う旅",
            "constraints": [{"id": "c1", "statement": "魔法は使えない"}],
        },
        "characters": [
            {
                "id": "char_001",
                "identity": {"kind": "named", "display_name": "アレン", "aliases": []},
                "importance": "core",
                "tracking_level": "full",
                "narrative_function": "主人公",
                "profile": None,
                "continuity_card": {
                    "current_state": "妹の声を聞き捜索中",
                    "current_location": {"kind": "location", "id": "loc_stone_city"},
                },
            }
        ],
        "locations": [
            {"id": "loc_stone_city", "name": "石都", "kind": "city", "immutable_constraints": ["外壁封鎖"], "current_state": ""}
        ],
        "world_rules": [{"id": "rule_001", "name": "石都の掟", "statement": "石は記憶を残す"}],
    }
    return BibleFactory.create_seed(plan)


def test_scene_design_model_builds():
    sd = SceneDesign(
        scene_id="scn_001",
        context_scope=ContextScope(
            pov_character=EntityRef(kind="character", id="char_001"),
            setting=EntityRef(kind="location", id="loc_stone_city"),
            required_refs=[EntityRef(kind="world_rule", id="rule_001")],
        ),
        design_intent=DesignIntent(
            foreshadowing=[{"intent_key": "sister_voice", "action": "plant"}],
            cast=[{"target_scene_id": "scn_001", "entries": []}],
        ),
        cast=[
            CastCharacter(character=EntityRef(kind="character", id="char_001")),
            CastLocalRole(label="港の検問兵", count="one", scene_function="疑念を示す"),
        ],
        relationship_context=RelationshipContext(
            relationship_refs=[{"id": "rel_001"}],
            notes=["師弟の敵対"],
        ),
    )
    assert sd.scene_id == "scn_001"
    assert len(sd.cast) == 2
    assert sd.cast[0].character.id == "char_001"
    assert sd.cast[1].label == "港の検問兵"
    assert sd.status == "draft"


def test_chapter_volume_design_build():
    cd = ChapterDesign(chapter_id="ch_001")
    vd = VolumeDesign(volume_id="vol_001")
    assert cd.chapter_id == "ch_001"
    assert vd.volume_id == "vol_001"


def test_attach_writer_context_populates_manifest():
    canon = _make_canon()
    sd = SceneDesign(
        scene_id="scn_001",
        context_scope=ContextScope(
            pov_character=EntityRef(kind="character", id="char_001"),
            setting=EntityRef(kind="location", id="loc_stone_city"),
            required_refs=[EntityRef(kind="world_rule", id="rule_001")],
        ),
    )
    result = attach_writer_context(sd, canon)
    assert isinstance(result.writer_context, WriterContext)
    assert result.projection_manifest is not None
    assert result.projection_manifest.canon_digest.startswith("sha256:")
    # pov identity + current state must be projected (P0)
    assert result.writer_context.pov["display_name"] == "アレン"
    assert result.writer_context.pov["observable_state"] == "妹の声を聞き捜索中"
    # setting constraints must be flattened to list[str]
    assert "外壁封鎖" in result.writer_context.setting_constraints


def test_projection_to_writer_context_mapping():
    proj = build_scene_projection(
        ContextScope(
            pov_character=EntityRef(kind="character", id="char_001"),
            setting=EntityRef(kind="location", id="loc_stone_city"),
        ),
        _make_canon(),
    )
    wc = projection_to_writer_context(proj)
    assert isinstance(wc, WriterContext)
    assert wc.pov["display_name"] == "アレン"
