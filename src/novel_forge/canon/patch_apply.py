"""Pure CanonPatch → Canon application (§4.4, §6, §6.1, §7.1).

This module contains :class:`CanonPatchApplier`, a *pure* function that takes a
:class:`Canon`, a :class:`CanonPatch`, the originating :class:`SourceRef`, the
:class:`ReviewEvidence` that approved the patch, and a
:class:`StableIdGenerator`, and returns a *new* ``Canon`` plus the immutable
:class:`CanonEvent` recording the change.

No I/O is performed. All §6.1 constraints are validated here and any violation
raises :class:`PatchValidationError` (a subclass of ``ValueError``) so callers
can treat it as a hard reject.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    KIND_BY_PREFIX,
    Artifact,
    Canon,
    CanonEvent,
    CanonPatch,
    Character,
    Collective,
    CreationRef,
    EntityKind,
    EntityRef,
    Foreshadowing,
    Glossary,
    HolderState,
    Knowledge,
    Location,
    Relationship,
    ReviewEvidence,
    SourceRef,
    Subplot,
    compute_canonical_digest,
)
from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.canon.patch_apply")

# Accepted importance tiers (§4.1 / §4.4).
IMPORTANCE_TIERS = ["minor", "supporting", "core"]
PROMOTION_ORDER = {"minor": 0, "supporting": 1, "core": 2}

# Custody may only reference these entity kinds (§4.6 / §6.1).
CUSTODY_KINDS = {"character", "collective", "location"}

# Knowledge holder states (§4.6).
KNOWLEDGE_STATES = {"knows", "suspects", "believes", "unaware"}

# Truth status values and the only allowed normal-patch transitions (§4.4 / §6.1).
TRUTH_STATUSES = {"confirmed", "contested", "false_belief"}
TRUTH_TRANSITIONS = {
    ("contested", "confirmed"),
    ("contested", "false_belief"),
}

# Forbidden-fields guard: these keys must never appear in a normal scene patch
# payload (they require plan seed / canon_correction). See §6.1 last bullet.
_CORRECTION_ONLY_KEYS = {
    "world_rules",
    "series_constraints",
    "immutable_constraints",
    "properties",
    "proposition",
    "truth_status",  # only the *transition* op may touch truth_status
}


from novel_forge.canon.models import PatchValidationError  # noqa: E402,F401


def _ref(o: Any) -> EntityRef:
    """Coerce a dict / EntityRef / CreationRef-ish object to an EntityRef."""
    if isinstance(o, EntityRef):
        return o
    if isinstance(o, dict):
        return EntityRef(kind=o["kind"], id=o["id"])
    raise PatchValidationError(f"cannot coerce {o!r} to EntityRef")


def _resolve_ref(ref: Any, created_map: dict[str, str]) -> EntityRef:
    """Resolve a patch reference (EntityRef or CreationRef) to a concrete EntityRef.

    A ``CreationRef`` (``{creation_key}``) must have been assigned a stable ID
    in ``created_map`` (key ``<kind>:<creation_key>`` or bare ``creation_key``);
    references can only point at existing Canon IDs or entities created in the
    same patch (§3.4 / §6.1).
    """
    if isinstance(ref, CreationRef):
        key = ref.creation_key
        for candidate in (f"{key}", f"character:{key}", f"location:{key}"):
            if candidate in created_map:
                entity_id = created_map[candidate]
                prefix = entity_id.split("_", 1)[0]
                kind = cast(EntityKind, KIND_BY_PREFIX.get(prefix, prefix))
                return EntityRef(kind=kind, id=entity_id)
        raise PatchValidationError(
            f"creation_key '{ref.creation_key}' referenced before/without a matching create"
        )
    return _ref(ref)


def _entity_by_id(canon: Canon, kind: str, entity_id: str) -> Any:
    ent = canon.get_entity(kind, entity_id)
    if ent is None:
        raise PatchValidationError(f"{kind} '{entity_id}' does not exist in Canon")
    return ent


class CanonPatchApplier:
    """Apply a validated CanonPatch to a Canon, returning (new_canon, event)."""

    def apply(
        self,
        canon: Canon,
        patch: CanonPatch,
        source: SourceRef,
        review_evidence: ReviewEvidence,
        id_gen: StableIdGenerator,
        scene_cast_ids: set[str] | None = None,
        existing_events: list[CanonEvent] | None = None,
        artifact_digest: str | None = None,
    ) -> tuple[Canon, CanonEvent]:
        """Pure apply. ``scene_cast_ids`` is the set of character ids appearing
        in the scene cast (used to validate Knowledge holder updates and
        Relationship updates, §6.1).

        When ``artifact_digest`` is provided it is bound verbatim into the
        resulting :class:`CanonEvent` instead of the post-apply Canon digest.
        This is used by :func:`apply_reviewed_patch` to record the *reviewed
        SceneDesign artifact digest* (design content + reviewed patch) per
        §6.3 / §7.1 — not the resulting Canon state.
        """
        scene_cast_ids = scene_cast_ids or set()

        # 1) Resolve creation_key → stable ID via StableIdGenerator.
        resolved_patch = deepcopy(patch)
        created_map: dict[str, str]
        resolved_patch, created_map = id_gen.assign(
            resolved_patch, canon, source, existing_events
        )

        errors: list[str] = []
        new_canon = deepcopy(canon)

        try:
            self._apply_characters(new_canon, resolved_patch, created_map, errors)
            self._apply_collectives(new_canon, resolved_patch, created_map, errors)
            self._apply_locations(new_canon, resolved_patch, created_map, errors)
            self._apply_artifacts(new_canon, resolved_patch, created_map, errors)
            self._apply_knowledge(
                new_canon, resolved_patch, created_map, errors, scene_cast_ids
            )
            self._apply_chronology(new_canon, resolved_patch, errors)
            self._apply_relationships(
                new_canon, resolved_patch, created_map, errors, scene_cast_ids
            )
            self._apply_foreshadowing(new_canon, resolved_patch, created_map, errors)
            self._apply_subplots(new_canon, resolved_patch, created_map, errors)
            self._apply_glossary(new_canon, resolved_patch, created_map, errors)
        except PatchValidationError as exc:
            errors.extend(exc.errors if exc.errors else [str(exc)])

        if errors:
            detail = "; ".join(errors)
            raise PatchValidationError(
                f"canon patch from {source.scene_id} rejected: {len(errors)} violation(s): {detail}",
                errors=errors,
            )

        # 3) Build event + digest.
        digest = compute_canonical_digest(new_canon)
        created_entity_ids = dict(created_map)
        # The event ``artifact_digest`` is the reviewed SceneDesign artifact
        # digest when supplied (§6.3 / §7.1); otherwise it falls back to the
        # post-apply Canon digest for non-reviewed call sites (e.g. the review
        # semantic preflight in ``review_scene_patch``).
        event_digest = artifact_digest if artifact_digest is not None else digest
        event = CanonEvent(
            event_id=f"cev_{source.scene_id}_r{source.revision}",
            source=source,
            artifact_digest=event_digest,
            review_evidence=review_evidence,
            patch=resolved_patch,
            created_entity_ids=created_entity_ids,
            created_at=datetime.now(UTC).isoformat(),
        )
        return new_canon, event

    # -- characters ---------------------------------------------------------

    def _apply_characters(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.characters

        # create (§6.1: minor only from scene patch; supporting needs parent Intent)
        for c in ops.create:
            if c.id is None:
                errors.append(f"character create '{c.creation_key}' missing stable id")
                continue
            self._validate_character_create(c, errors)
            if c.importance == "core":
                errors.append(
                    f"character create '{c.creation_key}' sets importance=core; "
                    "Core characters may only be created in plan seed"
                )
            ent = Character(
                id=c.id,
                identity=c.identity,
                importance=c.importance,
                tracking_level=c.tracking_level,
                narrative_function=c.narrative_function,
                profile=c.profile,
                continuity_card=c.continuity_card,
                affiliations=c.affiliations,
                last_changed_by=None,
            )
            canon.characters.append(ent)

        # state_updates: independent current_state / current_location (§6.1)
        for u in ops.state_updates:
            ref = _resolve_ref(u.character, created_map)
            ent = _entity_by_id(canon, "character", ref.id)
            if u.current_state is not None:
                ent.continuity_card.current_state = u.current_state
            if u.current_location is not None:
                loc_ref = _resolve_ref(u.current_location, created_map)
                if loc_ref.kind != "location":
                    errors.append(
                        f"character '{ref.id}' current_location must be a Location ref"
                    )
                    continue
                if canon.get_entity("location", loc_ref.id) is None:
                    errors.append(
                        f"character '{ref.id}' current_location references unknown "
                        f"location '{loc_ref.id}'"
                    )
                    continue
                ent.continuity_card.current_location = loc_ref

        # promote: minor→supporting→core, keep ID/alias/affiliation, profile_additions
        # only fill null profile fields (§4.4 / §6.1)
        for p in ops.promote:
            ref = _resolve_ref(p.character, created_map)
            ent = _entity_by_id(canon, "character", ref.id)
            if PROMOTION_ORDER.get(p.to_importance, 99) <= PROMOTION_ORDER.get(
                ent.importance, 0
            ):
                errors.append(
                    f"promote '{ref.id}' to '{p.to_importance}' is not a strict "
                    f"promotion from current '{ent.importance}'"
                )
                continue
            # reject profile corrections: only fill null/empty fields
            if ent.profile is None:
                ent.profile = _empty_profile()
            if p.profile_additions is not None:
                for field_name in type(p.profile_additions).model_fields:
                    value = getattr(p.profile_additions, field_name)
                    if value in (None, ""):
                        continue
                    existing = getattr(ent.profile, field_name, None)
                    if existing not in (None, ""):
                        errors.append(
                            f"promote '{ref.id}' profile_additions tries to overwrite "
                            f"existing field '{field_name}' (use canon_correction)"
                        )
                        continue
                    setattr(ent.profile, field_name, value)
            ent.importance = p.to_importance
            if ent.tracking_level == "continuity" and p.to_importance in (
                "supporting",
                "core",
            ):
                ent.tracking_level = "full"

        # identity_reveals: role_anchored → named (explicit, not merge) (§4.4 / §6.1)
        for r in ops.identity_reveals:
            ref = _resolve_ref(r.character, created_map)
            ent = _entity_by_id(canon, "character", ref.id)
            if ent.identity.kind != "role_anchored":
                errors.append(
                    f"identity_reveal '{ref.id}' requires role_anchored identity, "
                    f"got '{ent.identity.kind}'"
                )
                continue
            merged_aliases = [a for a in ent.identity.aliases if a]
            for a in r.add_aliases:
                if a not in merged_aliases:
                    merged_aliases.append(a)
            if r.display_name and r.display_name not in merged_aliases:
                merged_aliases.append(r.display_name)
            ent.identity = type(ent.identity)(
                kind="named",
                display_name=r.display_name,
                aliases=merged_aliases,
            )

    @staticmethod
    def _validate_character_create(c: Any, errors: list[str]) -> None:
        if c.identity is None or not getattr(c.identity, "display_name", ""):
            errors.append(f"character create '{c.creation_key}' missing identity")
        if c.importance not in IMPORTANCE_TIERS:
            errors.append(
                f"character create '{c.creation_key}' invalid importance '{c.importance}'"
            )
        if c.tracking_level not in ("full", "continuity"):
            errors.append(
                f"character create '{c.creation_key}' invalid tracking_level "
                f"'{c.tracking_level}'"
            )

    # -- collectives / locations -------------------------------------------

    def _apply_collectives(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.collectives
        for c in ops.create:
            if c.id is None:
                errors.append(f"collective create '{c.creation_key}' missing stable id")
                continue
            canon.collectives.append(
                Collective(
                    id=c.id,
                    kind=c.kind,
                    name=c.name,
                    function=c.function,
                    current_state=c.current_state,
                    stance_toward_characters=c.stance_toward_characters,
                    last_changed_by=None,
                )
            )
        for u in ops.state_updates:
            eid = u.id
            ent = _entity_by_id(canon, "collective", eid)
            # current_state only; immutable identity/constraints not patchable here.
            ent.current_state = u.current_state

    def _apply_locations(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.locations
        for c in ops.create:
            if c.id is None:
                errors.append(f"location create '{c.creation_key}' missing stable id")
                continue
            canon.locations.append(
                Location(
                    id=c.id,
                    name=c.name,
                    kind=c.kind,
                    parent_location=c.parent_location,
                    immutable_constraints=c.immutable_constraints,
                    current_state=c.current_state,
                    last_changed_by=None,
                )
            )
        for u in ops.state_updates:
            eid = u.id
            ent = _entity_by_id(canon, "location", eid)
            # Only current_state may change; immutable_constraints is correction-only (§6.1).
            if u.immutable_constraints:
                errors.append(
                    f"location '{eid}' immutable_constraints update forbidden in "
                    "normal patch (use canon_correction)"
                )
                continue
            # no-op guard: identical current_state is an empty update (§6.1)
            if u.current_state is not None and u.current_state == ent.current_state:
                errors.append(
                    f"location '{eid}' state update is a no-op (already "
                    f"'{ent.current_state}'); empty updates are rejected"
                )
                continue
            ent.current_state = u.current_state

    # -- artifacts ----------------------------------------------------------

    def _apply_artifacts(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.artifacts
        for c in ops.create:
            if c.id is None:
                errors.append(f"artifact create '{c.creation_key}' missing stable id")
                continue
            self._validate_custody(canon, c.custody, errors, f"artifact create '{c.creation_key}'")
            canon.artifacts.append(
                Artifact(
                    id=c.id,
                    name=c.name,
                    kind=c.kind,
                    properties=c.properties,
                    custody=c.custody,
                    condition=c.condition,
                    narrative_significance=c.narrative_significance,
                    last_changed_by=None,
                )
            )
        # custody_updates: custody only; kind/ref consistency (§6.1)
        for u in ops.custody_updates:
            eid = u.id
            ent = _entity_by_id(canon, "artifact", eid)
            if u.properties is not None:
                errors.append(
                    f"artifact '{eid}' custody_updates carries 'properties' — "
                    "property edits are correction-only (use canon_correction)"
                )
                continue
            if u.custody is not None:
                self._validate_custody(
                    canon, u.custody, errors, f"artifact '{eid}' custody"
                )
                ent.custody = u.custody
        for cu in ops.condition_updates:
            eid = cu.id
            ent = _entity_by_id(canon, "artifact", eid)
            ent.condition = cu.condition

    @staticmethod
    def _validate_custody(canon: Canon, custody: Any, errors: list[str], ctx: str) -> None:
        if custody is None:
            return
        kind = custody.kind if hasattr(custody, "kind") else (
            custody.get("kind") if isinstance(custody, dict) else None
        )
        cid = custody.id if hasattr(custody, "id") else (
            custody.get("id") if isinstance(custody, dict) else None
        )
        if not kind or not cid:
            errors.append(f"{ctx} custody must be {{kind, id}}")
            return
        if kind not in CUSTODY_KINDS:
            errors.append(
                f"{ctx} custody.kind must be one of {sorted(CUSTODY_KINDS)}, "
                f"got '{kind}'"
            )
            return
        if canon.get_entity(kind, cid) is None:
            errors.append(f"{ctx} custody references no {kind} entity '{cid}'")

    # -- knowledge ----------------------------------------------------------

    def _apply_knowledge(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
        scene_cast_ids: set[str],
    ) -> None:
        ops = patch.knowledge
        for c in ops.create:
            if c.id is None:
                errors.append(f"knowledge create '{c.creation_key}' missing stable id")
                continue
            if c.truth_status not in TRUTH_STATUSES:
                errors.append(
                    f"knowledge create '{c.creation_key}' invalid truth_status "
                    f"'{c.truth_status}'"
                )
            canon.knowledge.append(
                Knowledge(
                    id=c.id,
                    proposition=c.proposition,
                    truth_status=c.truth_status,
                    visibility=c.visibility,
                    holders=c.holders,
                    related_entity_refs=c.related_entity_refs,
                    last_changed_by=None,
                )
            )
        # holder_updates: holder must be scene cast or have explicit basis;
        # never auto-promote author truth to knows (§6.1)
        for hu in ops.holder_updates:
            ref = _resolve_ref(hu.knowledge, created_map)
            ent = _entity_by_id(canon, "knowledge", ref.id)
            holders_by_char = {h.holder.id: h for h in ent.holders}
            for upd in hu.holder_updates:
                holder = upd.holder
                hid = holder.id
                # The holder must be in the scene cast, OR an explicit
                # transmission/observation/inference basis must be declared.
                basis = upd.basis
                if hid not in scene_cast_ids and basis not in (
                    "transmission",
                    "observation",
                    "inference",
                ):
                    errors.append(
                        f"knowledge '{ref.id}' holder '{hid}' is not in scene cast "
                        "and has no explicit transmission/observation/inference basis"
                    )
                # POV leak guard: never auto-promote to 'knows' from author truth.
                new_state = upd.state
                if new_state == "knows":
                    prior_rec = holders_by_char.get(hid)
                    prior = prior_rec.state if prior_rec is not None else None
                    if (prior is None or prior == "unaware") and basis not in (
                        "transmission",
                        "observation",
                        "inference",
                    ):
                        errors.append(
                            f"knowledge '{ref.id}' cannot promote holder '{hid}' "
                            "to 'knows' without explicit basis (POV leak guard)"
                        )
                if new_state is not None and new_state not in KNOWLEDGE_STATES:
                    errors.append(
                        f"knowledge '{ref.id}' holder '{hid}' invalid state "
                        f"'{new_state}'"
                    )
            # apply holder changes
            holder_map = {h.holder.id: h for h in ent.holders}
            for upd in hu.holder_updates:
                hid = upd.holder.id
                rec = holder_map.get(hid)
                if rec is None:
                    rec = HolderState(holder=upd.holder, state="unaware")
                    ent.holders.append(rec)
                    holder_map[hid] = rec
                if upd.state is not None:
                    rec.state = upd.state
                if upd.basis is not None:
                    rec.basis = upd.basis

        # visibility_updates
        for vu in ops.visibility_updates:
            eid = vu.knowledge.id
            ent = _entity_by_id(canon, "knowledge", eid)
            ent.visibility = vu.visibility

        # truth_status_transitions: contested→confirmed/false_belief only (§6.1)
        for t in ops.truth_status_transitions:
            ref = _resolve_ref(t.knowledge, created_map)
            ent = _entity_by_id(canon, "knowledge", ref.id)
            if (ent.truth_status, t.to_status) not in TRUTH_TRANSITIONS:
                errors.append(
                    f"knowledge '{ref.id}' truth transition "
                    f"'{ent.truth_status}'→'{t.to_status}' not allowed in normal patch "
                    "(only contested→confirmed / contested→false_belief)"
                )
                continue
            ent.truth_status = t.to_status

    # -- chronology ---------------------------------------------------------

    def _apply_chronology(
        self,
        canon: Canon,
        patch: CanonPatch,
        errors: list[str],
    ) -> None:
        ops = patch.chronology
        if canon.chronology is None:
            if ops.advance_to is not None or ops.deadline_updates:
                errors.append("chronology patch present but Canon has no chronology")
            return
        if ops.advance_to is not None:
            adv = ops.advance_to
            cur = canon.chronology.current_marker
            if adv.ordinal <= cur.ordinal:
                errors.append(
                    f"chronology advance_to.ordinal ({adv.ordinal}) must be strictly "
                    f"greater than current marker ({cur.ordinal}); equal-ordinal label "
                    "change and rewind are rejected"
                )
            else:
                canon.chronology.current_marker = adv
        for du in ops.deadline_updates:
            eid = du.get("id")
            if eid is None:
                errors.append("chronology deadline_update missing id")
                continue
            found = None
            for d in canon.chronology.active_deadlines:
                if d.id == eid:
                    found = d
                    break
            if found is None:
                errors.append(f"chronology deadline '{eid}' not found")
                continue
            new_status = du.get("status")
            if new_status not in ("resolved", "missed"):
                errors.append(
                    f"chronology deadline '{eid}' may only go active→resolved/missed, "
                    f"got '{new_status}'"
                )
                continue
            found.status = new_status

    # -- relationships ------------------------------------------------------

    def _apply_relationships(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
        scene_cast_ids: set[str],
    ) -> None:
        ops = patch.relationships
        for c in ops.create:
            if c.id is None:
                errors.append(f"relationship create '{c.creation_key}' missing stable id")
                continue
            pids = sorted(set(c.participant_ids))
            if len(pids) != 2:
                errors.append(
                    f"relationship create '{c.creation_key}' must have exactly 2 distinct "
                    f"participants, got {len(pids)}"
                )
                continue
            # each participant exactly one perspective
            seen: set[str] = set()
            for p in c.perspectives:
                cid = p.character_id
                if cid in seen:
                    errors.append(
                        f"relationship create '{c.creation_key}' duplicate perspective for "
                        f"'{cid}'"
                    )
                seen.add(cid)
            if seen != set(pids):
                errors.append(
                    f"relationship create '{c.creation_key}' perspectives must cover exactly "
                    f"the 2 participants"
                )
            if not c.structural_bonds:
                errors.append(
                    f"relationship create '{c.creation_key}' requires a structural bond"
                )
            # participant entity existence
            for pid in pids:
                if canon.get_entity("character", pid) is None:
                    errors.append(
                        f"relationship create '{c.creation_key}' participant '{pid}' "
                        "is not a known character"
                    )
            canon.relationships.append(
                Relationship(
                    id=c.id,
                    participant_ids=pids,
                    structural_bonds=c.structural_bonds,
                    shared_state=c.shared_state,
                    perspectives=c.perspectives,
                    arc_summary="",
                    lifecycle="active",
                    last_changed_by=None,
                )
            )
        for u in ops.updates:
            ref = _resolve_ref(u.relationship, created_map)
            ent = _entity_by_id(canon, "relationship", ref.id)
            # at least one participant in scene cast (§6.1)
            if not (set(ent.participant_ids) & scene_cast_ids):
                errors.append(
                    f"relationship '{ref.id}' update rejected: no participant is in scene "
                    "cast (offstage effect forbidden)"
                )
                continue
            if u.shared_state is not None:
                ent.shared_state = u.shared_state
            for pu in u.perspective_updates:
                cid = pu.character_id
                if cid not in ent.participant_ids:
                    errors.append(
                        f"relationship '{ref.id}' perspective update for non-participant "
                        f"'{cid}'"
                    )
                    continue
                for rec in ent.perspectives:
                    if rec.character_id == cid:
                        for k, v in pu.model_dump(exclude_none=True).items():
                            if k != "character_id":
                                setattr(rec, k, v)
                        break
                else:
                    errors.append(
                        f"relationship '{ref.id}' has no perspective for '{cid}'"
                    )
            if u.arc_summary is not None:
                ent.arc_summary = u.arc_summary
            if u.lifecycle is not None:
                if ent.lifecycle != "active" or u.lifecycle != "resolved":
                    errors.append(
                        f"relationship '{ref.id}' lifecycle transition "
                        f"'{ent.lifecycle}'→'{u.lifecycle}' forbidden"
                    )
                else:
                    ent.lifecycle = u.lifecycle

    # -- foreshadowing / subplots / glossary --------------------------------

    def _apply_foreshadowing(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.foreshadowing
        for c in ops.create:
            if c.id is None:
                errors.append(
                    f"foreshadowing create '{c.creation_key}' has no stable id"
                )
                continue
            eid = c.id
            canon.foreshadowing.append(
                Foreshadowing(
                    id=eid,
                    description=c.description,
                    status="planted",
                    planted_by=None,
                    resolved_by=None,
                    intended_payoff=c.intended_payoff,
                    related_character_ids=[r.id for r in c.related_character_refs],
                    related_subplot_ids=[],
                    last_changed_by=None,
                )
            )
        for t in ops.transitions:
            ref = _resolve_ref(t.foreshadowing, created_map)
            ent = _entity_by_id(canon, "foreshadowing", ref.id)
            if ent.status != "planted":
                errors.append(
                    f"foreshadowing '{ref.id}' transition from '{ent.status}' forbidden "
                    "(only planted→resolved/abandoned in normal patch)"
                )
                continue
            if t.status not in ("resolved", "abandoned"):
                errors.append(
                    f"foreshadowing '{ref.id}' may only go planted→resolved/abandoned"
                )
                continue
            ent.status = t.status

    def _apply_subplots(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.subplots
        for c in ops.create:
            if c.id is None:
                errors.append(
                    f"subplot create '{c.creation_key}' has no stable id"
                )
                continue
            eid = c.id
            if not c.dramatic_question or not c.stakes:
                errors.append(
                    f"subplot create '{c.creation_key}' requires dramatic_question and stakes"
                )
                continue
            canon.subplots.append(
                Subplot(
                    id=eid,
                    name=c.name,
                    status="active",
                    dramatic_question=c.dramatic_question,
                    stakes=c.stakes,
                    current_state=c.current_state,
                    related_character_ids=[],
                    related_foreshadowing_ids=[],
                    last_changed_by=None,
                )
            )
        for u in ops.updates:
            ref = _resolve_ref(u.subplot, created_map)
            ent = _entity_by_id(canon, "subplot", ref.id)
            if u.current_state is not None:
                ent.current_state = u.current_state
            if u.status is not None:
                if ent.status != "active":
                    errors.append(
                        f"subplot '{ref.id}' status transition '{ent.status}'→'{u.status}' forbidden"
                    )
                else:
                    ent.status = u.status

    def _apply_glossary(
        self,
        canon: Canon,
        patch: CanonPatch,
        created_map: dict[str, str],
        errors: list[str],
    ) -> None:
        ops = patch.glossary
        for c in ops.create:
            if c.id is None:
                errors.append(
                    f"glossary create '{c.creation_key}' has no stable id"
                )
                continue
            eid = c.id
            canon.glossary.append(
                Glossary(
                    id=eid,
                    term=c.term,
                    definition=c.definition,
                )
            )


def _empty_profile() -> Any:
    """Build an all-None CharacterProfile (so promote can fill null fields)."""
    from novel_forge.canon.models import CharacterProfile

    return CharacterProfile(
        personality=None,
        motivation=None,
        appearance=None,
        background=None,
        arc=None,
        flaw=None,
    )
