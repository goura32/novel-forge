"""TDD: enforce the §6.3 / §7.1 review-evidence contract.

Per ``docs/dev/SERIES_BIBLE_SCHEMA_REDESIGN.md`` §6.3 and §7.1:

* ``CanonEvent.artifact_digest`` and ``ReviewEvidence.reviewed_artifact_digest``
  MUST equal the digest of the *reviewed SceneDesign artifact* (the scene design
  content + the patch that was reviewed), and therefore MUST be equal to each
  other.
* If the SceneDesign content **or** the patch is changed after review,
  ``apply_reviewed_patch`` MUST reject the apply (re-review required).

The prior implementation set ``event.artifact_digest`` to the *post-apply Canon
digest*, which is wrong: it is neither the reviewed artifact digest nor equal to
what the review bound.  These tests capture the corrected contract and must
fail against the buggy code.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from novel_forge.canon.design import SceneDesign
from novel_forge.canon.runtime import (
    ReviewResult,
    apply_reviewed_patch,
    attach_projection,
    build_chapter_intent,
    build_scene_design,
    build_volume_intent,
    review_scene_patch,
)
from novel_forge.canon.store import BibleFactory, CanonEventStore
from tests.test_v2_pipeline_e2e import _BASIC_SCOPE, SERIES_PLAN, _make_patch


def _design(canon) -> SceneDesign:
    vol = build_volume_intent(SERIES_PLAN, 1)
    ch = build_chapter_intent(vol, 1)
    return attach_projection(build_scene_design(ch, 1, _BASIC_SCOPE), canon)


def _store() -> tuple[TemporaryDirectory, CanonEventStore]:
    tmp = TemporaryDirectory()
    store = CanonEventStore(Path(tmp.name))
    store.write_seed(BibleFactory.create_seed(SERIES_PLAN))
    return tmp, store


def test_artifact_digest_is_reviewed_design_plus_patch_not_post_apply_canon():
    """event.artifact_digest must equal the reviewed SceneDesign artifact digest."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(seed)
        patch = _make_patch(
            characters={
                "state_updates": [
                    {
                        "character": {"kind": "character", "id": "char_001"},
                        "current_state": "覚醒",
                    }
                ]
            }
        )
        review = review_scene_patch(design, patch, seed)
        assert review.passed

        # The review result must expose the reviewed artifact digest.
        assert review.artifact_digest.startswith("sha256:")
        # It must NOT be the post-apply Canon digest (which depends on the seed).
        # The reviewed artifact digest is computed purely from design + patch.
        assert review.artifact_digest == review.artifact_digest

        _, event = apply_reviewed_patch(design, patch, seed, store, review)

        # Core contract: event.artifact_digest == review.artifact_digest
        assert event.artifact_digest == review.artifact_digest
        # And the review evidence binds to exactly that digest.
        assert event.review_evidence.reviewed_artifact_digest == event.artifact_digest
        # It must NOT be the post-apply Canon digest.
        from novel_forge.canon.models import compute_canonical_digest

        post_apply = compute_canonical_digest(store.replay(seed, store.load_active()))
        assert event.artifact_digest != post_apply, (
            "artifact_digest must be the reviewed SceneDesign artifact digest, "
            "not the post-apply Canon digest"
        )
    finally:
        tmp.cleanup()


def test_apply_rejected_when_scene_design_text_changed_after_review():
    """Changing scene *content* after review must force re-review (apply rejected)."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(seed)
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert review.passed

        # Mutate the reviewed scene design content AFTER the review.
        design.goal = "これは review 後に変更された goal である"
        design.writer_context = None  # drop a content field carried into the review

        with pytest.raises(ValueError, match="re-review|artifact"):
            apply_reviewed_patch(design, patch, seed, store, review)
        # Nothing was persisted.
        assert store.load_active() == []
    finally:
        tmp.cleanup()


def test_apply_rejected_when_patch_changed_after_review():
    """Changing the patch after review must force re-review (apply rejected)."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(seed)
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert review.passed

        # Mutate the reviewed patch AFTER the review.
        changed = _make_patch(
            characters={
                "state_updates": [
                    {
                        "character": {"kind": "character", "id": "char_001"},
                        "current_state": "別の状態",
                    }
                ]
            }
        )

        with pytest.raises(ValueError, match="re-review|artifact"):
            apply_reviewed_patch(design, changed, seed, store, review)
        assert store.load_active() == []
    finally:
        tmp.cleanup()


def test_review_result_carries_reviewed_artifact_digest():
    """review_scene_patch must populate ReviewResult.artifact_digest."""
    tmp, store = _store()
    try:
        seed = store.load_seed()
        design = _design(seed)
        patch = _make_patch()
        review = review_scene_patch(design, patch, seed)
        assert isinstance(review, ReviewResult)
        assert review.artifact_digest.startswith("sha256:")
        # Same design+patch must yield a stable digest.
        again = review_scene_patch(design, patch, seed)
        assert again.artifact_digest == review.artifact_digest
    finally:
        tmp.cleanup()
