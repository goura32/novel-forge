"""§5–§6 design artifacts: SceneDesign / ChapterDesign / VolumeDesign.

These are Canon-independent structured *plans* attached to volume / chapter /
scene artifacts.  They carry ``design_intent``, typed ``context_scope``,
``canon_patch`` (review-passed scenes only), ``cast``, ``relationship_context``,
``writer_context``, and a ``projection_manifest``.

They must NOT import any v1 runtime module.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    CastCharacter,
    CastLocalRole,
    ContextScope,
    DesignIntent,
    WriterContext,
)


def _forbid() -> ConfigDict:
    return ConfigDict(extra="forbid")


# §5 cast entry: a character ref OR a one-shot local role (never promoted).
CastEntry = CastCharacter | CastLocalRole


class RelationshipContext(BaseModel):
    """§6 scene relationship context (arc intent / perspective anchors)."""

    model_config = _forbid()

    relationship_refs: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProjectionManifest(BaseModel):
    """§6.2 projection manifest persisted on a scene design."""

    model_config = _forbid()

    projection_version: int = 1
    canon_digest: str = ""
    stage: str = ""
    roots: list[dict[str, Any]] = Field(default_factory=list)
    included: list[dict[str, Any]] = Field(default_factory=list)
    omitted_optional_count: int = 0


class SceneDesign(BaseModel):
    """§6 scene design artifact.

    Only a *review-passed* scene design carries ``canon_patch``.  The writer
    receives ``writer_context`` plus the immediately preceding scene summary;
    it never reads the Bible / Canon Event log / author truth.
    """

    model_config = _forbid()

    scene_id: str
    context_scope: ContextScope | None = None
    design_intent: DesignIntent | None = None
    cast: list[CastEntry] = Field(default_factory=list)
    relationship_context: RelationshipContext | None = None
    canon_patch: dict[str, Any] | None = None  # §6 CanonPatch (review-passed only)
    writer_context: WriterContext | None = None  # §6.2 projection for the writer
    projection_manifest: ProjectionManifest | None = None
    status: Literal["draft", "review_passed", "applied"] = "draft"


class ChapterDesign(BaseModel):
    """§5 chapter design artifact (intent + scope, never writes Canon)."""

    model_config = _forbid()

    chapter_id: str
    context_scope: ContextScope | None = None
    design_intent: DesignIntent | None = None
    scene_seeds: list[dict[str, Any]] = Field(default_factory=list)


class VolumeDesign(BaseModel):
    """§5 volume design artifact (intent + scope, never writes Canon)."""

    model_config = _forbid()

    volume_id: str
    context_scope: ContextScope | None = None
    design_intent: DesignIntent | None = None


__all__ = [
    "CastEntry",
    "RelationshipContext",
    "ProjectionManifest",
    "SceneDesign",
    "ChapterDesign",
    "VolumeDesign",
]
