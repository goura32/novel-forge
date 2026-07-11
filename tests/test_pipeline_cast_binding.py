"""TDD: bind scene cast to SceneDesign.cast, not the pipeline's flat dict.

Per ``docs/dev/SERIES_BIBLE_SCHEMA_REDESIGN.md`` §7.2 the scene cast is the
authoritative set used for cast-relevant review and event provenance.  The
canonical cast entry shape is ``CastCharacter`` / ``CastLocalRole`` nested
under ``SceneDesign.cast`` (``character: {kind, id}``), not a flat
``{"kind": "character", "id": ...}`` dict read off the spec.

The pipeline used to compute ``scene_cast_ids`` from ``spec["cast"]`` with a
flat ``r.get("id")`` access.  That (a) duplicates the cast already attached to
the design and (b) silently produces an empty set when the pipeline passes the
nested ``CastCharacter`` shape, defeating cast-relevant review and the event's
``scene_cast_ids`` provenance.

These tests assert the pipeline derives ``scene_cast_ids`` from the canonical
``SceneDesign.cast`` only, and that a flat-dict spec cast is coerced (or
rejected) rather than silently dropped.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from novel_forge.canon.design import CastEntry, SceneDesign
from novel_forge.canon.models import CastCharacter, EntityRef
from novel_forge.canon.runtime import (
    apply_reviewed_patch,
    attach_projection,
    build_chapter_intent,
    build_scene_design,
    build_volume_intent,
    review_scene_patch,
)
from novel_forge.canon.store import BibleFactory, CanonEventStore
from tests.test_v2_pipeline_e2e import _BASIC_SCOPE, SERIES_PLAN, _make_patch


def _store() -> tuple[TemporaryDirectory, CanonEventStore]:
    tmp = TemporaryDirectory()
    store = CanonEventStore(Path(tmp.name))
    store.write_seed(BibleFactory.create_seed(SERIES_PLAN))
    return tmp, store


def _design(canon, cast: list[CastEntry] | None = None) -> SceneDesign:
    vol = build_volume_intent(SERIES_PLAN, 1)
    ch = build_chapter_intent(vol, 1)
    return attach_projection(
        build_scene_design(ch, 1, _BASIC_SCOPE, cast=cast or []), canon
    )


def test_pipeline_derives_scene_cast_ids_from_scene_design_cast():
    """scene_cast_ids must come from SceneDesign.cast (nested CastCharacter)."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        # canonical nested cast entry, as the spec SHOULD express it
        cast: list[CastEntry] = [
            CastCharacter(character=EntityRef(kind="character", id="char_001")),
            CastCharacter(character=EntityRef(kind="character", id="char_002")),
        ]
        design = _design(seed, cast=cast)
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert review.passed, review.issues

        # The cast passed to build_scene_design is the single source of truth.
        # apply_reviewed_patch must record exactly those two IDs as provenance,
        # derived from the design's cast — not from any flat spec dict.
        design.accept_reviewed_patch(patch)
        _canon, event = apply_reviewed_patch(
            design, patch, seed, store, review, revision=1,
            scene_cast_ids={c.character.id for c in design.cast if isinstance(c, CastCharacter)},
        )
        assert set(event.scene_cast_ids) == {"char_001", "char_002"}
    finally:
        tmp.cleanup()


def test_flat_cast_dict_is_not_silently_dropped_by_pipeline():
    """A flat spec cast must be coerced to CastCharacter, not read as r['id']=None."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        # The flat shape a caller might pass: {"kind": "character", "id": "char_001"}
        flat_cast = [{"kind": "character", "id": "char_001"}]
        # build_scene_design now coerces flat dicts into CastCharacter entries.
        design = _design(seed, cast=flat_cast)  # type: ignore[list-item]
        assert any(
            isinstance(c, CastCharacter) and c.character.id == "char_001"
            for c in design.cast
        ), "flat cast dict must be coerced into a CastCharacter, not dropped"
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert review.passed, review.issues
        design.accept_reviewed_patch(patch)
        _canon, event = apply_reviewed_patch(
            design, patch, seed, store, review, revision=1,
            scene_cast_ids={c.character.id for c in design.cast if isinstance(c, CastCharacter)},
        )
        assert "char_001" in event.scene_cast_ids
    finally:
        tmp.cleanup()


def test_apply_rejects_scene_cast_ids_that_diverge_from_scene_design():
    """Callers cannot widen patch authorization beyond SceneDesign.cast."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(
            seed,
            cast=[CastCharacter(character=EntityRef(kind="character", id="char_001"))],
        )
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert review.passed, review.issues
        with pytest.raises(ValueError, match="scene_cast_ids diverge"):
            apply_reviewed_patch(
                design,
                patch,
                seed,
                store,
                review,
                scene_cast_ids={"char_001", "char_002"},
            )
    finally:
        tmp.cleanup()


def test_character_cast_rejects_conflicting_flat_and_nested_ids():
    """A cast payload must not smuggle a second ID outside SceneDesign.cast."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        conflicting_cast = [
            {
                "kind": "character",
                "id": "char_out_of_scope",
                "character": {"kind": "character", "id": "char_001"},
            }
        ]
        with pytest.raises(ValueError, match="conflicting character IDs"):
            _design(seed, cast=conflicting_cast)  # type: ignore[list-item]
    finally:
        tmp.cleanup()


def test_relationship_update_requires_cast_in_scope_design_not_flat_spec():
    """Cast-relevant review reads SceneDesign.cast, not the flat spec dict."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        # relationship arc referencing a cast member that is NOT in the
        # SceneDesign.cast (only present in a hypothetical flat spec).
        design = _design(seed, cast=[])  # empty canonical cast
        patch = _make_patch(
            relationships={
                "create": [
                    {
                        "creation_key": "k_rel",
                        "participant_ids": ["char_001", "char_002"],
                        "structural_bonds": [
                            {"kind": "trust", "label": "共犯", "direction": "symmetric"}
                        ],
                        "shared_state": {
                            "cooperation": "conditional",
                            "openness": "guarded",
                            "central_tension": "信頼",
                            "current_arrangement": "",
                        },
                        "perspectives": [
                            {
                                "character_id": "char_001",
                                "attitude": "警戒",
                                "trust": "conditional",
                                "desire_from_other": "真実",
                                "boundary": "過去",
                            },
                            {
                                "character_id": "char_002",
                                "attitude": "保護",
                                "trust": "full",
                                "desire_from_other": "記憶",
                                "boundary": "",
                            },
                        ],
                    }
                ],
                "updates": [],
            }
        )
        review = review_scene_patch(design, patch, seed)
        # With an empty SceneDesign.cast, the relationship involves out-of-scope
        # cast and must be flagged — proving review uses the design's cast.
        assert not review.passed
        assert any("cast_relevant" in i for i in review.issues)
    finally:
        tmp.cleanup()
