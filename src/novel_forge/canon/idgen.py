"""Stable ID generation for new Canon entities (§3.3).

New entities are referenced inside a patch by a per-source-unique
``creation_key``.  The manager mints a stable ID at first application time as
``scene_id + creation_key`` and persists it in ``CanonEvent.created_entity_ids``.
A later revision of the same source reuses the same ID.
"""

from __future__ import annotations

from novel_forge.canon.models import (
    PATCH_CREATE_KIND,
    PREFIX_BY_KIND,
    Canon,
    CanonPatch,
    SourceRef,
    parse_seq,
)
from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.canon.idgen")


class StableIdGenerator:
    """Assign stable IDs to new entities declared in a CanonPatch."""

    def _max_seq_for_prefix(self, canon: Canon, prefix: str) -> int:
        max_seq = 0
        for eid in canon.all_ids():
            if eid.startswith(prefix + "_"):
                max_seq = max(max_seq, parse_seq(eid))
        return max_seq

    def _known_map(self, existing_events: list | None = None) -> dict[str, str]:
        """Map ``scene_id|kind|creation_key`` to stable ids from prior events."""
        known: dict[str, str] = {}
        if not existing_events:
            return known
        for ev in existing_events:
            scene_id = ev.source.scene_id
            for key, eid in (ev.created_entity_ids or {}).items():
                # Persisted keys are ``entitykind:creation_key``.  The entity
                # kind is part of identity: cross-kind reuse is never valid.
                if ":" not in key:
                    continue
                kind, ck = key.split(":", 1)
                known[f"{scene_id}|{kind}|{ck}"] = eid
        return known

    def assign(
        self,
        patch: CanonPatch,
        existing: Canon,
        source: SourceRef,
        existing_events: list | None = None,
    ) -> tuple[CanonPatch, dict[str, str]]:
        """Resolve a patch's creation payloads to stable IDs.

        Returns the patched patch (creation payloads carry their assigned
        ``id``) and a ``entitykind:creation_key -> id`` mapping.
        """
        known = self._known_map(existing_events)
        created: dict[str, str] = {}

        seen_creation_keys: set[str] = set()
        for field_name, kind in PATCH_CREATE_KIND.items():
            ops = getattr(patch, field_name)
            creates = getattr(ops, "create", [])
            prefix = PREFIX_BY_KIND[kind]
            next_seq = self._max_seq_for_prefix(existing, prefix) + 1
            for create in creates:
                ck = create.creation_key
                if ck in seen_creation_keys:
                    raise ValueError(
                        f"creation_key '{ck}' is duplicated in source {source.scene_id}; "
                        "creation keys are source-unique across entity kinds"
                    )
                seen_creation_keys.add(ck)
                cache_key = f"{source.scene_id}|{kind}|{ck}"
                if cache_key in known:
                    eid = known[cache_key]
                else:
                    eid = f"{prefix}_{next_seq:03d}"
                    next_seq += 1
                    known[cache_key] = eid
                # assign id onto the payload (so replay can persist it)
                object.__setattr__(create, "id", eid)
                created[f"{kind}:{ck}"] = eid
                _log.debug("assigned stable id %s for %s", eid, cache_key)

        return patch, created
