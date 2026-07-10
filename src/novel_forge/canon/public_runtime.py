"""Public NovelEngine adapters for the Series Bible v2 runtime.

This module is the only bridge between the public plan/design/write commands and
Canon v2.  It never imports v1 Bible, Blackboard, ContextBuilder, or SceneWriter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .design import CastEntry, ChapterDesign, ProjectionManifest, SceneDesign, VolumeDesign
from .models import (
    Canon,
    CastCharacter,
    CastLocalRole,
    ContextScope,
    DesignIntent,
    EntityRef,
    SceneLocation,
    WriterContext,
)
from .slice import CanonSliceBuilder, Projection
from .store import CanonEventStore


def _text_items(value: object) -> list[str]:
    """Flatten projection values while preserving only writer-safe text."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_text_items(item))
        return out
    return []

_STABLE_ID = re.compile(
    r"\b(?:char|loc|art|know|rel|fh|sp|grp|term|deadline|cev|scn|vol)_?[A-Za-z0-9_-]*\d+[A-Za-z0-9_-]*\b",
    re.IGNORECASE,
)
_FORBIDDEN_WRITER_MARKER = re.compile(r"\b(?:canon(?:_?(?:seed|digest|event|verse|bible))?|bible_seed|bible_mgr|bible_storage|event_log|event_store|sha256)\b", re.IGNORECASE)


def _safe_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"writer boundary rejected non-text {field}")
    if _STABLE_ID.search(value) or _FORBIDDEN_WRITER_MARKER.search(value):
        raise ValueError(f"writer boundary rejected forbidden reference in {field}")
    return value


def _safe_text_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"writer boundary rejected non-list {field}")
    return [_safe_text(item, field) for item in value]


def _writer_payload(scene: SceneDesign) -> dict[str, Any]:
    """Build the only serializable writer input from a persisted design.

    ``WriterContext`` deliberately has permissive internal types for projection
    construction.  The public writer never serializes it directly: this DTO
    rejects unknown keys, stable IDs, Canon/Bible/event markers, and all
    non-text leaves before a prompt is rendered.
    """
    wc = scene.writer_context
    if wc is None:
        raise ValueError(f"v2 SceneDesign {scene.scene_id} has no writer_context")
    pov = wc.pov
    if set(pov) != {"display_name"}:
        raise ValueError("writer boundary rejected unexpected POV fields")
    cast: list[dict[str, str]] = []
    for item in wc.cast_constraints:
        if not isinstance(item, dict) or set(item) - {"display_name", "observable_state", "behavioral_constraint"}:
            raise ValueError("writer boundary rejected unexpected cast fields")
        cast.append({key: _safe_text(item.get(key, ""), f"cast.{key}") for key in item})
    writer_context = {
        "pov": {"display_name": _safe_text(pov["display_name"], "pov.display_name")},
        "cast_constraints": cast,
        "setting_constraints": _safe_text_list(wc.setting_constraints, "setting_constraints"),
        "setting_state": _safe_text_list(wc.setting_state, "setting_state"),
        "artifact_constraints": _safe_text_list(wc.artifact_constraints, "artifact_constraints"),
        "artifact_state": _safe_text_list(wc.artifact_state, "artifact_state"),
        "time_constraints": _safe_text_list(wc.time_constraints, "time_constraints"),
        "required_story_beats": _safe_text_list(wc.required_story_beats, "required_story_beats"),
        "unrevealed_guardrails": _safe_text_list(wc.unrevealed_guardrails, "unrevealed_guardrails"),
    }
    brief: dict[str, Any] = {
        key: _safe_text(value, f"scene_brief.{key}")
        for key, value in {
            "title": scene.title,
            "goal": scene.goal,
            "conflict": scene.conflict,
            "turning_point": scene.turning_point,
            "outcome": scene.outcome,
            "ending_hook": scene.ending_hook,
        }.items()
    }
    brief["key_events"] = _safe_text_list(scene.key_events, "scene_brief.key_events")
    return {"writer_context": writer_context, "scene_brief": brief}

class V2ProjectRuntime:
    """Read/write access to v2 artifacts for one public project.

    Canon mutation remains exclusively in ``apply_reviewed_patch``.  Design and
    writer artifacts are persisted separately below each volume directory.
    """

    def __init__(self, series_dir: Path) -> None:
        self.series_dir = Path(series_dir)
        self.store = CanonEventStore(self.series_dir / "canon")
        self._slicer = CanonSliceBuilder()

    def canon(self) -> Canon:
        """Return the recovered materialized Canon, never a legacy projection."""
        return self.store.recover()

    def default_scope(self, canon: Canon, requested_names: list[str] | None = None, setting_name: str = "") -> ContextScope:
        """Resolve only exact, Canon-backed display names into typed references.

        No fuzzy/name-similarity lookup is performed.  An unresolved generated
        name becomes a local role in the design artifact, never a Canon ref.
        """
        if not canon.characters:
            raise ValueError("v2 design requires at least one Canon character")
        if not canon.locations:
            raise ValueError("v2 design requires at least one Canon location; add it in the plan seed")
        by_name = {c.identity.display_name: c for c in canon.characters}
        requested_pov = requested_names[0] if requested_names else ""
        pov = by_name.get(requested_pov) if requested_pov else canon.characters[0]
        if pov is None:
            # POV name from a generated scene may not exactly match a Canon
            # display name.  Fall back to the first character rather than
            # hard-failing the whole design.
            pov = canon.characters[0]
        if setting_name:
            location = next((location for location in canon.locations if location.name == setting_name), None)
            if location is None:
                # Setting names from generated scene designs may not exactly
                # match a Canon location (different phrasing).  Fall back to the
                # first Canon location instead of hard-failing the whole design.
                location = canon.locations[0]
        else:
            location = canon.locations[0]
        required = []
        for name in requested_names or []:
            character = by_name.get(name)
            if character is not None and character.id != pov.id:
                required.append(EntityRef(kind="character", id=character.id))
        return ContextScope(
            pov_character=EntityRef(kind="character", id=pov.id),
            setting=EntityRef(kind="location", id=location.id),
            required_refs=required,
        )

    def projection(self, stage: str, scope: ContextScope, canon: Canon) -> Projection:
        return self._slicer.build(stage, scope, canon)

    def author_context_text(self, stage: str, scope: ContextScope, canon: Canon) -> str:
        projection = self.projection(stage, scope, canon)
        return json.dumps(projection.author_context, ensure_ascii=False, indent=2)

    def scene_artifact(
        self,
        *,
        volume: int,
        chapter: int,
        scene: int,
        raw: dict[str, Any],
        canon: Canon,
    ) -> SceneDesign:
        requested: list[str] = []
        pov = raw.get("pov")
        if isinstance(pov, str) and pov:
            requested.append(pov)
        for value in raw.get("characters", []):
            if isinstance(value, str) and value and value not in requested:
                requested.append(value)
        scope = self.default_scope(canon, requested, str(raw.get("setting", "")))
        projection = self.projection("scene", scope, canon)
        by_name = {c.identity.display_name: c for c in canon.characters}
        cast: list[CastEntry] = []
        for name in requested:
            character = by_name.get(name)
            if character is not None:
                cast.append(CastCharacter(character=EntityRef(kind="character", id=character.id)))
            else:
                cast.append(CastLocalRole(label=name, count="one", scene_function="scene_local"))
        pov_ref = scope.pov_character
        if pov_ref is None:
            raise ValueError("v2 scene scope requires a POV character")
        pov_name = next(c.identity.display_name for c in canon.characters if c.id == pov_ref.id)
        safe = projection.pov_safe_context
        beats = [
            value
            for value in (
                raw.get("goal"), raw.get("conflict"), raw.get("turning_point"), raw.get("outcome"), raw.get("ending_hook")
            )
            if isinstance(value, str) and value
        ]
        writer_context = WriterContext(
            pov={"display_name": pov_name},
            cast_constraints=list(safe.get("cast_constraints", [])),
            setting_constraints=_text_items(safe.get("setting_constraints")),
            setting_state=_text_items(safe.get("setting_state")),
            artifact_constraints=_text_items(safe.get("artifact_constraints")),
            artifact_state=_text_items(safe.get("artifact_state")),
            time_constraints=_text_items(safe.get("time_constraints")),
            required_story_beats=beats + [str(v) for v in raw.get("key_events", []) if isinstance(v, str)],
            unrevealed_guardrails=list(safe.get("unrevealed_guardrails", [])),
        )
        manifest = ProjectionManifest(
            projection_version=projection.projection_version,
            canon_digest=projection.canon_digest,
            stage=projection.stage,
            roots=list(projection.scope_manifest.get("roots", [])),
            included=list(projection.scope_manifest.get("included", [])),
            omitted_optional_count=int(projection.scope_manifest.get("omitted_optional_count", 0)),
        )
        design = SceneDesign(
            scene_id=f"vol{volume:02d}_ch{chapter:02d}_sc{scene:03d}",
            source_location=SceneLocation(volume=volume, chapter=chapter, ordinal=scene),
            chapter_number=chapter,
            scene_number=scene,
            title=str(raw.get("title", "")),
            goal=str(raw.get("goal", "")),
            conflict=str(raw.get("conflict", "")),
            outcome=str(raw.get("outcome", "")),
            turning_point=str(raw.get("turning_point", "")),
            ending_hook=str(raw.get("ending_hook", "")),
            key_events=[str(v) for v in raw.get("key_events", []) if isinstance(v, str)],
            context_scope=scope,
            design_intent=DesignIntent(constraints=[str(raw.get("theme", ""))] if raw.get("theme") else []),
            cast=cast,
            writer_context=writer_context,
            projection_manifest=manifest,
        )
        # Validate the public writer DTO here while Canon truth is still
        # available.  A design response must not smuggle an author-only secret
        # into its narrative brief or writer beats.
        serialized = json.dumps(_writer_payload(design), ensure_ascii=False)
        for knowledge in canon.knowledge:
            if knowledge.visibility == "secret" and knowledge.proposition and knowledge.proposition in serialized:
                raise ValueError("writer boundary rejected author-only secret proposition")
        return design

    def writer_payload(self, scene: SceneDesign) -> dict[str, Any]:
        """Return the validated, writer-safe DTO for a persisted design."""
        return _writer_payload(scene)

    def save_design(
        self,
        volume: int,
        volume_design: VolumeDesign,
        chapters: list[ChapterDesign],
        scenes: list[SceneDesign],
    ) -> Path:
        path = self.series_dir / f"vol{volume:02d}" / "v2_design.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "volume": volume_design.model_dump(mode="json", exclude_none=True),
            "chapters": [c.model_dump(mode="json", exclude_none=True) for c in chapters],
            "scenes": [s.model_dump(mode="json", exclude_none=True) for s in scenes],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load_design(self, volume: int) -> tuple[dict[str, Any], list[SceneDesign]]:
        path = self.series_dir / f"vol{volume:02d}" / "v2_design.json"
        if not path.exists():
            raise FileNotFoundError(f"v2 design artifact not found: {path}; run design first")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 2:
            raise ValueError(f"unsupported design artifact version: {payload.get('version')!r}")
        return payload, [SceneDesign.model_validate(item) for item in payload.get("scenes", [])]


__all__ = ["V2ProjectRuntime"]
