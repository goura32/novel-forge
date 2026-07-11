"""TDD: stable scene ID transaction persists SceneDesign with its Canon Event.

Per ``docs/dev/SERIES_BIBLE_SCHEMA_REDESIGN.md`` §4.2 the opaque ``scene_id`` is
immutable across revisions and scene edits, and §7.2 requires a *transaction*
that writes the Canon Event and the design artifact together (so a later scene
edit / deletion can rely on the existing design when replaying or replacing).

The store must therefore persist ``SceneDesign`` artifacts keyed by the stable
``scene_id``, atomically with the event, and expose a loader that returns the
latest design per scene_id — mirroring ``load_active`` for events.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from novel_forge.canon.design import CastCharacter, SceneDesign
from novel_forge.canon.models import CastCharacter as ModelCastCharacter
from novel_forge.canon.models import EntityRef
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


def _design(store: CanonEventStore, canon, cast=None) -> SceneDesign:
    vol = build_volume_intent(SERIES_PLAN, 1)
    ch = build_chapter_intent(vol, 1)
    design = build_scene_design(ch, 1, _BASIC_SCOPE, cast=cast or [])
    design = attach_projection(design, canon)
    store.save_design(design)
    return design


def test_store_persists_design_keyed_by_stable_scene_id():
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(store, seed)
        loaded = store.load_active_designs()
        assert design.scene_id in {d.scene_id for d in loaded}
        by_id = {d.scene_id: d for d in loaded}
        assert by_id[design.scene_id].scene_id == design.scene_id
    finally:
        tmp.cleanup()


def test_design_edit_keeps_stable_scene_id_across_revisions():
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(store, seed)
        original_id = design.scene_id

        # A scene edit updates the same stable id (it is NOT a new scene).
        design.title = "改訂後の表題"
        store.save_design(design)
        loaded = store.load_active_designs()
        assert len(loaded) == 1
        assert loaded[0].scene_id == original_id
        assert loaded[0].title == "改訂後の表題"
    finally:
        tmp.cleanup()


def test_design_and_event_share_transaction_source_id():
    """The persisted design's scene_id matches the persisted event's source id."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        cast = [CastCharacter(character=EntityRef(kind="character", id="char_001"))]
        design = _design(store, seed, cast=cast)
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert review.passed, review.issues
        design.accept_reviewed_patch(patch)
        _canon, event = apply_reviewed_patch(
            design,
            patch,
            seed,
            store,
            review,
            revision=1,
            scene_cast_ids={c.character.id for c in design.cast if isinstance(c, ModelCastCharacter)},
        )
        designs = store.load_active_designs()
        events = store.load_active()
        assert event.source.scene_id == design.scene_id
        assert design.scene_id in {d.scene_id for d in designs}
        assert design.scene_id in {e.source.scene_id for e in events}
    finally:
        tmp.cleanup()
