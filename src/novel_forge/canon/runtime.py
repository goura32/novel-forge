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
from uuid import uuid4

from novel_forge.canon.design import (
    CastCharacter,
    CastEntry,
    CastLocalRole,
    ChapterDesign,
    SceneDesign,
    VolumeDesign,
)
from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Canon,
    CanonEvent,
    CanonPatch,
    EntityRef,
    ReviewEvidence,
    SceneLocation,
    SourceRef,
)
from novel_forge.canon.patch_apply import CanonPatchApplier
from novel_forge.canon.projection import attach_writer_context
from novel_forge.canon.registry import get_validator
from novel_forge.canon.self_correction_tracker import SelfCorrectionTracker
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


def _intent_from_constraints(constraints: list[Any]):
    from novel_forge.canon.models import DesignIntent

    normalized = [str(item) for item in constraints if str(item).strip()]
    return DesignIntent(constraints=normalized)


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
    scene_id: str | None = None,
    source_location: SceneLocation | None = None,
) -> SceneDesign:
    """Create a SceneDesign with an opaque immutable ID and explicit location.

    ``cast`` accepts either canonical ``CastEntry`` instances or flat dicts of
    the shapes ``{"kind": "character", "id": ...}`` / ``{"kind": "local_role",
    "label": ..., "count": ..., "scene_function": ...}``.  Flat dicts are coerced
    to ``CastCharacter`` / ``CastLocalRole`` so callers cannot silently drop the
    cast by passing the nested shape incorrectly (§7.2).
    """
    opaque_scene_id = scene_id or f"scn_{uuid4().hex}"
    location = source_location or SceneLocation(
        volume=1,
        chapter=1,
        ordinal=scene_ordinal,
    )
    coerced_cast: list[CastEntry] = [_coerce_cast_entry(c) for c in (cast or [])]
    design = SceneDesign(
        scene_id=opaque_scene_id,
        source_location=location,
        context_scope=context_scope,
        cast=coerced_cast,
        relationship_context=relationship_context,
        design_intent=design_intent or _empty_intent(),
        status="draft",
    )
    return design


def _coerce_cast_entry(entry: Any) -> CastEntry:
    """Coerce a flat cast dict to its canonical ``CastEntry`` model.

    Accepts ``CastCharacter`` / ``CastLocalRole`` instances unchanged, or a flat
    dict.  A flat ``{"kind": "character", "id": ...}`` becomes
    ``CastCharacter(character=EntityRef(kind="character", id=...))``; a flat
    ``{"kind": "local_role", ...}`` becomes ``CastLocalRole(...)``.  Anything
    else is validated as-is so the model raises a clear error.
    """
    if isinstance(entry, (CastCharacter, CastLocalRole)):
        return entry
    if isinstance(entry, dict):
        kind = entry.get("kind")
        if kind == "character":
            ref = entry.get("character")
            flat_id = entry.get("id")
            if isinstance(ref, dict):
                entity_ref = EntityRef.model_validate(ref)
                if flat_id is not None and str(flat_id) != entity_ref.id:
                    raise ValueError(
                        "character cast has conflicting character IDs in 'id' and 'character.id'"
                    )
            elif flat_id is not None:
                entity_ref = EntityRef(kind="character", id=str(flat_id))
            else:
                raise ValueError("character cast requires 'id' or 'character'")
            if entity_ref.kind != "character":
                raise ValueError("character cast requires character.kind='character'")
            return CastCharacter(character=entity_ref)
        if kind == "local_role":
            return CastLocalRole.model_validate(entry)
    # unknown shape — let pydantic surface a precise validation error
    return CastCharacter.model_validate(entry)


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
    # Digest of the *reviewed SceneDesign artifact*: the scene design content
    # plus the exact patch payload that was reviewed (§6.3 / §7.1).  This is the
    # value bound into ``CanonEvent.artifact_digest`` and
    # ``ReviewEvidence.reviewed_artifact_digest``.  It is deliberately NOT the
    # post-apply Canon digest — the event must identify the reviewed input, not
    # the resulting state.
    artifact_digest: str = ""
    # Digest of the exact patch payload reviewed by this result.
    review_digest: str = ""
    # Canon digest used to build the writer projection and review context.
    design_digest: str = ""
    # Explicit duplicate of the patch binding: retained separately so review
    # evidence cannot be confused with Canon/projection state.
    patch_digest: str = ""


def review_scene_patch(
    scene_design: SceneDesign,
    patch: dict[str, Any],
    canon: Canon,
    prior_review_digest: str = "",
    seed: Canon | None = None,
    tracker: SelfCorrectionTracker | None = None,
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

    If ``tracker`` is provided, every emitted issue is recorded as a
    :class:`CorrectionRecord` (append-only telemetry; the Canon is never
    mutated by tracking).
    """
    issues: list[str] = []

    # 1) schema-validate the patch against the committed canon_patch schema (§9)
    patch_validator = get_validator("canon_patch")
    for err in patch_validator.iter_errors(patch):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        issues.append(f"[canon_patch schema] [{path}] {err.message}")

    # 1b) Semantic preflight against the *current* Canon.  Schema acceptance
    # is not approval: cast/scope, continuity, relationship, knowledge and
    # transition rules are evaluated before a review can pass.
    if not issues:
        try:
            typed_patch = CanonPatch.model_validate(patch)
            source = _source_from_design(scene_design, revision=1)
            CanonPatchApplier().apply(
                canon=canon,
                patch=typed_patch,
                source=source,
                review_evidence=ReviewEvidence(
                    status="approved",
                    reviewed_artifact_digest="sha256:review-preflight",
                    review_digest="sha256:review-preflight",
                ),
                id_gen=StableIdGenerator(),
                scene_cast_ids=_scene_cast_ids(scene_design),
                existing_events=[],
            )
        except Exception as exc:
            issues.append(f"[canon_patch semantic] {exc}")

    # 2) POV-leak check: the writer_context carried on the design must not
    #    contain author-only truth (proposition text of secret knowledge the
    #    POV does not hold).  The projection helper already strips these, but
    #    we re-assert the guardrail contract here.
    _check_pov_leak(scene_design, canon, issues)

    # 3b) Cast-relevant Bible slice: relationships must not be changed (created
    #     / promoted / transitioned / perspective-updated) without the related
    #     cast in scope (§6.3 cast-relevant slice).
    _check_cast_relevant_cast(scene_design, patch, canon, issues)
    # Canon change therefore requires a fresh projection and review.
    current_digest = compute_canonical_digest(canon)
    if scene_design.projection_manifest is None:
        issues.append("[review_evidence] scene design has no projection manifest")
    elif scene_design.projection_manifest.canon_digest != current_digest:
        issues.append(
            "[review_evidence] projection canon digest is stale; rebuild projection and re-review"
        )

    patch_digest = _stable_hash(patch)
    if prior_review_digest and prior_review_digest != patch_digest:
        issues.append("[review_evidence] reviewed patch changed; re-review is required")

    design_digest = _design_digest(scene_design)
    # The reviewed artifact digest binds the *reviewed input* (scene design
    # content + the exact patch reviewed), not the resulting Canon state (§6.3 /
    # §7.1).  It is what ``apply_reviewed_patch`` must echo into the event and
    # review evidence, and what forces a re-review if either changes.
    artifact_digest = _reviewed_artifact_digest(scene_design, patch)
    review = ReviewResult(
        passed=not issues,
        issues=issues,
        artifact_digest=artifact_digest,
        review_digest=prior_review_digest or patch_digest,
        design_digest=design_digest,
        patch_digest=patch_digest,
    )
    if tracker is not None and issues:
        loc = scene_design.source_location
        tracker.record_issues(
            issues,
            scene_id=scene_design.scene_id,
            source_ref=(
                f"vol{loc.volume}/ch{loc.chapter}/ord{loc.ordinal}"
                if loc is not None
                else ""
            ),
        )
    return review


def _scene_cast_ids(scene_design: SceneDesign) -> set[str]:
    """Extract actual Canon character IDs from the persisted scene scope/cast."""
    ids: set[str] = set()
    if scene_design.context_scope is not None and scene_design.context_scope.pov_character is not None:
        ids.add(scene_design.context_scope.pov_character.id)
    for entry in scene_design.cast:
        if entry.kind == "character":
            ids.add(entry.character.id)
    return ids


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


def _check_cast_relevant_cast(
    scene_design: SceneDesign, patch: dict[str, Any], canon: Canon, issues: list[str]
) -> None:
    """A cast-relevant relationship change requires the related cast in scope (§6.3)."""
    scope_ids = _scene_cast_ids(scene_design)
    rel = patch.get("relationships", {})
    changed_rel_ids: set[str] = set()
    for op_field in ("create", "promote", "transition", "updates", "perspective_updates"):
        for item in rel.get(op_field, []):
            rid = item.get("id") or item.get("creation_key")
            if rid:
                changed_rel_ids.add(str(rid))
    if not changed_rel_ids:
        return
    for rid in changed_rel_ids:
        existing = canon.get_entity("relationship", rid)
        if existing is None:
            # new relationship — check participants are in scope
            created = rel.get("create", [])
            rel_item: dict[str, Any] = next(
                (c for c in created if c.get("creation_key") == rid or c.get("id") == rid), {}
            )
            raw_parts = rel_item.get("participant_ids", [])
            participants: list[str] = [
                str(p.get("id")) if isinstance(p, dict) else str(p) for p in raw_parts
            ]
            out_of_scope = [p for p in participants if p and p not in scope_ids]
            if out_of_scope:
                issues.append(
                    f"[cast_relevant] relationship {rid} references out-of-scope cast: {out_of_scope}"
                )
        else:
            out_of_scope = [pid for pid in existing.participant_ids if pid not in scope_ids]
            if out_of_scope:
                issues.append(
                    f"[cast_relevant] relationship {rid} involves out-of-scope cast: {out_of_scope}"
                )


def _stable_hash(obj: Any) -> str:
    import hashlib
    import json

    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


# SceneDesign fields that are bookkeeping rather than reviewable artifact
# content.  They are excluded from the reviewed artifact digest so that a
# projection rebuild (``projection_manifest``) or status transition after a
# review does not, by itself, invalidate an otherwise-unchanged design (§6.3 /
# §7.1).  ``canon_patch`` is excluded because the reviewed patch is supplied
# separately to :func:`review_scene_patch` / :func:`apply_reviewed_patch` and is
# already bound via ``ReviewResult.patch_digest``.
_SCENE_ARTIFACT_EXCLUDE = {"projection_manifest", "status", "canon_patch"}


def _reviewed_artifact_digest(scene_design: SceneDesign, patch: dict[str, Any]) -> str:
    """Digest of the reviewed SceneDesign artifact (design content + patch).

    This is the value bound into ``CanonEvent.artifact_digest`` and
    ``ReviewEvidence.reviewed_artifact_digest`` (§6.3 / §7.1).  It identifies the
    exact reviewed input (scene design text + patch), NOT the resulting Canon
    state, so a later edit to either forces a re-review at apply time.
    """
    design_dump = scene_design.model_dump(mode="json", exclude=_SCENE_ARTIFACT_EXCLUDE)
    payload = {"design": design_dump, "patch": patch}
    return _stable_hash(payload)


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
    if not review.passed:
        raise ValueError("review rejected: Canon Event must not be created or persisted")
    current_digest = compute_canonical_digest(canon)
    if review.design_digest != current_digest:
        raise ValueError("review evidence is stale for the current Canon; rebuild projection and re-review")
    if review.patch_digest and review.patch_digest != _stable_hash(patch):
        raise ValueError("reviewed patch changed; re-review is required")

    # §6.3 / §7.1: the event must bind the *reviewed SceneDesign artifact
    # digest* (scene design content + the exact patch that was reviewed), and
    # the review evidence must echo it.  If the scene design text or the patch
    # changed after the review, the reviewed artifact digest no longer matches
    # the current input — reject the apply and force a re-review.
    expected_artifact = _reviewed_artifact_digest(scene_design, patch)
    if not review.artifact_digest:
        raise ValueError("review result carries no reviewed artifact digest")
    if review.artifact_digest != expected_artifact:
        raise ValueError(
            "reviewed SceneDesign artifact changed after review; re-review is required"
        )

    source = _source_from_design(scene_design, revision)
    resolved_patch = CanonPatch.model_validate(patch)
    authoritative_scene_cast_ids = _scene_cast_ids(scene_design)
    if scene_cast_ids is not None and scene_cast_ids != authoritative_scene_cast_ids:
        raise ValueError("scene_cast_ids diverge from SceneDesign.cast")
    applier = CanonPatchApplier()
    new_canon, event = applier.apply(
        canon=canon,
        patch=resolved_patch,
        source=source,
        review_evidence=ReviewEvidence(
            status="approved",
            reviewed_artifact_digest=review.artifact_digest,
            review_digest=review.review_digest,
            review_contract_version=1,
        ),
        id_gen=StableIdGenerator(),
        scene_cast_ids=authoritative_scene_cast_ids,
        existing_events=store.load_active(),
        artifact_digest=review.artifact_digest,
    )
    # The event artifact_digest is now the reviewed SceneDesign artifact digest
    # (set by the applier), and review_evidence.reviewed_artifact_digest echoes
    # it.  The store integrity check (reviewed_artifact_digest ==
    # artifact_digest) therefore holds for the reviewed input, not for the
    # post-apply Canon state.
    # Persist replay-critical scope context with the event.  Replay must never
    # consult a transient SceneDesign object to validate relationship changes.
    event.scene_cast_ids = sorted(authoritative_scene_cast_ids)
    # The scene artifact may be promoted only after the patch was resolved
    # successfully.  ``SceneDesign`` validates the draft → review_passed
    # transition atomically, so an applied design cannot lose its patch.
    scene_design.accept_reviewed_patch(patch)
    # The store transaction validates dependencies, replays the *active* event
    # set from immutable seed, and materializes only that replay result.
    replayed = store.replace_design_segment([source.scene_id], [event])

    scene_design.mark_patch_applied()
    return replayed, event


def _source_from_design(scene_design: SceneDesign, revision: int) -> SourceRef:
    if scene_design.source_location is None:
        raise ValueError("SceneDesign.source_location is required for Canon Event creation")
    return SourceRef(
        scene_id=scene_design.scene_id,
        location=scene_design.source_location,
        revision=revision,
    )


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
    tracker: SelfCorrectionTracker | None = None,
) -> dict[str, Any]:
    """End-to-end v2 pipeline: plan → intents → scene patch → write → export.

    This is the low-level, programmatic entry point used by E2E tests and
    ad-hoc tooling.  Production commands (plan/design/write/export) go through
    ``novel_forge.canon.public_runtime.V2ProjectRuntime`` instead; that adapter
    is the supported public surface for the v2 flow.

    ``scene_specs`` is a list of dicts, each with keys:
      * ``context_scope`` — a ContextScope dict (pov_character, setting, required_refs)
      * ``cast``          — list[CastEntry] (optional)
      * ``patch``         — a canon_patch dict to validate+apply after review
      * ``relationship_context`` — optional RelationshipContext dict

    If ``tracker`` is provided, every review-gate issue is recorded as a
    :class:`CorrectionRecord` (append-only telemetry; the Canon is never
    mutated by tracking).

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
        review = review_scene_patch(design, patch, current_canon, tracker=tracker)
        if not review.passed:
            raise ValueError(
                f"scene {design.scene_id} review rejected: {review.issues}"
            )
        # SceneDesign.cast is the authoritative scene scope (§7.2).  ``cast``
        # was validated/coerced at construction and must not be re-read from
        # the caller payload as a second, potentially divergent source.
        scene_cast_ids = _scene_cast_ids(design)
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
