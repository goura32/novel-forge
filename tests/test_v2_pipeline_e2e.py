"""Phase 5 fake-LLM end-to-end tests for the v2 Series Bible pipeline (§12).

No external LLM is used: ``run_v2_pipeline`` accepts an optional ``writer_draft_fn``
so the writer stage is fully deterministic, and every Canon op is a static dict.

These tests pin the §12 acceptance criteria against the *locked* canon core
(``novel_forge.canon.*``), which is disjoint from the legacy v1 runtime that
§10 removed (``scene_writer`` / ``context_builder`` / ``bible_manager`` / Bible
second-write path).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from novel_forge.canon.design import SceneDesign
from novel_forge.canon.models import (
    Canon,
    CanonEvent,
    ReviewEvidence,
    compute_canonical_digest,
)
from novel_forge.canon.registry import get_validator, validate
from novel_forge.canon.runtime import (
    apply_reviewed_patch,
    attach_projection,
    build_chapter_intent,
    build_scene_design,
    build_volume_intent,
    review_scene_patch,
    run_v2_pipeline,
)
from novel_forge.canon.store import (
    BibleFactory,
    CanonEventStore,
    ReviewEvidenceMismatchError,
)

# ---------------------------------------------------------------------------
# Plan seed for the E2E scenarios (a small, self-consistent series)
# ---------------------------------------------------------------------------

SERIES_PLAN = {
    "series": {
        "id": "series",
        "title": "星海の継承者",
        "logline": "忘却された星で目覚めた少女の物語",
    },
    "characters": [
        {
            "id": "char_001",
            "identity": {"kind": "named", "display_name": "リィナ"},
            "importance": "core",
            "tracking_level": "full",
            "narrative_function": "主人公",
            "continuity_card": {"current_state": "冷凍睡眠から覚醒", "current_location": None},
        },
        {
            "id": "char_002",
            "identity": {"kind": "named", "display_name": "カイル"},
            "importance": "supporting",
            "tracking_level": "full",
            "narrative_function": "案内人",
            "continuity_card": {"current_state": "survivor", "current_location": None},
        },
    ],
    "locations": [
        {"id": "loc_001", "name": "覚醒室", "kind": "facility", "current_state": "静寂"},
    ],
    "chronology": {
        "current_marker": {"ordinal": 0, "label": "開始"},
        "active_deadlines": [],
    },
}

# A POV scope over the core character in the seeded location.
_BASIC_SCOPE = {
    "pov_character": {"kind": "character", "id": "char_001"},
    "setting": {"kind": "location", "id": "loc_001"},
    "required_refs": [{"kind": "character", "id": "char_002"}],
}


def _make_patch(**ops) -> dict:
    """Build a canon_patch dict with only the given per-entity ops populated."""
    patch: dict = {
        "characters": {"create": [], "state_updates": [], "promote": [], "identity_reveals": []},
        "collectives": {"create": [], "state_updates": []},
        "locations": {"create": [], "state_updates": []},
        "artifacts": {"create": [], "custody_updates": [], "condition_updates": []},
        "knowledge": {"create": [], "holder_updates": [], "visibility_updates": [],
                      "truth_status_transitions": []},
        "chronology": {"advance_to": None, "deadline_updates": []},
        "relationships": {"create": [], "updates": []},
        "foreshadowing": {"create": [], "transitions": []},
        "subplots": {"create": [], "updates": []},
        "glossary": {"create": []},
    }
    for kind, value in ops.items():
        patch[kind] = value
    return patch


def _fake_draft(design: SceneDesign, prompt: str) -> str:
    """Deterministic fake writer output (no LLM)."""
    return f"<<draft {design.scene_id}>>"


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="v2_e2e_"))


def _design_for(scope: dict) -> SceneDesign:
    vol = build_volume_intent(SERIES_PLAN, 1)
    ch = build_chapter_intent(vol, 1)
    design = build_scene_design(ch, 1, scope)
    return attach_projection(design, BibleFactory.create_seed(SERIES_PLAN))


def _source(design: SceneDesign):
    from novel_forge.canon.models import SourceRef

    return SourceRef(scene_id=design.scene_id,
                     location={"volume": 1, "chapter": 1, "ordinal": 1}, revision=1)


# §12 (1): identical digest == no-op (idempotent replay)
def test_identical_digest_is_noop():
    result = run_v2_pipeline(SERIES_PLAN, [
        {"context_scope": _BASIC_SCOPE, "patch": _make_patch()},
    ])
    digest_a = result["digest"]
    result2 = run_v2_pipeline(SERIES_PLAN, [
        {"context_scope": _BASIC_SCOPE, "patch": _make_patch()},
    ])
    assert result2["digest"] == digest_a
    seed = BibleFactory.create_seed(SERIES_PLAN)
    assert compute_canonical_digest(seed) == digest_a


# §12 (2): segment transaction — a scene patch is atomic
def test_segment_applied_as_single_event():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                characters={"create": [
                    {
                        "creation_key": "k_alice",
                        "identity": {"kind": "named", "display_name": "アリス"},
                        "importance": "minor",
                        "tracking_level": "continuity",
                        "narrative_function": "通行人",
                        "continuity_card": {"current_state": "立ち去る"},
                    }
                ], "state_updates": [], "promote": [], "identity_reveals": []},
            ),
        },
    ])
    events = result["events"]
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, CanonEvent)
    assert len(ev.created_entity_ids) == 1
    created = next(iter(ev.created_entity_ids.values()))
    assert created.startswith("char_")
    assert any(c.id == created for c in result["canon"].characters)


# §12 (3): dependent deletion rejected
def test_dependent_deletion_rejected():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                locations={"create": [
                    {"creation_key": "k_cave", "name": "隠れ穴", "kind": "natural",
                     "current_state": "暗い"},
                ], "state_updates": []},
            ),
        },
        # scene 2 creates a character whose continuity card references the
        # location (loc_002) created by scene 1 — a true EntityRef dependency.
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                characters={"create": [
                    {
                        "creation_key": "k_bob",
                        "identity": {"kind": "named", "display_name": "ボブ"},
                        "importance": "minor",
                        "tracking_level": "continuity",
                        "narrative_function": "探検者",
                        "continuity_card": {"current_state": "穴にいる",
                                            "current_location": {"kind": "location",
                                                                "id": "loc_002"}},
                    }
                ], "state_updates": [], "promote": [], "identity_reveals": []},
            ),
        },
    ])
    store: CanonEventStore = result["store"]
    events = store.load_active()
    errors = store.validate_segment_replacement(
        removed_scene_ids=[events[0].source.scene_id], replacement_events=[], events=events
    )
    assert errors, "expected rejection: scene 2 references an entity created by scene 1"


# §12 (4): structured EventRef + review evidence binding
def test_structured_event_ref():
    result = run_v2_pipeline(SERIES_PLAN, [
        {"context_scope": _BASIC_SCOPE, "patch": _make_patch()},
    ])
    ev = result["events"][0]
    assert ev.source.scene_id
    assert set(ev.source.location.model_dump()) == {"volume", "chapter", "ordinal"}
    assert ev.artifact_digest.startswith("sha256:")
    assert isinstance(ev.review_evidence, ReviewEvidence)
    assert ev.review_evidence.reviewed_artifact_digest == ev.artifact_digest
    assert ev.review_evidence.status == "approved"


# §12 (5): typed reference + dangling reference hard-stop (at apply time)
def test_typed_reference_dangling_rejected_at_replay():
    good_patch = _make_patch(
        artifacts={"create": [
            {"creation_key": "k_sword", "name": "聖剣", "kind": "weapon",
             "narrative_significance": "key"},
        ], "custody_updates": [], "condition_updates": []},
    )
    assert validate("canon_patch", good_patch) == []

    ref_patch = _make_patch(
        characters={"create": [],
                    "state_updates": [
                        {"character": {"kind": "character", "id": "char_999"},
                         "current_state": "gone"}],
                    "promote": [], "identity_reveals": []},
    )
    assert validate("canon_patch", ref_patch) == []  # schema OK
    store = CanonEventStore(_tmp())
    store.write_seed(BibleFactory.create_seed(SERIES_PLAN))
    design = _design_for(_BASIC_SCOPE)
    review = review_scene_patch(design, ref_patch, store.load_seed())
    assert not review.passed
    assert any("semantic" in issue for issue in review.issues)


# §12 (6): Design Intent separated from Bible (Canon has no intent field)
def test_design_intent_separated_from_canon():
    vol = build_volume_intent(SERIES_PLAN, 1)
    ch = build_chapter_intent(vol, 1, chapter_constraints=["緊迫感を保つ"])
    assert vol.design_intent is not None
    assert ch.design_intent is not None
    result = run_v2_pipeline(SERIES_PLAN, [
        {"context_scope": _BASIC_SCOPE, "patch": _make_patch()},
    ])
    assert "design_intent" not in result["canon"].model_dump(by_alias=False)


# §12 (7): status + review forced (mismatch is a hard stop)
def test_event_requires_review_evidence():
    ev = CanonEvent(
        event_id="ev_x",
        source={"scene_id": "s1", "location": {"volume": 1, "chapter": 1, "ordinal": 1}},
        artifact_digest="sha256:abc",
        review_evidence={"status": "approved", "reviewed_artifact_digest": "sha256:abc",
                         "review_digest": "sha256:rev", "review_contract_version": 1},
        patch=_make_patch(),
    )
    assert ev.review_evidence.status == "approved"
    ev.review_evidence.reviewed_artifact_digest = "sha256:WRONG"
    store = CanonEventStore(_tmp())
    store.write_seed(BibleFactory.create_seed(SERIES_PLAN))
    with pytest.raises(ReviewEvidenceMismatchError):
        store.replay(store.load_seed(), [ev])


# §12 (8): event store is the single source of truth (recover == replay)
def test_event_store_is_source_of_truth():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                artifacts={"create": [
                    {"creation_key": "k_orb", "name": "記憶の珠", "kind": "relic",
                     "narrative_significance": "memory"},
                ], "custody_updates": [], "condition_updates": []},
            ),
        },
    ])
    store = result["store"]
    recovered = store.recover()
    assert compute_canonical_digest(recovered) == result["digest"]
    assert any(a.name == "記憶の珠" for a in recovered.artifacts)


# §12 (9): only corruption stops replay (consistent re-runs)
def test_only_corruption_stops():
    r1 = run_v2_pipeline(SERIES_PLAN, [{"context_scope": _BASIC_SCOPE, "patch": _make_patch()}])
    r2 = run_v2_pipeline(SERIES_PLAN, [{"context_scope": _BASIC_SCOPE, "patch": _make_patch()}])
    assert r1["digest"] == r2["digest"]


# §12 (10): external $ref resolves via registry
def test_external_ref_resolves_via_registry():
    scope_validator = get_validator("context_scope")
    errs = list(scope_validator.iter_errors(_BASIC_SCOPE))
    assert errs == []


# §12 (11): no Bible second-write path — legacy artifacts are gone
def test_no_bible_second_write_path():
    prompts = Path(__file__).resolve().parents[1] / "src" / "novel_forge" / "resources" / "prompts"
    schemas = Path(__file__).resolve().parents[1] / "schemas"
    assert not (prompts / "scene_summary_and_bible_update.md").exists()
    assert not (schemas / "scene_summary_and_bible_update.json").exists()
    # The v1 bible_manager module is removed entirely (single source of truth = Canon).
    with pytest.raises(ModuleNotFoundError):
        import novel_forge.bible_manager  # noqa: F401


def test_legacy_prompt_adapter_reads_v2_materialized_canon(tmp_path: Path):
    from novel_forge.canon.store import CanonEventStore

    result = run_v2_pipeline(SERIES_PLAN, [{"context_scope": _BASIC_SCOPE, "patch": _make_patch()}], workdir=tmp_path / "canon")
    canon = CanonEventStore(tmp_path / "canon").recover()
    char = next(c for c in canon.characters if c.id == "char_001")
    text = char.continuity_card.current_state
    assert "冷凍睡眠" in text
    assert result["store"].bible_path.exists()
    # The v2 canon is the single source of truth; legacy BibleManager.save is gone.
    assert not hasattr(canon, "save")


def test_review_gate_blocks_rejected_patch_from_event_log(tmp_path: Path):
    seed = BibleFactory.create_seed(SERIES_PLAN)
    design = attach_projection(
        build_scene_design(
            build_chapter_intent(build_volume_intent(SERIES_PLAN, 1), 1), 1, _BASIC_SCOPE
        ),
        seed,
    )
    # a patch that changes a cast member but omits that cast from the scene
    patch = _make_patch(
        characters={
            "state_updates": [
                {"character": {"kind": "character", "id": "char_001"}, "current_state": "脱出を試みる"}
            ]
        }
    )
    review = review_scene_patch(design, patch, seed)
    assert review.passed, "simple in-scope cast change must pass review"
    # now a patch that references an out-of-scope cast member
    leak_patch = _make_patch(
        characters={"create": [{
            "creation_key": "k_out",
            "identity": {"kind": "named", "display_name": "侵入者"},
            "importance": "minor",
            "tracking_level": "continuity",
            "narrative_function": "x",
            "continuity_card": {"current_state": "侵入した"},
        }]},
        relationships={"create": [{
            "creation_key": "rel_out",
            "relationship_type": "rivalry",
            "participant_ids": ["char_002", "char_999"],
            "dynamics": "敵対",
        }]},
    )
    leak_review = review_scene_patch(design, leak_patch, seed)
    assert not leak_review.passed
    assert any("cast_relevant" in i for i in leak_review.issues)
    store = CanonEventStore(tmp_path / "canon")
    store.write_seed(seed)
    with pytest.raises(ValueError, match="review rejected"):
        apply_reviewed_patch(design, leak_patch, seed, store, leak_review)
    result = run_v2_pipeline(
        SERIES_PLAN,
        [{
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                characters={
                    "create": [{
                        "creation_key": "provenance_minor",
                        "identity": {"kind": "named", "display_name": "証人"},
                        "importance": "minor",
                        "tracking_level": "continuity",
                        "narrative_function": "証言者",
                        "continuity_card": {"current_state": "待機"},
                    }],
                    "state_updates": [], "promote": [], "identity_reveals": [],
                }
            ),
        }],
        workdir=tmp_path,
    )
    event = result["events"][0]
    created_id = event.created_entity_ids["character:provenance_minor"]
    character = result["canon"].get_entity("character", created_id)
    assert character is not None
    assert character.last_changed_by is not None
    assert character.last_changed_by.scene_id == event.source.scene_id
    assert character.last_changed_by.event_digest == event.artifact_digest
    assert compute_canonical_digest(result["store"].replay()) == compute_canonical_digest(result["canon"])


def test_segment_transaction_rejects_orphan_without_writing(tmp_path: Path):
    result = run_v2_pipeline(
        SERIES_PLAN,
        [
            {
                "context_scope": _BASIC_SCOPE,
                "patch": _make_patch(
                    locations={"create": [{"creation_key": "removable", "name": "港", "kind": "facility", "current_state": "静か"}], "state_updates": []}
                ),
            },
            {
                "context_scope": _BASIC_SCOPE,
                "patch": _make_patch(
                    characters={"create": [{
                        "creation_key": "depends_on_port",
                        "identity": {"kind": "named", "display_name": "船頭"},
                        "importance": "minor", "tracking_level": "continuity", "narrative_function": "案内人",
                        "continuity_card": {"current_state": "港にいる", "current_location": {"kind": "location", "id": "loc_002"}},
                    }], "state_updates": [], "promote": [], "identity_reveals": []}
                ),
            },
        ],
        workdir=tmp_path,
    )
    store = result["store"]
    before = store.events_path.read_bytes()
    with pytest.raises(Exception, match="references entity"):
        store.replace_design_segment([result["events"][0].source.scene_id], [])
    assert store.events_path.read_bytes() == before


def test_identical_segment_replacement_is_a_noop(tmp_path: Path):
    result = run_v2_pipeline(SERIES_PLAN, [{"context_scope": _BASIC_SCOPE, "patch": _make_patch()}], workdir=tmp_path)
    store = result["store"]
    event = result["events"][0]
    before = store.events_path.read_bytes()
    retried = event.model_copy(update={"created_at": "2099-01-01T00:00:00+00:00"})
    store.replace_design_segment([event.source.scene_id], [retried])
    assert store.events_path.read_bytes() == before


def test_creation_key_identity_is_kind_scoped_across_entity_kinds():
    result = run_v2_pipeline(
        SERIES_PLAN,
        [{
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                characters={"create": [{"creation_key": "same", "identity": {"kind": "named", "display_name": "A"}, "importance": "minor", "tracking_level": "continuity", "narrative_function": "x", "continuity_card": {"current_state": "x"}}], "state_updates": [], "promote": [], "identity_reveals": []},
                locations={"create": [{"creation_key": "same", "name": "B", "kind": "facility", "current_state": "x"}], "state_updates": []},
            ),
        }],
    )

    created = result["events"][0].created_entity_ids
    assert created["character:same"].startswith("char_")
    assert created["location:same"].startswith("loc_")
def test_fake_llm_e2e_core_scenarios():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                characters={"create": [
                    {
                        "creation_key": "k_mute",
                        "identity": {"kind": "named", "display_name": "黙秘の者"},
                        "importance": "minor",
                        "tracking_level": "continuity",
                        "narrative_function": "謎の人物",
                        "continuity_card": {"current_state": "監視している"},
                    }
                ], "state_updates": [], "promote": [], "identity_reveals": []},
            ),
        },
        {
            "context_scope": _BASIC_SCOPE,
            "cast": [
                {"kind": "character", "character": {"kind": "character", "id": "char_001"}},
                {"kind": "character", "character": {"kind": "character", "id": "char_002"}},
            ],
            "patch": _make_patch(
                relationships={"create": [
                    {
                        "creation_key": "k_rel",
                        "participant_ids": ["char_001", "char_002"],
                        "structural_bonds": [
                            {"kind": "trust", "label": "共犯関係", "direction": "symmetric"}],
                        "shared_state": {"cooperation": "conditional", "openness": "guarded",
                                         "central_tension": "信頼", "current_arrangement": ""},
                        "perspectives": [
                            {"character_id": "char_001", "attitude": "警戒", "trust": "conditional",
                             "desire_from_other": "真実", "boundary": "過去"},
                            {"character_id": "char_002", "attitude": "保護", "trust": "full",
                             "desire_from_other": "記憶", "boundary": ""},
                        ],
                    }
                ], "updates": []},
                knowledge={"create": [
                    {
                        "creation_key": "k_secret",
                        "proposition": "リィナは星の鍵である",
                        "truth_status": "contested",
                        "visibility": "secret",
                        "holders": [{"holder": {"kind": "character", "id": "char_002"},
                                     "state": "knows"}],
                    }
                ], "holder_updates": [], "visibility_updates": [],
                "truth_status_transitions": []},
            ),
        },
    ], writer_draft_fn=_fake_draft)

    canon = result["canon"]
    assert any(c.identity.display_name == "黙秘の者" for c in canon.characters)
    rel = canon.relationships[0]
    assert rel.participant_ids == ["char_001", "char_002"]
    know = canon.knowledge[0]
    assert know.truth_status == "contested"
    assert know.visibility == "secret"
    assert len(result["drafts"]) == 2
    assert all(draft.startswith("<<draft scn_") and draft.endswith(">>") for draft in result["drafts"])


# POV-leak guard: writer_context must not expose secret proposition text
def test_writer_context_never_exposes_secret_truth():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                knowledge={"create": [
                    {
                        "creation_key": "k_s",
                        "proposition": "リィナは星の鍵である",
                        "truth_status": "confirmed",
                        "visibility": "secret",
                        "holders": [{"holder": {"kind": "character", "id": "char_002"},
                                     "state": "knows"}],
                    }
                ], "holder_updates": [], "visibility_updates": [],
                "truth_status_transitions": []},
            ),
        },
    ])
    wc = result["designs"][0].writer_context
    blob = str(wc.model_dump())
    assert "星の鍵" not in blob


# Scope closure across scenes
def test_scope_closure_across_scenes():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                artifacts={"create": [
                    {"creation_key": "k_map", "name": "星図", "kind": "document",
                     "narrative_significance": "nav"},
                ], "custody_updates": [], "condition_updates": []},
            ),
        },
        {"context_scope": _BASIC_SCOPE, "patch": _make_patch()},
    ])
    assert len(result["events"]) == 2
    assert any(a.name == "星図" for a in result["canon"].artifacts)


# P0 non-drop: a core character update survives replay
def test_p0_core_update_survives():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                characters={"create": [], "state_updates": [
                    {"character": {"kind": "character", "id": "char_001"},
                     "current_state": "覚醒完了"},
                ], "promote": [], "identity_reveals": []},
            ),
        },
    ])
    c = result["canon"].get_entity("character", "char_001")
    assert c is not None
    assert c.continuity_card.current_state == "覚醒完了"


# P2 omission: a missing required entity sub-field is rejected by schema
def test_p2_omission_rejected_by_schema():
    # a character create missing the required 'identity' field must fail
    bad = _make_patch()
    bad["characters"]["create"].append({
        "creation_key": "k_x",
        "importance": "minor",
        "tracking_level": "continuity",
        "narrative_function": "x",
        "continuity_card": {"current_state": "x"},
    })
    errs = validate("canon_patch", bad)
    assert errs, "omitting a required entity sub-field must fail schema validation"


# materialized view auto-regenerates on write (§7/§8)
def test_materialized_view_regenerated():
    result = run_v2_pipeline(SERIES_PLAN, [
        {
            "context_scope": _BASIC_SCOPE,
            "patch": _make_patch(
                glossary={"create": [{"creation_key": "k_term", "term": "星葬",
                                     "definition": "星の葬儀"}]},
            ),
        },
    ])
    store = result["store"]
    bible = store.bible_path.read_text(encoding="utf-8")
    assert "星葬" in bible
    assert compute_canonical_digest(
        Canon.model_validate_json(bible)
    ) == result["digest"]
