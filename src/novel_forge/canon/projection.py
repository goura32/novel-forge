"""§6.2 projection helpers: attach writer_context to SceneDesign.

Connects ``CanonSliceBuilder`` (deterministic projection) to the scene design
artifact.  The writer receives only ``scene_design.writer_context`` plus the
immediately preceding scene summary — never the Bible / Canon Event log /
author-only truth / stable IDs.
"""

from __future__ import annotations

from typing import Any

from .design import ProjectionManifest, SceneDesign, WriterContext
from .models import Canon, ContextScope
from .slice import CanonSliceBuilder, Projection


def build_scene_projection(
    scope: ContextScope,
    canon: Canon,
    stage: str = "scene_design",
    budget: int = 8000,
) -> Projection:
    """Build a deterministic projection from a ContextScope + Canon."""
    builder = CanonSliceBuilder()
    return builder.build(stage=stage, scope=scope, canon=canon, budget=budget)


def projection_to_writer_context(proj: Projection) -> WriterContext:
    """Map a projection's ``pov_safe_context`` into a §6.2 WriterContext."""
    safe: dict[str, Any] = proj.pov_safe_context or {}

    def as_list(v: Any) -> list[Any]:
        if v is None:
            return []
        return v if isinstance(v, list) else [v]

    def flatten_str(v: Any) -> list[str]:
        out: list[str] = []
        for item in as_list(v):
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, list):
                out.extend(x for x in item if isinstance(x, str))
        return out

    cast_constraints = as_list(safe.get("cast_constraints"))
    # POV is the first cast entry (the pov_character root).
    pov = cast_constraints[0] if cast_constraints else {}

    return WriterContext(
        pov=pov if isinstance(pov, dict) else {},
        cast_constraints=cast_constraints,
        setting_constraints=flatten_str(safe.get("setting_constraints")),
        setting_state=as_list(safe.get("setting_state")),
        artifact_constraints=flatten_str(safe.get("artifact_constraints")),
        artifact_state=as_list(safe.get("artifact_state")),
        time_constraints=as_list(safe.get("time_constraints")),
        required_story_beats=as_list(safe.get("required_story_beats")),
        unrevealed_guardrails=as_list(safe.get("unrevealed_guardrails")),
    )


def attach_writer_context(
    scene_design: SceneDesign,
    canon: Canon,
    stage: str = "scene_design",
    budget: int = 8000,
) -> SceneDesign:
    """Populate ``writer_context`` + ``projection_manifest`` on a SceneDesign.

    Requires ``scene_design.context_scope``; raises ``ValueError`` if absent.
    """
    if scene_design.context_scope is None:
        raise ValueError("SceneDesign.context_scope is required to build a projection")
    proj = build_scene_projection(
        scene_design.context_scope, canon, stage=stage, budget=budget
    )
    scene_design.writer_context = projection_to_writer_context(proj)
    scene_design.projection_manifest = ProjectionManifest(
        projection_version=proj.projection_version,
        canon_digest=proj.canon_digest,
        stage=proj.stage,
        roots=proj.scope_manifest.get("roots", []),
        included=proj.scope_manifest.get("included", []),
        omitted_optional_count=proj.scope_manifest.get("omitted_optional_count", 0),
    )
    return scene_design


__all__ = [
    "build_scene_projection",
    "projection_to_writer_context",
    "attach_writer_context",
]
