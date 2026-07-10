"""CanonSliceBuilder — deterministic LLM projection (§6.2).

Given a stage, a typed ``ContextScope`` and the current ``Canon``, the builder
produces a ``Projection`` containing:

* ``scope_manifest`` — roots, included entity refs, omitted optional count
* ``author_context`` — what design / patch review may read (incl. author-only
  Knowledge truth + holder matrix)
* ``pov_safe_context`` — what the writer may receive (no stable IDs, no event
  digests, no author-only truth leaks)

Selection priority (§6.2 table):

* **P0 invariant** — always included, never dropped by budget:
  series constraints, scope-relevant world rules, POV/cast identity +
  current_state, setting immutable_constraints, scope-relevant active
  deadlines, scope-relevant POV knowledge.
* **P1 causal** — relationship arcs among cast, affiliations (collectives),
  scope artifacts/knowledge, related active subplots / unresolved
  foreshadowing, recent scene outcome. Compact form.
* **P2 optional** — weakly related minor characters, parent location, past arc
  summaries, auxiliary glossary. Dropped only by deterministic rank when over
  budget.

Scope closure is performed purely over the ID graph (no string search / name
similarity), seeded from ``scope.required_refs`` + roots.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from novel_forge.canon.models import (
    Canon,
    ContextScope,
    EntityKind,
    EntityRef,
    compute_canonical_digest,
)
from novel_forge.logging_config import get_logger

_log = get_logger("novel_forge.canon.slice")


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


@dataclass
class Projection:
    projection_version: int = 1
    canon_digest: str = ""
    stage: str = ""
    scope_manifest: dict[str, Any] = field(default_factory=dict)
    author_context: dict[str, Any] = field(default_factory=dict)
    pov_safe_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "projection_version": self.projection_version,
            "canon_digest": self.canon_digest,
            "stage": self.stage,
            "scope_manifest": self.scope_manifest,
            "author_context": self.author_context,
            "pov_safe_context": self.pov_safe_context,
        }


# entity kinds whose "current_state" summary must not be dropped
STATE_KINDS = {"character", "location", "artifact", "collective", "relationship"}


def _ref(kind: EntityKind, eid: str) -> EntityRef:
    return EntityRef(kind=kind, id=eid)


def _ref_key(r: EntityRef) -> tuple[str, str]:
    return (r.kind, r.id)


class CanonSliceBuilder:
    # Class-level cache of the active scope's (kind, id) set, populated at the
    # start of each ``build()`` call so helper methods (e.g. ``_is_pov_knowledge``)
    # can refer to it without threading the scope through every call.
    _scope_ids_cache: ClassVar[set[tuple[str, str]]] = set()
    """Build deterministic projections from a Canon + ContextScope."""

    def __init__(self) -> None:
        # outgoing edges per entity (kind,id) -> list of (kind,id)
        self._edges: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)

    # ----- ID-graph closure (§5.1) --------------------------------------
    def _scan_graph(self, canon: Canon) -> None:
        self._edges = defaultdict(set)

        def link(a: tuple[str, str], b: tuple[str, str]) -> None:
            self._edges[a].add(b)

        for ch in canon.characters:
            a = ("character", ch.id)
            if ch.continuity_card.current_location:
                link(a, _ref_key(ch.continuity_card.current_location))
            for aff in ch.affiliations:
                link(a, ("collective", aff.collective.id))
        for loc in canon.locations:
            if loc.parent_location:
                link(("location", loc.id), _ref_key(loc.parent_location))
        for art in canon.artifacts:
            if art.custody:
                link(("artifact", art.id), (art.custody.kind, art.custody.id))
        for kn in canon.knowledge:
            for ref in kn.related_entity_refs:
                link(("knowledge", kn.id), _ref_key(ref))
            for h in kn.holders:
                link(("knowledge", kn.id), _ref_key(h.holder))
        for rel in canon.relationships:
            for pid in rel.participant_ids:
                link(("relationship", rel.id), ("character", pid))
        for fh in canon.foreshadowing:
            for cid in fh.related_character_ids:
                link(("foreshadowing", fh.id), ("character", cid))
            for sid in fh.related_subplot_ids:
                link(("foreshadowing", fh.id), ("subplot", sid))
        for sp in canon.subplots:
            for cid in sp.related_character_ids:
                link(("subplot", sp.id), ("character", cid))
            for fid in sp.related_foreshadowing_ids:
                link(("subplot", sp.id), ("foreshadowing", fid))

    def _closure(self, roots: list[EntityRef]) -> set[tuple[str, str]]:
        seen: set[tuple[str, str]] = set()
        stack = [_ref_key(r) for r in roots]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            for nxt in self._edges.get(node, ()):
                if nxt not in seen:
                    stack.append(nxt)
        return seen

    # ----- helpers -------------------------------------------------------
    @staticmethod
    def _scope_ids(scope: ContextScope) -> set[tuple[str, str]]:
        ids: set[tuple[str, str]] = set()
        if scope.pov_character is not None:
            ids.add(("character", scope.pov_character.id))
        if scope.setting is not None:
            ids.add(("location", scope.setting.id))
        for r in scope.required_refs:
            ids.add(_ref_key(r))
        return ids

    def _entity_obj(self, canon: Canon, kind: str, eid: str) -> Any | None:
        return canon.get_entity(kind, eid)

    @classmethod
    def _is_pov_knowledge(cls, canon: Canon, kn, pov_id: str) -> bool:
        for h in kn.holders:
            if h.holder.id == pov_id:
                return True
        return ("knowledge", kn.id) in cls._scope_ids_cache

    # ----- build ---------------------------------------------------------
    def build(
        self,
        stage: str,
        scope: ContextScope,
        canon: Canon,
        budget: int = 8000,
    ) -> Projection:
        self._scan_graph(canon)
        if scope.pov_character is None or scope.setting is None:
            raise ValueError("ContextScope requires pov_character and setting")
        pov_id = scope.pov_character.id
        self.__class__._scope_ids_cache = self._scope_ids(scope)

        roots: list[EntityRef] = [
            scope.pov_character,
            scope.setting,
            *scope.required_refs,
        ]
        closed = self._closure(roots)

        # Partition entities into P0 / P1 / P2 with a deterministic rank key.
        p0: list[tuple] = []
        p1: list[tuple] = []
        p2: list[tuple] = []

        # --- P0: invariants ---
        # series constraints
        for c in canon.series.constraints:
            p0.append(("series_constraint", c.id, None, c.statement))
        # scope-relevant world rules
        for wr in canon.world_rules:
            p0.append(("world_rule", wr.id, None, wr.statement))
        # POV/cast identity + current_state
        for ch in canon.characters:
            if ("character", ch.id) in closed:
                p0.append(("character", ch.id, ch.identity.display_name, ch.continuity_card.current_state))
        # setting immutable constraints + current_state
        for loc in canon.locations:
            if ("location", loc.id) in closed:
                p0.append(("location", loc.id, loc.name, loc.immutable_constraints))
        # scope-relevant active deadlines
        if canon.chronology:
            for d in canon.chronology.active_deadlines:
                if ("deadline", d.id) in closed:
                    p0.append(("deadline", d.id, d.statement, d.due_marker.label))
        # scope-relevant POV knowledge
        for kn in canon.knowledge:
            if ("knowledge", kn.id) in closed and self._is_pov_knowledge(canon, kn, pov_id):
                p0.append(("knowledge", kn.id, kn.proposition, kn.truth_status))

        # --- P1: causal ---
        # relationship arcs among cast
        for rel in canon.relationships:
            if ("relationship", rel.id) in closed and rel.lifecycle == "active":
                p1.append(("relationship", rel.id, rel.participant_ids, rel.arc_summary))
        # collectives (affiliations)
        for grp in canon.collectives:
            if ("collective", grp.id) in closed:
                p1.append(("collective", grp.id, grp.name, grp.current_state))
        # scope artifacts / knowledge (already captured pov knowledge in P0;
        # non-pov but scope-relevant knowledge goes P1)
        for art in canon.artifacts:
            if ("artifact", art.id) in closed:
                p1.append(("artifact", art.id, art.name, art.condition))
        for kn in canon.knowledge:
            if ("knowledge", kn.id) in closed and not self._is_pov_knowledge(canon, kn, pov_id):
                p1.append(("knowledge", kn.id, kn.proposition, kn.visibility))
        # related active subplots / unresolved foreshadowing
        for sp in canon.subplots:
            if ("subplot", sp.id) in closed and sp.status == "active":
                p1.append(("subplot", sp.id, sp.name, sp.current_state))
        for fh in canon.foreshadowing:
            if ("foreshadowing", fh.id) in closed and fh.status == "planted":
                p1.append(("foreshadowing", fh.id, fh.description, fh.intended_payoff))

        # --- P2: optional (weakly related) ---
        for ch in canon.characters:
            if ch.importance == "minor" and ("character", ch.id) not in closed:
                p2.append(("character", ch.id, ch.identity.display_name, "minor"))
        for loc in canon.locations:
            # parent locations of included locations
            if ("location", loc.id) not in closed:
                for incl in closed:
                    if incl[0] == "location":
                        inc_loc = self._entity_obj(canon, "location", incl[1])
                        if inc_loc and inc_loc.parent_location and inc_loc.parent_location.id == loc.id:
                            p2.append(("location", loc.id, loc.name, "parent"))
                            break
        for term in canon.glossary:
            p2.append(("glossary", term.id, term.term, term.definition))

        # P0 is never dropped. P1 kept fully in this implementation (compact
        # form). P2 may be dropped by deterministic rank when over budget.
        selected: list[tuple] = list(p0) + list(p1)

        def rank_key(item: tuple) -> tuple:
            kind, eid, *_ = item
            # explicit ref (in scope) > direct relation (in closure) >
            # recency (id seq) > id string
            in_scope = (kind, eid) in self.__class__._scope_ids_cache
            in_closed = (kind, eid) in closed
            seq = parse_seq_local(eid)
            return (0 if in_scope else (1 if in_closed else 2), -seq, eid)

        p2_sorted = sorted(p2, key=rank_key)

        used = sum(entity_size_approx(i) for i in selected)
        omitted = 0
        for item in p2_sorted:
            size = entity_size_approx(item)
            if used + size <= budget:
                selected.append(item)
                used += size
            else:
                omitted += 1

        # Build included manifest
        included_refs = []
        for item in selected:
            kind, eid, *_ = item
            included_refs.append({"kind": kind, "id": eid})

        # Bind the projection to the complete Canon, not a selected subset.  The
        # subset controls prompt budget, while the full digest makes any Canon
        # mutation invalidate author-context/review evidence as required by §6.
        digest = compute_canonical_digest(canon)

        projection = Projection(
            projection_version=1,
            canon_digest=digest,
            stage=stage,
            scope_manifest={
                "roots": [r.model_dump(mode="json") for r in roots],
                "included": included_refs,
                "omitted_optional_count": omitted,
            },
            author_context=self._author_context(canon, selected, pov_id),
            pov_safe_context=self._pov_safe_context(canon, selected, pov_id),
        )
        return projection

    # ----- context builders ---------------------------------------------
    def _collect_entities(self, canon: Canon, selected: list[tuple]) -> dict[str, set[str]]:
        by_kind: dict[str, set[str]] = defaultdict(set)
        for item in selected:
            kind, eid, *_ = item
            by_kind[kind].add(eid)
        return by_kind

    def _subset_canon(self, canon: Canon, by_kind: dict[str, set[str]]) -> Canon:
        data = canon.model_dump(mode="json", exclude_none=True)
        for kind, ids in by_kind.items():
            if kind == "series_constraint":
                data["series"]["constraints"] = [
                    c for c in data["series"].get("constraints", []) if c["id"] in ids
                ]
                continue
            if kind == "world_rule":
                data["world_rules"] = [w for w in data.get("world_rules", []) if w["id"] in ids]
                continue
            if kind == "deadline":
                if "chronology" in data and data["chronology"]:
                    data["chronology"]["active_deadlines"] = [
                        d for d in data["chronology"].get("active_deadlines", []) if d["id"] in ids
                    ]
                continue
            list_name = {
                "character": "characters",
                "collective": "collectives",
                "location": "locations",
                "artifact": "artifacts",
                "knowledge": "knowledge",
                "relationship": "relationships",
                "foreshadowing": "foreshadowing",
                "subplot": "subplots",
                "glossary": "glossary",
            }[kind]
            if list_name in data:
                data[list_name] = [e for e in data[list_name] if e["id"] in ids]
        return Canon.model_validate(data)

    def _author_context(self, canon: Canon, selected: list[tuple], pov_id: str) -> dict[str, Any]:
        by_kind = self._collect_entities(canon, selected)
        ctx: dict[str, Any] = {}
        if "knowledge" in by_kind:
            # include proposition + holder matrix (author-only truth)
            ctx["knowledge"] = [
                {
                    "proposition": kn.proposition,
                    "truth_status": kn.truth_status,
                    "visibility": kn.visibility,
                    "holders": kn.holders,
                }
                for kn in canon.knowledge
                if kn.id in by_kind["knowledge"]
            ]
        if "relationship" in by_kind:
            ctx["relationships"] = [
                {
                    "participant_ids": rel.participant_ids,
                    "shared_state": rel.shared_state,
                    "perspectives": rel.perspectives,
                    "arc_summary": rel.arc_summary,
                }
                for rel in canon.relationships
                if rel.id in by_kind["relationship"]
            ]
        # pov character identity + full current state
        if "character" in by_kind:
            ctx["characters"] = [
                {
                    "identity": ch.identity.model_dump(mode="json", exclude_none=True),
                    "continuity_card": ch.continuity_card.model_dump(mode="json", exclude_none=True),
                    "affiliations": [a.model_dump(mode="json", exclude_none=True) for a in ch.affiliations],
                }
                for ch in canon.characters
                if ch.id in by_kind["character"]
            ]
        if "series_constraint" in by_kind:
            ctx["series_constraints"] = [
                constraint.statement for constraint in canon.series.constraints if constraint.id in by_kind["series_constraint"]
            ]
        if "world_rule" in by_kind:
            ctx["world_rules"] = [rule.statement for rule in canon.world_rules if rule.id in by_kind["world_rule"]]
        if "location" in by_kind:
            ctx["locations"] = [
                {"name": location.name, "immutable_constraints": location.immutable_constraints, "current_state": location.current_state}
                for location in canon.locations if location.id in by_kind["location"]
            ]
        if "artifact" in by_kind:
            ctx["artifacts"] = [
                {"name": artifact.name, "properties": artifact.properties, "condition": artifact.condition, "custody": artifact.custody}
                for artifact in canon.artifacts if artifact.id in by_kind["artifact"]
            ]
        if "deadline" in by_kind and canon.chronology:
            ctx["deadlines"] = [
                {"statement": deadline.statement, "due_marker": deadline.due_marker.label, "status": deadline.status}
                for deadline in canon.chronology.active_deadlines if deadline.id in by_kind["deadline"]
            ]
        if "glossary" in by_kind:
            ctx["glossary"] = [
                {"term": term.term, "definition": term.definition}
                for term in canon.glossary if term.id in by_kind["glossary"]
            ]
        return ctx

    def _pov_safe_context(self, canon: Canon, selected: list[tuple], pov_id: str) -> dict[str, Any]:
        """Writer projection: no stable IDs, no event digests, no author truth.

        §6.2 — expose observable constraints/state and guardrails, but never
        expose the secret proposition text of things the POV does not know.
        """
        by_kind = self._collect_entities(canon, selected)
        ctx: dict[str, Any] = {}

        # cast observable constraints
        cast = []
        for ch in canon.characters:
            if ch.id in by_kind.get("character", set()):
                cast.append(
                    {
                        "display_name": ch.identity.display_name,
                        "observable_state": ch.continuity_card.current_state,
                        "behavioral_constraint": ch.continuity_card.distinguishing_traits,
                    }
                )
        ctx["cast_constraints"] = cast

        # setting
        setting = []
        for loc in canon.locations:
            if loc.id in by_kind.get("location", set()):
                setting.append(
                    {
                        "name": loc.name,
                        "immutable_constraints": loc.immutable_constraints,
                        "current_state": loc.current_state,
                    }
                )
        ctx["setting_constraints"] = [s["immutable_constraints"] for s in setting if s["immutable_constraints"]]
        ctx["setting_state"] = [s["current_state"] for s in setting]

        # artifacts
        arts: list[dict[str, Any]] = []
        for art in canon.artifacts:
            if art.id in by_kind.get("artifact", set()):
                arts.append(
                    {
                        "name": art.name,
                        "properties": art.properties,
                        "condition": art.condition,
                        "custody": art.custody,
                    }
                )
        ctx["artifact_constraints"] = [a["properties"] for a in arts if a["properties"]]
        character_labels = {ch.id: ch.identity.display_name for ch in canon.characters}
        collective_labels = {grp.id: grp.name for grp in canon.collectives}
        location_labels = {loc.id: loc.name for loc in canon.locations}
        ctx["artifact_state"] = [
            f"{a['name']} は "
            f"{_custody_label(a['custody'], character_labels, collective_labels, location_labels)} が携行し、{a['condition']}"
            for a in arts
        ]

        # time constraints (deadlines)
        if canon.chronology:
            dl = [
                f"{d.statement}（期限: {d.due_marker.label}）"
                for d in canon.chronology.active_deadlines
                if d.id in by_kind.get("deadline", set())
            ]
            ctx["time_constraints"] = dl

        # guardrails: never leak secret author truths / stable IDs / digests
        ctx["unrevealed_guardrails"] = [
            "POVが観測・推論していない原因、他者の非公開動機、未開示の真相を断定しない",
        ]
        return ctx


def _custody_label(
    custody: Any | None,
    character_labels: dict[str, str],
    collective_labels: dict[str, str],
    location_labels: dict[str, str],
) -> str:
    """Resolve custody from the current Canon without exposing a stable ID."""
    if not custody:
        return "誰も"
    if custody.kind == "character":
        return character_labels.get(custody.id, "ある人物")
    if custody.kind == "collective":
        return collective_labels.get(custody.id, "ある組織")
    if custody.kind == "location":
        return location_labels.get(custody.id, "ある場所")
    return "誰か"


def parse_seq_local(eid: str) -> int:
    digits = "".join(ch for ch in reversed(eid) if ch.isdigit())
    return int(digits[::-1]) if digits else 0


def entity_size_approx(item: tuple) -> int:
    """Cheap size proxy (character count of the summary tuple)."""
    total = 0
    for part in item[2:]:
        if isinstance(part, str):
            total += len(part)
        elif isinstance(part, (list, dict)):
            total += len(json.dumps(part, ensure_ascii=False))
    return max(total, 32)
