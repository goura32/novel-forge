"""Tests for CanonSliceBuilder (§3.2, §5.1, §6.2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from novel_forge.canon.models import (
    Canon,
    ContextScope,
    EntityRef,
)
from novel_forge.canon.slice import CanonSliceBuilder


def _make_canon() -> Canon:
    return Canon.model_validate(
        {
            "schema_version": 2,
            "series": {
                "id": "series",
                "title": "怪の街 記憶の礎",
                "constraints": [{"id": "constraint_001", "statement": "死者は蘇生できない", "scope": "series"}],
            },
            "world_rules": [{"id": "rule_001", "name": "石媒律", "statement": "魔法は石を媒体とする"}],
            "characters": [
                {
                    "id": "char_001",
                    "identity": {"kind": "named", "display_name": "アリーン", "aliases": []},
                    "importance": "core",
                    "tracking_level": "full",
                    "narrative_function": "主人公",
                    "profile": {"motivation": "妹を探す"},
                    "continuity_card": {
                        "current_state": "石の都へ到着",
                        "current_location": {"kind": "location", "id": "loc_stone_city"},
                        "distinguishing_traits": "石粉の指",
                    },
                    "affiliations": [{"collective": {"kind": "collective", "id": "grp_north_gate"}, "role": "客人", "status": "active"}],
                },
                {
                    "id": "char_014",
                    "identity": {"kind": "role_anchored", "display_name": "北門の薬師", "aliases": []},
                    "importance": "minor",
                    "tracking_level": "continuity",
                    "narrative_function": "薬師",
                    "profile": None,
                    "continuity_card": {
                        "current_state": "通行証を疑っている",
                        "current_location": {"kind": "location", "id": "loc_stone_city"},
                        "distinguishing_traits": "左手の青い染料",
                    },
                    "affiliations": [{"collective": {"kind": "collective", "id": "grp_north_gate"}, "role": "薬師", "status": "active"}],
                },
            ],
            "collectives": [
                {
                    "id": "grp_north_gate",
                    "kind": "organization",
                    "name": "北門衛兵隊",
                    "function": "検問",
                    "current_state": "警戒中",
                    "stance_toward_characters": [
                        {"character": {"kind": "character", "id": "char_001"}, "stance": "suspicious", "reason": "不審な印"}
                    ],
                }
            ],
            "locations": [
                {
                    "id": "loc_stone_city",
                    "name": "石の都",
                    "kind": "city",
                    "parent_location": None,
                    "immutable_constraints": ["夜間は城門が封鎖される"],
                    "current_state": "北門検査強化",
                },
                {
                    "id": "loc_country",
                    "name": "王国",
                    "kind": "region",
                    "parent_location": None,
                    "immutable_constraints": [],
                    "current_state": "",
                },
            ],
            "artifacts": [
                {
                    "id": "art_memory_stone",
                    "name": "記憶石",
                    "kind": "magical_item",
                    "properties": ["一度だけ再生できる"],
                    "custody": {"kind": "character", "id": "char_001"},
                    "condition": "ひびが一本",
                    "narrative_significance": "妹の手がかり",
                }
            ],
            "knowledge": [
                {
                    "id": "know_secret",
                    "proposition": "妹の記憶は石に封じられている",
                    "truth_status": "confirmed",
                    "visibility": "secret",
                    "holders": [{"holder": {"kind": "character", "id": "char_001"}, "state": "knows"}],
                    "related_entity_refs": [{"kind": "artifact", "id": "art_memory_stone"}],
                },
                {
                    "id": "know_public",
                    "proposition": "石都は夜間封鎖される",
                    "truth_status": "confirmed",
                    "visibility": "public",
                    "holders": [{"holder": {"kind": "character", "id": "char_014"}, "state": "knows"}],
                },
            ],
            "relationships": [
                {
                    "id": "rel_001",
                    "participant_ids": ["char_001", "char_002"],
                    "structural_bonds": [{"kind": "kinship", "label": "姉妹"}],
                    "shared_state": {"cooperation": "conditional"},
                    "perspectives": [
                        {"character_id": "char_001", "attitude": "protective"},
                        {"character_id": "char_002", "attitude": "wary"},
                    ],
                    "arc_summary": "再会後の敵対から共同調査へ",
                    "lifecycle": "active",
                }
            ],
            "foreshadowing": [
                {
                    "id": "fh_001",
                    "description": "石の中から妹の声",
                    "status": "planted",
                    "related_character_ids": ["char_001"],
                    "related_subplot_ids": ["sp_001"],
                    "intended_payoff": "記憶の判明",
                }
            ],
            "subplots": [
                {
                    "id": "sp_001",
                    "name": "石都の陰謀",
                    "status": "active",
                    "dramatic_question": "長老はなぜ集める",
                    "stakes": "記憶が失われる",
                    "current_state": "関与判明",
                }
            ],
            "glossary": [{"id": "term_001", "term": "彫刻師", "definition": "記憶を石に刻む職能"}],
            "chronology": {
                "current_marker": {"ordinal": 3, "label": "第3日"},
                "active_deadlines": [
                    {"id": "deadline_gate", "statement": "夜明けまでに北門を越える", "due_marker": {"ordinal": 4, "label": "第4日"}, "status": "active"}
                ],
            },
        }
    )


def _scope() -> ContextScope:
    return ContextScope(
        pov_character=EntityRef(kind="character", id="char_001"),
        setting=EntityRef(kind="location", id="loc_stone_city"),
        required_refs=[
            EntityRef(kind="relationship", id="rel_001"),
            EntityRef(kind="artifact", id="art_memory_stone"),
            EntityRef(kind="knowledge", id="know_secret"),
            EntityRef(kind="deadline", id="deadline_gate"),
        ],
    )


def _included_ids(proj) -> set:
    return {(r["kind"], r["id"]) for r in proj.scope_manifest["included"]}


def test_scope_closure_includes_affiliated_collective():
    canon = _make_canon()
    scope = _scope()
    proj = CanonSliceBuilder().build("scene_design", scope, canon)
    inc = _included_ids(proj)
    # closure: POV char -> affiliation -> collective
    assert ("collective", "grp_north_gate") in inc


def test_scope_closure_includes_relation_participants():
    canon = _make_canon()
    scope = _scope()
    proj = CanonSliceBuilder().build("scene_design", scope, canon)
    inc = _included_ids(proj)
    assert ("relationship", "rel_001") in inc
    # rel_001 participants pulled in by closure
    assert ("character", "char_001") in inc


def test_p0_invariants_never_dropped():
    canon = _make_canon()
    scope = _scope()
    proj = CanonSliceBuilder().build("scene_design", scope, canon, budget=10)
    inc = _included_ids(proj)
    # P0: series constraint, world rule, pov identity+state, setting constraint,
    # deadline, pov knowledge
    assert ("series_constraint", "constraint_001") in inc
    assert ("world_rule", "rule_001") in inc
    assert ("character", "char_001") in inc
    assert ("location", "loc_stone_city") in inc
    assert ("deadline", "deadline_gate") in inc
    assert ("knowledge", "know_secret") in inc


def test_p2_optional_deterministic_omission():
    canon = _make_canon()
    scope = _scope()
    # force over-budget so P2 (parent location, glossary, minor) get dropped
    proj = CanonSliceBuilder().build("scene_design", scope, canon, budget=5)
    manifest = proj.scope_manifest
    assert manifest["omitted_optional_count"] >= 1
    inc = _included_ids(proj)
    # P0/P1 kept despite tiny budget
    assert ("character", "char_001") in inc


def test_digest_consistency_same_selection():
    canon = _make_canon()
    scope = _scope()
    b = CanonSliceBuilder()
    p1 = b.build("scene_design", scope, canon)
    p2 = b.build("scene_design", scope, canon)
    assert p1.canon_digest == p2.canon_digest
    assert p1.canon_digest.startswith("sha256:")


def test_author_context_has_knowledge_proposition():
    canon = _make_canon()
    scope = _scope()
    proj = CanonSliceBuilder().build("scene_design", scope, canon)
    ac = proj.author_context
    props = [k["proposition"] for k in ac.get("knowledge", [])]
    assert "妹の記憶は石に封じられている" in props
    assert "魔法は石を媒体とする" in ac["world_rules"]
    assert ac["locations"] == [{
        "name": "石の都",
        "immutable_constraints": ["夜間は城門が封鎖される"],
        "current_state": "北門検査強化",
    }]


def test_pov_safe_context_hides_secret_truth_and_ids():
    canon = _make_canon()
    scope = _scope()
    proj = CanonSliceBuilder().build("scene_design", scope, canon)
    psc = proj.pov_safe_context
    blob = str(psc)
    # no stable IDs
    assert "char_001" not in blob
    assert "know_secret" not in blob
    # guardrail present, secret proposition not leaked
    assert any("断定しない" in g for g in psc.get("unrevealed_guardrails", []))
    assert "妹の記憶は石に封じられている" not in blob
    # custody labels must come from the active Canon, never a fixed example ID.
    assert any("アリーン" in state for state in psc.get("artifact_state", []))
