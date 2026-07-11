"""§5–§6 design artifact + projection connection tests (Phase 3 core)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from novel_forge.canon.design import (
    ChapterDesign,
    RelationshipContext,
    SceneDesign,
    VolumeDesign,
)
from novel_forge.canon.models import (
    Affiliation,
    CastCharacter,
    CastLocalRole,
    ContextScope,
    ContinuityCard,
    DesignIntent,
    EntityRef,
    Stance,
    WriterContext,
)
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
            foreshadowing=[
                {
                    "intent_key": "sister_voice",
                    "action": "plant",
                    "target_scene_id": "scn_001",
                }
            ],
            cast=[
                {
                    "target_scene_id": "scn_001",
                    "entries": [
                        {
                            "kind": "local_role",
                            "label": "港の検問兵",
                            "count": "one",
                            "scene_function": "疑念を示す",
                        }
                    ],
                }
            ],
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


def test_design_intent_requires_typed_keys_actions_and_targets() -> None:
    intent = DesignIntent(
        relationship_arcs=[
            {
                "relationship": {"kind": "relationship", "id": "rel_001"},
                "action": "shift",
                "target_scene_id": "scn_001",
                "expected_effect": "敵対を共同調査へ変える",
            }
        ]
    )
    assert intent.relationship_arcs[0].relationship.id == "rel_001"

    with pytest.raises(ValidationError, match="relationship"):
        DesignIntent(
            relationship_arcs=[
                {
                    "relationship": {"kind": "character", "id": "char_001"},
                    "action": "shift",
                    "target_scene_id": "scn_001",
                }
            ]
        )
    with pytest.raises(ValidationError, match="action"):
        DesignIntent(
            relationship_arcs=[
                {
                    "relationship": {"kind": "relationship", "id": "rel_001"},
                    "action": "guess",
                    "target_scene_id": "scn_001",
                }
            ]
        )


def test_context_scope_and_character_cast_enforce_reference_kind() -> None:
    with pytest.raises(ValidationError, match="pov_character"):
        ContextScope(pov_character=EntityRef(kind="location", id="loc_001"))
    with pytest.raises(ValidationError, match="setting"):
        ContextScope(setting=EntityRef(kind="character", id="char_001"))
    with pytest.raises(ValidationError, match="character"):
        CastCharacter(character=EntityRef(kind="location", id="loc_001"))


def test_canon_homogeneous_references_enforce_expected_kinds() -> None:
    with pytest.raises(ValidationError, match="current_location"):
        ContinuityCard(
            current_state="waiting",
            current_location=EntityRef(kind="character", id="char_002"),
        )
    with pytest.raises(ValidationError, match="collective"):
        Affiliation(
            collective=EntityRef(kind="character", id="char_002"),
            role="member",
        )
    with pytest.raises(ValidationError, match="character"):
        Stance(
            character=EntityRef(kind="location", id="loc_001"),
            stance="neutral",
        )


def test_draft_scene_design_rejects_canon_patch() -> None:
    with pytest.raises(ValidationError, match="review-passed"):
        SceneDesign(scene_id="scn_001", canon_patch={"characters": {}})


def test_review_passed_scene_design_requires_canon_patch() -> None:
    with pytest.raises(ValidationError, match="canon_patch"):
        SceneDesign(scene_id="scn_001", status="review_passed")


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
