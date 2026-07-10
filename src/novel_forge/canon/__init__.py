"""Series Bible v2 — Canon / Identity / Patch / Event package.

This package is a *new* v2 implementation. It must not import or depend on any
v1 runtime module (``novel_forge.models``, ``storage``, ``bible_manager``,
``scene_writer``, ``context_builder``, ``cli``, ``engine/*``).

The Pydantic v2 models in ``models.py`` are the single source of truth for the
Canon domain contract. ``slice.py`` builds deterministic LLM projections
(§6.2), ``idgen.py`` mints stable IDs (§3.3), ``store.py`` holds the
event-sourced store / replay / recovery (§7, §8), and ``patch_apply.py``
applies a reviewed patch to a Canon (§6, §7.1).
"""

from __future__ import annotations

from novel_forge.canon.design import (
    CastEntry,
    ChapterDesign,
    ProjectionManifest,
    RelationshipContext,
    SceneDesign,
    VolumeDesign,
)
from novel_forge.canon.idgen import StableIdGenerator
from novel_forge.canon.models import (
    Canon,
    CanonEvent,
    CanonPatch,
    CharacterIdentity,
    CharacterProfile,
    ContextScope,
    CreationRef,
    EntityRef,
    ReviewEvidence,
    SourceRef,
    compute_canonical_digest,
)
from novel_forge.canon.patch_apply import CanonPatchApplier, PatchValidationError
from novel_forge.canon.projection import attach_writer_context
from novel_forge.canon.registry import build_registry, get_validator
from novel_forge.canon.runtime import (
    ReviewResult,
    apply_reviewed_patch,
    attach_projection,
    build_chapter_intent,
    build_scene_design,
    build_volume_intent,
    export_canon,
    review_scene_patch,
    run_v2_pipeline,
    write_scene,
)
from novel_forge.canon.slice import CanonSliceBuilder, Projection
from novel_forge.canon.store import (
    BibleFactory,
    CanonEventStore,
    CanonStoreError,
)

__all__ = [
    "Canon",
    "CanonEvent",
    "CanonPatch",
    "CharacterIdentity",
    "CharacterProfile",
    "ContextScope",
    "CreationRef",
    "EntityRef",
    "ReviewEvidence",
    "SourceRef",
    "compute_canonical_digest",
    "StableIdGenerator",
    "CanonPatchApplier",
    "PatchValidationError",
    "attach_writer_context",
    "build_registry",
    "get_validator",
    "CastEntry",
    "ChapterDesign",
    "ProjectionManifest",
    "RelationshipContext",
    "SceneDesign",
    "VolumeDesign",
    "CanonSliceBuilder",
    "Projection",
    "BibleFactory",
    "CanonEventStore",
    "CanonStoreError",
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
