"""Pure replay of selected, immutable Canon artifact payloads.

A Canon projection is derived solely from an immutable ``canon.seed`` payload
and its selected ``canon.frontier`` event-set payload.  This module deliberately
has no artifact lookup or filesystem concerns; callers must supply already
verified payloads from Runtime Artifact Retention.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from novel_forge.canon.models import Canon, CanonEvent, PatchValidationError, find_refs
from novel_forge.canon.store import apply_patch

__all__ = [
    "FrontierPayloadError",
    "SeedPayloadError",
    "replay_frontier",
    "validate_frontier_payload",
    "validate_seed_payload",
]


class SeedPayloadError(ValueError):
    """Raised when an immutable ``canon.seed`` artifact payload is invalid."""


class FrontierPayloadError(ValueError):
    """Raised when an immutable ``canon.frontier`` artifact payload is invalid."""


def validate_seed_payload(payload: Mapping[str, Any]) -> Canon:
    """Validate an artifact seed payload into a fresh ``Canon`` instance."""
    if not isinstance(payload, Mapping):
        raise SeedPayloadError("Canon seed payload must be an object")
    try:
        return Canon.model_validate(payload)
    except (ValidationError, ValueError, TypeError) as exc:
        raise SeedPayloadError(f"invalid Canon seed payload: {exc}") from exc


def validate_frontier_payload(payload: Mapping[str, Any]) -> tuple[CanonEvent, ...]:
    """Validate the exact ``{'events': [...]}`` frontier artifact shape."""
    if not isinstance(payload, Mapping):
        raise FrontierPayloadError("Canon frontier payload must be an object")
    if set(payload) != {"events"}:
        raise FrontierPayloadError("Canon frontier payload must contain only an 'events' field")
    raw_events = payload["events"]
    if not isinstance(raw_events, list):
        raise FrontierPayloadError("Canon frontier payload 'events' must be a list")

    events: list[CanonEvent] = []
    seen_sources: set[tuple[str, int]] = set()
    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, Mapping):
            raise FrontierPayloadError(f"frontier event payload at index {index} must be an object")
        try:
            event = CanonEvent.model_validate(raw_event)
        except (ValidationError, ValueError, TypeError) as exc:
            raise FrontierPayloadError(
                f"invalid frontier event payload at index {index}: {exc}"
            ) from exc
        _validate_event_integrity(event)
        # P0-2: at most one active event per (scene_id, revision)
        source_key = (event.source.scene_id, event.source.revision)
        if source_key in seen_sources:
            raise FrontierPayloadError(
                f"frontier has duplicate active source "
                f"{event.source.scene_id} revision {event.source.revision}"
            )
        seen_sources.add(source_key)
        events.append(event)
    return tuple(events)


def replay_frontier(
    seed_payload: Mapping[str, Any], frontier_payload: Mapping[str, Any]
) -> Canon:
    """Replay a selected frontier onto its seed without mutating either payload.

    Events are ordered by their complete source location and identity, rather
    than by scene ordinal alone, so independently numbered chapters and volumes
    replay in their intended chronological order.
    """
    seed = validate_seed_payload(seed_payload)
    events = validate_frontier_payload(frontier_payload)
    ordered = sorted(
        events,
        key=lambda event: (
            event.source.location.volume,
            event.source.location.chapter,
            event.source.location.ordinal,
            event.source.scene_id,
            event.source.revision,
        ),
    )

    canon = seed.model_copy(deep=True)
    created_ids: set[str] = set(canon.all_ids())
    for event in ordered:
        try:
            canon = apply_patch(canon, event.patch, event)
        except (PatchValidationError, ValidationError, ValueError) as exc:
            raise FrontierPayloadError(
                f"event {event.event_id} patch rejected during replay: {exc}"
            ) from exc
        # P0-1: created_entity_ids must not collide with any prior entity
        for eid in event.created_entity_ids.values():
            if eid in created_ids:
                raise FrontierPayloadError(
                    f"event {event.event_id} created_entity_ids collision: "
                    f"id '{eid}' already exists in canon"
                )
            created_ids.add(eid)
        # P0-3: references must resolve against the canon built so far
        _validate_event_references_resolve(canon, event)
    _validate_typed_references(canon, ordered)
    return canon


def _validate_event_references_resolve(canon: Canon, event: CanonEvent) -> None:
    """Reject a reference whose entity is not present in the canon built up to
    and including this event (P0-3: no forward/dangling references)."""
    for ref in find_refs(event.patch.model_dump(mode="json", exclude_none=True)):
        if canon.get_entity(ref.kind, ref.id) is None:
            raise FrontierPayloadError(
                f"event {event.event_id} references missing entity "
                f"{ref.kind}:{ref.id} at its own replay point"
            )


def _validate_typed_references(canon: Canon, events: list[CanonEvent]) -> None:
    """Reject a reference whose ID exists only under a different entity kind."""
    all_ids = canon.all_ids()
    for event in events:
        refs = find_refs(event.patch.model_dump(mode="json", exclude_none=True))
        for ref in refs:
            if canon.get_entity(ref.kind, ref.id) is not None:
                continue
            if ref.id in all_ids:
                raise FrontierPayloadError(
                    f"event {event.event_id} has typed reference kind mismatch: "
                    f"{ref.kind}:{ref.id}"
                )
            raise FrontierPayloadError(
                f"event {event.event_id} references missing entity {ref.kind}:{ref.id}"
            )


def _validate_event_integrity(event: CanonEvent) -> None:
    if event.review_evidence.status != "approved":
        raise FrontierPayloadError(
            f"frontier event payload {event.event_id} requires approved review evidence"
        )
    if event.review_evidence.reviewed_artifact_digest != event.artifact_digest:
        raise FrontierPayloadError(
            f"frontier event payload {event.event_id} has mismatched reviewed artifact digest"
        )
