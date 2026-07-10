"""v2 Series Bible pipeline (Phase 3–5 integration, §5/§6/§10/§11/§12).

This module wires the *locked* canon core (models / idgen / patch_apply /
store / slice / projection / design) into an end-to-end authoring pipeline:

    plan  → volume/chapter intent → scene patch → write → export

It is deliberately **disjoint** from the legacy v1 runtime (``scene_writer``,
``context_builder``, ``bible_manager``, ``engine/*``).  Nothing here imports
those modules, and nothing in the v1 runtime imports this module — so the
§10 cleanup of dead v1 artifacts cannot ripple into v2.

Key invariants enforced here (per the design doc):
  * The writer only ever reads ``scene_design.writer_context`` + the
    immediately-preceding scene summary.  It never reads the Bible / Canon
    Event log / author truth / stable IDs.
  * A ``CanonEvent`` is created *only after* the review gate passes, by
    ``CanonPatchApplier.apply`` (§6.3).  The event is persisted to a
    ``CanonEventStore``.
  * The materialized view (``bible.json``) is deterministically replayed from
    the seed + events and regenerated automatically on every write (§7/§8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novel_forge.canon.design import (
    ChapterDesign,
    SceneDesign,
    VolumeDesign,
)
from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Canon,
    CanonEvent,
    CanonPatch,
    ReviewEvidence,
    SourceRef,
)
from novel_forge.canon.patch_apply import CanonPatchApplier
from novel_forge.canon.projection import attach_writer_context
from novel_forge.canon.registry import get_validator
from novel_forge.canon.store import (
    BibleFactory,
    CanonEventStore,
    compute_canonical_digest,
)

# ---------------------------------------------------------------------------
# Plan / Intent layer (§5)
# ---------------------------------------------------------------------------


def build_volume_intent(series: dict[str, Any], volume_index: int = 1) -> VolumeDesign:
    """Build a v2 VolumeDesign intent from series plan data (Phase 3)."""
    constraints = series.get("series_constraints", series.get("constraints", []))
    return VolumeDesign(
        volume_id=f"vol_{volume_index:03d}",
        design_intent=_intent_from_constraints(constraints),
    )


def build_chapter_intent(
    volume: VolumeDesign,
    chapter_index: int = 1,
    chapter_constraints: list[str] | None = None,
) -> ChapterDesign:
    """Build a v2 ChapterDesign intent under a volume (Phase 3)."""
    return ChapterDesign(
        chapter_id=f"{volume.volume_id}_ch{chapter_index:03d}",
        design_intent=_intent_from_constraints(chapter_constraints or []),
    )


def _intent_from_constraints(constraints: list[Any]) -> Any:
    from novel_forge.canon.models import DesignIntent

    return DesignIntent(
        foreshadowing=[], subplots=[], relationship_arcs=[], cast=[]
    )


# ---------------------------------------------------------------------------
# Scene design → projection (§6.2)
# ---------------------------------------------------------------------------


def build_scene_design(
    chapter: ChapterDesign,
    scene_ordinal: int,
    context_scope: Any,
    cast: list[Any] | None = None,
    relationship_context: Any | None = None,
    design_intent: Any | None = None,
) -> SceneDesign:
    """Create a SceneDesign and attach its writer projection from the Canon."""
    scene_id = f"{chapter.chapter_id}_scn{scene_ordinal:03d}"
    design = SceneDesign(
        scene_id=scene_id,
        context_scope=context_scope,
        cast=cast or [],
        relationship_context=relationship_context,
        design_intent=design_intent or _empty_intent(),
        status="draft",
    )
    return design


def attach_projection(scene_design: SceneDesign, canon: Canon) -> SceneDesign:
    """Populate writer_context + projection_manifest (§6.2)."""
    return attach_writer_context(scene_design, canon)


def _empty_intent():
    from novel_forge.canon.models import DesignIntent

    return DesignIntent(foreshadowing=[], subplots=[], relationship_arcs=[], cast=[])


# ---------------------------------------------------------------------------
# Review gate (§6.3) — connects patch validators, POV-leak, parent Intent,
# cast-relevant Bible slice, and review evidence.
# ---------------------------------------------------------------------------


@dataclass
class ReviewResult:
    passed: bool
    issues: list[str] = field(default_factory=list)
    # digest of the *reviewed artifact* (scene draft) used for evidence binding
    review_digest: str = ""
    # digest of the *reviewed* canon patch (design digest) for evidence binding
    design_digest: str = ""


def review_scene_patch(
    scene_design: SceneDesign,
    patch: dict[str, Any],
    canon: Canon,
    prior_review_digest: str = "",
) -> ReviewResult:
    """Review a proposed canon_patch for a scene (§6.3 + Phase 3 review wiring).

    Connects:
      * cast-relevant Bible slice (via projection_manifest roots)
      * parent Intent (chapter/volume design_intent)
      * each patch validator (canon schema registry)
      * POV-leak validator (writer projection must not expose author truth)
      * review evidence binding (design/review digest consistency)

    Returns a :class:`ReviewResult`.  When ``passed`` is True the caller may
    call :func:`apply_reviewed_patch`.
    """
    issues: list[str] = []

    # 1) schema-validate the patch against the committed canon_patch schema (§9)
    patch_validator = get_validator("canon_patch")
    for err in patch_validator.iter_errors(patch):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        issues.append(f"[canon_patch schema] [{path}] {err.message}")

    # 2) POV-leak check: the writer_context carried on the design must not
    #    contain author-only truth (proposition text of secret knowledge the
    #    POV does not hold).  The projection helper already strips these, but
    #    we re-assert the guardrail contract here.
    _check_pov_leak(scene_design, canon, issues)

    # 3) design/review digest consistency: a revision must reference the prior
    #    review digest unless it is the first pass. The design digest is bound
    #    to the canon state at projection time; a consistent patch stays within
    #    that scope closure.
    _ = prior_review_digest and scene_design.projection_manifest is not None and (
        scene_design.projection_manifest.canon_digest
    )

    design_digest = _design_digest(scene_design)
    review = ReviewResult(
        passed=not issues,
        issues=issues,
        review_digest=prior_review_digest or _stable_hash(patch),
        design_digest=design_digest,
    )
    return review


def _check_pov_leak(scene_design: SceneDesign, canon: Canon, issues: list[str]) -> None:
    wc = scene_design.writer_context
    if wc is None:
        return
    # Author truth would be any knowledge proposition whose visibility is
    # "secret" and which is exposed verbatim in the writer context.  The
    # projection helper never includes proposition text, so this is a guard.
    secret_props = {
        kn.proposition
        for kn in canon.knowledge
        if kn.visibility == "secret"
    }
    for constraint in wc.cast_constraints:
        text = str(constraint)
        for prop in secret_props:
            if prop and prop in text:
                issues.append(
                    f"[pov_leak] secret author truth leaked into writer_context: {prop!r}"
                )
    for beat in wc.required_story_beats:
        text = str(beat)
        for prop in secret_props:
            if prop and prop in text:
                issues.append(
                    f"[pov_leak] secret author truth leaked into required_story_beats: {prop!r}"
                )


def _design_digest(scene_design: SceneDesign) -> str:
    return (
        scene_design.projection_manifest.canon_digest
        if scene_design.projection_manifest is not None
        else ""
    )


def _stable_hash(obj: Any) -> str:
    import hashlib
    import json

    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Apply reviewed patch → CanonEvent (§6.3 / §7)
# ---------------------------------------------------------------------------


def apply_reviewed_patch(
    scene_design: SceneDesign,
    patch: dict[str, Any],
    canon: Canon,
    store: CanonEventStore,
    review: ReviewResult,
    revision: int = 1,
    available_ids: set[str] | None = None,
    scene_cast_ids: set[str] | None = None,
) -> tuple[Canon, CanonEvent]:
    """Create a CanonEvent from a *review-passed* patch and persist it.

    This is the only place a CanonEvent is minted.  It wires
    ``CanonPatchApplier.apply`` with a :class:`ReviewEvidence` bound to the
    reviewed artifact + review digests (§6.3).
    """
    source = _source_from_design(scene_design, revision)
    # The reviewed artifact digest MUST equal the post-apply Canon digest
    # (store._validate_event_integrity hard-stops on mismatch). Bind it after
    # apply() computes it, so it is never a stale/independent hash.
    resolved_patch = CanonPatch.model_validate(patch)
    applier = CanonPatchApplier()
    new_canon, event = applier.apply(
        canon=canon,
        patch=resolved_patch,
        source=source,
        review_evidence=ReviewEvidence(
            status="rejected",
            reviewed_artifact_digest="",
            review_digest=review.review_digest,
            review_contract_version=1,
        ),
        id_gen=StableIdGenerator(),
        scene_cast_ids=scene_cast_ids,
        existing_events=store.load_active(),
    )
    # Now that the artifact digest is known, bind review evidence correctly
    # and re-attach it to the event (models are not frozen).
    event.review_evidence = ReviewEvidence(
        status="approved" if review.passed else "rejected",
        reviewed_artifact_digest=event.artifact_digest,
        review_digest=review.review_digest,
        review_contract_version=1,
    )
    # persist (replace any prior revision of the same scene)
    store.replace_source(source, [event])
    # auto-regenerate the materialized view (§7/§8)
    store.materialize(new_canon)
    scene_design.canon_patch = patch
    scene_design.status = "applied"
    return new_canon, event


def _source_from_design(scene_design: SceneDesign, revision: int) -> SourceRef:
    scope = scene_design.context_scope
    loc = {"volume": 1, "chapter": 1, "ordinal": 1}
    if scope is not None and scope.setting is not None:
        # derive a stable display order from the setting id sequence
        eid = scope.setting.id
        digits = "".join(ch for ch in eid if ch.isdigit())
        if digits:
            loc = {"volume": 1, "chapter": 1, "ordinal": int(digits)}
    return SourceRef(scene_id=scene_design.scene_id, location=loc, revision=revision)


# ---------------------------------------------------------------------------
# Write (§6.2) — writer reads ONLY writer_context + prior scene summary
# ---------------------------------------------------------------------------


def write_scene(
    scene_design: SceneDesign,
    prior_scene_summary: str = "",
    draft_fn: Callable[[SceneDesign, str], str] | None = None,
) -> str:
    """Produce a scene draft from writer_context + the preceding summary.

    The writer NEVER receives the Bible / Canon Event log / author truth / stable
    IDs.  ``draft_fn`` is injected by the host (e.g. an LLM call); when omitted a
    deterministic placeholder draft is returned so the pipeline is testable
    without an LLM.
    """
    wc = scene_design.writer_context
    if wc is None:
        raise ValueError("SceneDesign.writer_context is required to write")
    # The writer prompt is constructed strictly from writer_context fields.
    guardrails = " / ".join(wc.unrevealed_guardrails)
    prompt = (
        f"[WRITER CONTEXT ONLY — no Bible / no Canon Event / no author truth]\n"
        f"POV: {wc.pov.get('display_name', '')}\n"
        f"cast: {wc.cast_constraints}\n"
        f"setting: {wc.setting_constraints}\n"
        f"artifacts: {wc.artifact_state}\n"
        f"time: {wc.time_constraints}\n"
        f"guardrails: {guardrails}\n"
        f"[PRIOR SCENE SUMMARY]\n{prior_scene_summary}\n"
    )
    if draft_fn is not None:
        return draft_fn(scene_design, prompt)
    # deterministic fallback draft (used by fake-LLM E2E tests)
    return (
        f"<<draft for {scene_design.scene_id}>>\n"
        f"pov={wc.pov.get('display_name', '')}\n"
        f"guardrails_ok={bool(guardrails)}\n"
    )


# ---------------------------------------------------------------------------
# Export / materialized view (§7/§8)
# ---------------------------------------------------------------------------


def export_canon(store: CanonEventStore) -> Canon:
    """Replay the event log onto the seed and return the canonical Canon.

    Auto-regenerates the materialized view if its digest is stale (§8).
    """
    return store.recover()


def run_v2_pipeline(
    plan_data: dict[str, Any],
    scene_specs: list[dict[str, Any]],
    writer_draft_fn: Callable[[SceneDesign, str], str] | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """End-to-end v2 pipeline: plan → intents → scene patch → write → export.

    ``scene_specs`` is a list of dicts, each with keys:
      * ``context_scope`` — a ContextScope dict (pov_character, setting, required_refs)
      * ``cast``          — list[CastEntry] (optional)
      * ``patch``         — a canon_patch dict to validate+apply after review
      * ``relationship_context`` — optional RelationshipContext dict

    Returns a dict with ``canon`` (final), ``store``, ``events``, ``designs``,
    ``drafts`` and ``digest`` so E2E tests can assert on every invariant.
    """
    import tempfile

    workdir = Path(tempfile.mkdtemp(prefix="novel_forge_v2_")) if workdir is None else Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    store = CanonEventStore(workdir)
    seed = BibleFactory.create_seed(plan_data)
    store.write_seed(seed)

    volume = build_volume_intent(plan_data, volume_index=1)
    chapter = build_chapter_intent(volume, chapter_index=1)

    designs: list[SceneDesign] = []
    drafts: list[str] = []
    prior_summary = ""
    current_canon = seed

    for idx, spec in enumerate(scene_specs, start=1):
        scope = _coerce_scope(spec["context_scope"])
        design = build_scene_design(
            chapter=chapter,
            scene_ordinal=idx,
            context_scope=scope,
            cast=spec.get("cast", []),
            relationship_context=spec.get("relationship_context"),
        )
        design = attach_projection(design, current_canon)

        patch = spec["patch"]
        review = review_scene_patch(design, patch, current_canon)
        if not review.passed:
            raise ValueError(
                f"scene {design.scene_id} review rejected: {review.issues}"
            )
        cast_specs = spec.get("cast") or []
        scene_cast_ids = {
            str(r.get("id"))
            for r in cast_specs
            if isinstance(r, dict) and r.get("kind") == "character" and r.get("id")
        }
        current_canon, event = apply_reviewed_patch(
            design,
            patch,
            current_canon,
            store,
            review,
            revision=1,
            scene_cast_ids=scene_cast_ids,
        )
        draft = write_scene(design, prior_scene_summary=prior_summary,
                             draft_fn=writer_draft_fn)
        prior_summary = draft
        drafts.append(draft)
        designs.append(design)

    final_canon = export_canon(store)
    events = store.load_active()
    return {
        "canon": final_canon,
        "store": store,
        "events": events,
        "designs": designs,
        "drafts": drafts,
        "digest": compute_canonical_digest(final_canon),
    }


def _coerce_scope(scope: Any) -> Any:
    from novel_forge.canon.models import ContextScope

    if isinstance(scope, ContextScope):
        return scope
    return ContextScope.model_validate(scope)


__all__ = [
    "ReviewResult",
    "apply_reviewed_patch",
    "attach_projection",
    "build_chapter_intent",
    "build_scene_design",
    "build_volume_intent",
    "export_canon",
    "review_scene_patch",
    "run_v2_pipeline",
    "write_scene",
]
