"""CanonEventStore, BibleFactory, replay & fault recovery (§7, §8).

Storage layout (§8)::

    series/
      bible_seed.json      # v2 Plan Seed (source of truth)
      canon_events.jsonl   # active Canon Event set (source of truth)
      bible.json           # materialized Canon view (cache, regenerable)

`bible.json` is always derivable from ``bible_seed.json`` + active
``canon_events.jsonl`` via :meth:`CanonEventStore.replay`.  Digest mismatch at
startup triggers automatic regeneration (:meth:`CanonEventStore.recover`).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Canon,
    CanonEvent,
    CanonPatch,
    EntityRef,
    EventRef,
    SourceRef,
    compute_canonical_digest,
)
from novel_forge.canon.patch_apply import CanonPatchApplier
from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.canon.store")


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------


def atomic_write_json(path: Path, data: Any) -> None:
    """Serialize ``data`` to ``path`` atomically (temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            with contextlib.suppress(OSError):
                os.unlink(tmp)


# ---------------------------------------------------------------------------
# Patch application (replay step) — delegates to the canonical applier.
# ---------------------------------------------------------------------------


def apply_patch(canon: Canon, patch: CanonPatch, event: CanonEvent) -> Canon:
    """Apply one reviewed CanonPatch to a Canon, returning the new Canon.

    Delegates to :class:`CanonPatchApplier` (the single source of truth for
    §6.1 patch semantics) so replay and live application cannot diverge.
    """
    applier = CanonPatchApplier()
    new_canon, applied_event = applier.apply(
        canon=canon,
        patch=patch,
        source=event.source,
        review_evidence=event.review_evidence,
        id_gen=StableIdGenerator(),
        scene_cast_ids=set(event.scene_cast_ids),
        existing_events=[event],
    )
    _apply_provenance(new_canon, patch, event, applied_event.created_entity_ids)
    return new_canon


def _apply_provenance(
    canon: Canon,
    patch: CanonPatch,
    event: CanonEvent,
    created_entity_ids: dict[str, str],
) -> None:
    """Attach the structured EventRef to every entity mutated by the event."""
    ref = EventRef(scene_id=event.source.scene_id, event_digest=event.artifact_digest)
    changed: list[tuple[str, str]] = []
    for key, entity_id in created_entity_ids.items():
        kind = key.split(":", 1)[0]
        changed.append((kind, entity_id))
    def existing_id(value: Any) -> str | None:
        return getattr(value, "id", None)

    changed.extend(("character", eid) for u in patch.characters.state_updates if (eid := existing_id(u.character)))
    changed.extend(("character", eid) for u in patch.characters.promote if (eid := existing_id(u.character)))
    changed.extend(("character", eid) for u in patch.characters.identity_reveals if (eid := existing_id(u.character)))
    changed.extend(("collective", u.id) for u in patch.collectives.state_updates)
    changed.extend(("location", u.id) for u in patch.locations.state_updates)
    changed.extend(("artifact", u.id) for u in patch.artifacts.custody_updates)
    changed.extend(("artifact", u.id) for u in patch.artifacts.condition_updates)
    changed.extend(("relationship", eid) for u in patch.relationships.updates if (eid := existing_id(u.relationship)))
    changed.extend(("foreshadowing", eid) for u in patch.foreshadowing.transitions if (eid := existing_id(u.foreshadowing)))
    changed.extend(("subplot", eid) for u in patch.subplots.updates if (eid := existing_id(u.subplot)))
    for kind, entity_id in changed:
        entity: Any = canon.get_entity(kind, entity_id)
        if entity is not None and hasattr(entity, "last_changed_by"):
            entity.last_changed_by = ref
        if kind == "foreshadowing" and entity is not None:
            if entity.status == "planted":
                entity.planted_by = ref
            elif entity.status in {"resolved", "abandoned"}:
                entity.resolved_by = ref


def _to_event_ref(event: CanonEvent):
    return {"scene_id": event.source.scene_id, "event_digest": event.artifact_digest}


# ---------------------------------------------------------------------------
# BibleFactory
# ---------------------------------------------------------------------------


class BibleFactory:
    """Assemble the initial Canon (Plan Seed) from plan data (§7.4 / Phase 2)."""

    @staticmethod
    def create_seed(plan_data: dict) -> Canon:
        """Build a Canon from a `series_plan.json` structure.

        The plan seed is the single source of truth (SSOT) for Core / initial
        Supporting / initial Collective / Location / Artifact / Knowledge /
        Chronology / Relationship Arc / WorldRule / Glossary.
        """
        series_in = plan_data.get("series") or plan_data
        series = {
            "id": series_in.get("id", "series"),
            "title": series_in.get("title", ""),
            "logline": series_in.get("logline", ""),
            "genres": series_in.get("genres", series_in.get("genre", [])),
            "target_audience": series_in.get("target_audience", ""),
            "themes": series_in.get("themes", []),
            "tone": series_in.get("tone", ""),
            "selling_points": series_in.get("selling_points", []),
            "constraints": series_in.get("constraints", []),
        }

        def _with_id(lst, default_prefix):
            out = []
            for i, item in enumerate(lst, 1):
                if isinstance(item, str):
                    if default_prefix == "rule":
                        item = {"name": f"rule_{i:03d}", "statement": item}
                    elif default_prefix == "term":
                        item = {"term": item, "definition": ""}
                    else:
                        raise ValueError(f"{default_prefix} seed entries must be objects")
                item = dict(item)
                item.setdefault("id", f"{default_prefix}_{i:03d}")
                out.append(item)
            return out

        def _characters(raw_characters):
            normalized = []
            for i, raw in enumerate(raw_characters, 1):
                item = dict(raw)
                if "identity" not in item:
                    # Convert the public plan's legacy character shape exactly
                    # once, at immutable seed creation.
                    name = item.get("name", f"人物{i}")
                    item = {
                        "id": f"char_{i:03d}",
                        "identity": {"kind": "named", "display_name": name},
                        "importance": "core",
                        "tracking_level": "full",
                        "narrative_function": item.get("role", ""),
                        "profile": {
                            key: item[key]
                            for key in ("appearance", "personality", "motivation", "flaw", "age", "occupation", "background")
                            if item.get(key)
                        },
                        "continuity_card": {"current_state": item.get("state", "")},
                    }
                item.setdefault("id", f"char_{i:03d}")
                normalized.append(item)
            return normalized

        chronology = plan_data.get("chronology")
        if chronology is not None:
            chronology = {
                "current_marker": chronology.get(
                    "current_marker", {"ordinal": 0, "label": "開始"}
                ),
                "active_deadlines": _with_id(chronology.get("active_deadlines", []), "deadline"),
            }

        canon = Canon.model_validate({
            "schema_version": 2,
            "series": series,
            "characters": _characters(plan_data.get("characters") or plan_data.get("main_characters", [])),
            "collectives": _with_id(plan_data.get("collectives", []), "grp"),
            "locations": _with_id(plan_data.get("locations", []), "loc"),
            "artifacts": _with_id(plan_data.get("artifacts", []), "art"),
            "knowledge": _with_id(plan_data.get("knowledge", []), "know"),
            "world_rules": _with_id(plan_data.get("world_rules", []), "rule"),
            "glossary": _with_id(plan_data.get("glossary", []), "term"),
            "relationships": _with_id(plan_data.get("relationships", []), "rel"),
            "foreshadowing": _with_id(plan_data.get("foreshadowing", []), "fh"),
            "subplots": _with_id(plan_data.get("subplots", []), "sp"),
            "chronology": chronology,
        })
        return canon

    @staticmethod
    def write_seed(workdir: Path, canon: Canon) -> Path:
        workdir = Path(workdir)
        path = workdir / "bible_seed.json"
        atomic_write_json(path, canon.model_dump(mode="json", exclude_none=True))
        _log.info("wrote plan seed -> %s", path)
        return path


# ---------------------------------------------------------------------------
# CanonEventStore
# ---------------------------------------------------------------------------


class CanonEventStore:
    """Event-sourced Canon store (§7)."""

    def __init__(self, workdir: Path) -> None:
        self.workdir = Path(workdir)
        self.seed_path = self.workdir / "bible_seed.json"
        self.events_path = self.workdir / "canon_events.jsonl"
        self.bible_path = self.workdir / "bible.json"

    # ----- seed (immutable once events exist, §7.4) ----------------------
    def load_seed(self) -> Canon:
        if not self.seed_path.exists():
            raise FileNotFoundError(f"plan seed not found: {self.seed_path}")
        raw = self.seed_path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorruptedCanonError(f"plan seed JSON corrupt: {exc}") from exc
        return Canon.model_validate(data)

    def write_seed(self, canon: Canon) -> None:
        """Write the plan seed. Refuses if events already exist (§7.4)."""
        if self.events_path.exists() and self.events_path.stat().st_size > 0:
            raise SeedImmutableError(
                "plan seed is immutable once Canon Events exist; call "
                "reset_series_canon() first"
            )
        BibleFactory.write_seed(self.workdir, canon)

    # ----- events --------------------------------------------------------
    def load_active(self) -> list[CanonEvent]:
        """Load the active event set: latest revision per source (scene_id)."""
        if not self.events_path.exists():
            return []
        latest: dict[str, CanonEvent] = {}
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = CanonEvent.model_validate_json(line)
            except json.JSONDecodeError as exc:
                raise CorruptedCanonError(f"event JSON corrupt: {exc}") from exc
            except Exception as exc:  # pydantic validation -> schema violation
                raise SchemaViolationError(f"event schema violation: {exc}") from exc
            sid = ev.source.scene_id
            if sid not in latest or ev.source.revision > latest[sid].source.revision:
                latest[sid] = ev
        return list(latest.values())

    def save_events(self, events: list[CanonEvent]) -> None:
        """Atomically persist the full active event set (JSONL)."""
        lines = [ev.model_dump_json() for ev in events]
        # JSONL atomic write (temp + rename)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.workdir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                for ln in lines:
                    fh.write(ln)
                    fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.events_path)
        finally:
            if os.path.exists(tmp):
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
        _log.info("saved %d active events", len(events))

    def replace_source(self, source: SourceRef, events: list[CanonEvent]) -> None:
        """Backward-compatible single-source wrapper for the segment transaction."""
        self.replace_design_segment([source.scene_id], events)

    def replace_design_segment(
        self,
        removed_scene_ids: list[str],
        replacement_events: list[CanonEvent],
    ) -> Canon:
        """Atomically replace an ordered design segment and rematerialize Canon.

        The candidate active set is dependency-checked and replayed *before*
        replacing ``canon_events.jsonl``.  Thus a rejected replacement cannot
        leave a partial event set or a divergent ``bible.json`` behind.
        """
        if not removed_scene_ids:
            raise ValueError("replace_design_segment requires at least one source scene_id")
        removed = set(removed_scene_ids)
        if any(ev.source.scene_id not in removed for ev in replacement_events):
            raise ValueError("replacement events must belong to the replaced design segment")

        current = self.load_active()
        errors = self.validate_segment_replacement(
            removed_scene_ids=sorted(removed),
            replacement_events=replacement_events,
            events=current,
        )
        if errors:
            raise SegmentDependencyError("; ".join(errors))

        kept = [ev for ev in current if ev.source.scene_id not in removed]
        candidate = [*kept, *replacement_events]
        candidate.sort(
            key=lambda ev: (
                ev.source.location.volume,
                ev.source.location.chapter,
                ev.source.location.ordinal,
                ev.source.scene_id,
                ev.source.revision,
            )
        )

        # Same active source content is a true no-op: do not rewrite timestamps
        # or the event file merely because a caller retried the same request.
        active_by_source = {ev.source.scene_id: ev for ev in current}
        if (
            len(replacement_events) == len(removed)
            and all(
                sid in active_by_source
                and active_by_source[sid].model_dump(exclude={"created_at"})
                == next(ev for ev in replacement_events if ev.source.scene_id == sid).model_dump(exclude={"created_at"})
                for sid in removed
            )
        ):
            return self.recover()

        # Replay candidate first: invalid events never reach durable storage.
        canon = self.replay(self.load_seed(), candidate)
        self.save_events(candidate)
        self.materialize(canon)
        _log.info("replaced design segment %s (%d events)", sorted(removed), len(replacement_events))
        return canon

    # ----- replay --------------------------------------------------------
    def replay(self, seed: Canon | None = None, events: list[CanonEvent] | None = None) -> Canon:
        """Deterministically replay events onto the seed (§7.3 step 2)."""
        if seed is None:
            seed = self.load_seed()
        if events is None:
            events = self.load_active()
        # deterministic order: full source location, then scene_id and revision
        ordered = sorted(
            events,
            key=lambda e: (
                e.source.location.volume,
                e.source.location.chapter,
                e.source.location.ordinal,
                e.source.scene_id,
                e.source.revision,
            ),
        )
        canon = seed.model_copy(deep=True)
        for ev in ordered:
            self._validate_event_integrity(ev)
            canon = apply_patch(canon, ev.patch, ev)
        self._validate_references(canon, ordered)
        return canon

    # ----- materialized view --------------------------------------------
    def materialize(self, canon: Canon) -> Path:
        atomic_write_json(self.bible_path, canon.model_dump(mode="json", exclude_none=True))
        _log.info("materialized bible.json (digest=%s)", compute_canonical_digest(canon))
        return self.bible_path

    # ----- recovery (§7.3 step 4/5) --------------------------------------
    def recover(self) -> Canon:
        """Regenerate the materialized view if its digest mismatches replay.

        Raises a hard :class:`CanonStoreError` only for corruption, schema
        violation, reference inconsistency, or review-evidence mismatch.
        """
        seed = self.load_seed()
        events = self.load_active()
        canon = self.replay(seed, events)
        digest = compute_canonical_digest(canon)

        if self.bible_path.exists():
            try:
                stored = Canon.model_validate_json(
                    self.bible_path.read_text(encoding="utf-8")
                )
            except Exception as exc:
                # The materialized file is a cache, not a source of truth.  A
                # valid seed + event set must recover it automatically.
                _log.warning("bible.json invalid; regenerating materialized cache: %s", exc)
                self.materialize(canon)
                return canon
            if compute_canonical_digest(stored) != digest:
                _log.warning("bible.json digest mismatch; regenerating")
                self.materialize(canon)
        else:
            self.materialize(canon)
        return canon

    # ----- integrity checks ---------------------------------------------
    def _validate_event_integrity(self, ev: CanonEvent) -> None:
        if ev.review_evidence.status != "approved":
            raise ReviewEvidenceMismatchError(
                f"event {ev.event_id}: Canon Events require approved review evidence"
            )
        if not ev.artifact_digest or not ev.review_evidence.reviewed_artifact_digest:
            raise ReviewEvidenceMismatchError(
                f"event {ev.event_id}: artifact_digest and reviewed_artifact_digest "
                f"must be set (the reviewed SceneDesign artifact digest, §6.3 / §7.1)"
            )
        if ev.review_evidence.reviewed_artifact_digest != ev.artifact_digest:
            raise ReviewEvidenceMismatchError(
                f"event {ev.event_id}: reviewed_artifact_digest != artifact_digest"
            )

    def _validate_references(self, canon: Canon, events: list[CanonEvent]) -> None:
        valid = canon.all_ids()
        for ev in events:
            refs = self._patch_refs(ev.patch)
            for r in refs:
                if r.id not in valid:
                    raise ReferenceInconsistencyError(
                        f"event {ev.event_id} references missing entity {r.id}"
                    )
                if canon.get_entity(r.kind, r.id) is None:
                    raise ReferenceInconsistencyError(
                        f"event {ev.event_id} has typed reference kind mismatch: "
                        f"{r.kind}:{r.id}"
                    )

    @staticmethod
    def _patch_refs(patch: CanonPatch) -> list[EntityRef]:
        from novel_forge.canon.models import find_refs

        refs: list[EntityRef] = []
        for ops in [
            patch.characters,
            patch.collectives,
            patch.locations,
            patch.artifacts,
            patch.knowledge,
            patch.relationships,
            patch.foreshadowing,
            patch.subplots,
            patch.glossary,
        ]:
            refs.extend(find_refs(ops.model_dump(mode="json", exclude_none=True)))
        for u in patch.artifacts.custody_updates:
            uu = cast(Any, u)
            cid = uu.id if hasattr(uu, "id") else uu.get("id")
            if cid:
                refs.append(EntityRef(kind="artifact", id=cid))
        for cu in patch.artifacts.condition_updates:
            uu = cast(Any, cu)
            cid = uu.id if hasattr(uu, "id") else uu.get("id")
            if cid:
                refs.append(EntityRef(kind="artifact", id=cid))
        if patch.chronology.advance_to is None:
            pass
        for dl_u in patch.chronology.deadline_updates:
            dl = dl_u.get("deadline") if isinstance(dl_u, dict) else getattr(dl_u, "deadline", None)
            if dl and dl.get("id"):
                refs.append(EntityRef(kind="deadline", id=dl["id"]))
        for rel in patch.relationships.create:
            refs.extend(EntityRef(kind="character", id=pid) for pid in rel.participant_ids)
        for fh in patch.foreshadowing.create:
            refs.extend(fh.related_character_refs)
        return refs

    # ----- dependency graph (§3.2 / §7.2) --------------------------------
    def build_dependency_graph(self, events: list[CanonEvent] | None = None) -> dict[str, list[str]]:
        """Map entity_id -> list of scene_ids that created/referenced it."""
        if events is None:
            events = self.load_active()
        graph: dict[str, list[str]] = defaultdict(list)
        for ev in events:
            sid = ev.source.scene_id
            for eid in ev.created_entity_ids.values():
                graph.setdefault(eid, [])
                if sid not in graph[eid]:
                    graph[eid].append(sid)
            for r in self._patch_refs(ev.patch):
                graph.setdefault(r.id, [])
                if sid not in graph[r.id]:
                    graph[r.id].append(sid)
        return dict(graph)

    def validate_segment_replacement(
        self,
        removed_scene_ids: list[str],
        replacement_events: list[CanonEvent],
        events: list[CanonEvent] | None = None,
    ) -> list[str]:
        """Reject if a removed source's created entities are still referenced.

        Returns a list of error strings (empty == accepted), per §3.2 / §7.2.
        """
        if events is None:
            events = self.load_active()

        # entities created by removed scenes
        removed_created: set[str] = set()
        for ev in events:
            if ev.source.scene_id in removed_scene_ids:
                removed_created.update(ev.created_entity_ids.values())

        if not removed_created:
            return []

        # which entities survive (replacement + remaining events)
        surviving_ids: set[str] = set()
        for ev in replacement_events:
            surviving_ids.update(ev.created_entity_ids.values())
        for ev in events:
            if ev.source.scene_id in removed_scene_ids:
                continue
            surviving_ids.update(ev.created_entity_ids.values())

        # any surviving event that references a removed-created entity?
        errors: list[str] = []
        for ev in events:
            if ev.source.scene_id in removed_scene_ids:
                continue
            for r in self._patch_refs(ev.patch):
                if r.id in removed_created and r.id not in surviving_ids:
                    errors.append(
                        f"scene {ev.source.scene_id} references entity {r.id} "
                        f"created by a removed scene"
                    )
        return errors

    # ----- reset (§7.4) --------------------------------------------------
    def reset_series_canon(self) -> None:
        """Discard all events; plan seed again becomes mutable."""
        if self.events_path.exists():
            self.events_path.unlink()
        if self.bible_path.exists():
            self.bible_path.unlink()
        _log.warning("series canon reset: all events discarded")


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class CanonStoreError(Exception):
    """Base class for hard storage errors."""


class CorruptedCanonError(CanonStoreError):
    """JSON corruption — hard stop."""


class SchemaViolationError(CanonStoreError):
    """Pydantic / schema violation — hard stop."""


class ReferenceInconsistencyError(CanonStoreError):
    """Dangling reference after replay — hard stop."""


class SegmentDependencyError(CanonStoreError):
    """A segment replacement would orphan entities used by surviving scenes."""


class ReviewEvidenceMismatchError(CanonStoreError):
    """reviewed_artifact_digest != artifact_digest — hard stop."""


class SeedImmutableError(CanonStoreError):
    """Attempted to rewrite the plan seed while events exist."""
