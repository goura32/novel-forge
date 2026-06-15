from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ── 事実記録（Blackboard）──────────────────────────────────────────────

class Fact(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class Blackboard(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    scene_summaries: dict[str, str] = Field(default_factory=dict)
    continuity_notes: list[str] = Field(default_factory=list)


# ── 設定資料集（Bible）────────────────────────────────────────────────

class CharacterProfile(BaseModel):
    name: str
    role: str = ""
    arc: str = ""
    appearance: str = ""
    personality: str = ""
    state: str = ""


class GlossaryItem(BaseModel):
    term: str
    definition: str


class ForeshadowingItem(BaseModel):
    description: str
    resolved: bool = False


class Bible(BaseModel):
    characters: list[CharacterProfile] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingItem] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)


# ── シーン設計 ─────────────────────────────────────────────────────────

class SceneDesign(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128)
    pov: str = Field(max_length=64, default="")
    goal: str = ""
    conflict: str = Field(max_length=200, default="")
    outcome: str = Field(max_length=200, default="")
    characters: list[str] = Field(default_factory=list)
    emotional_arc: str = Field(max_length=200, default="")
    key_events: list[str] = Field(default_factory=list)
    setting: str = Field(max_length=200, default="")
    notes: str = Field(max_length=500, default="")


# ── 章設計 ─────────────────────────────────────────────────────────────

class ChapterDesign(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128)
    theme: str = Field(max_length=200, default="")
    scene_summaries: list[str] = Field(default_factory=list)
    emotional_arc: str = Field(max_length=200, default="")
    purpose: str = Field(
        default="",
        pattern="^(introduction|rising_action|turning_point|climax|resolution)$",
    )
    act_role: str = Field(
        default="",
        pattern="^(setup|confrontation|resolution)$",
    )
    characters: list[str] = Field(default_factory=list)


# ── 巻アウトライン ─────────────────────────────────────────────────────

class SceneOutline(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128)
    pov: str = Field(max_length=64, default="")
    goal: str = ""
    conflict: str = Field(max_length=200, default="")
    outcome: str = Field(max_length=200, default="")
    characters: list[str] = Field(default_factory=list)


class ChapterOutline(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128)
    purpose: str = Field(
        pattern="^(introduction|rising_action|turning_point|climax|resolution)$",
    )
    scenes: list[SceneOutline] = Field(default_factory=list)


class VolumeOutline(BaseModel):
    volume_number: int = Field(ge=1)
    title: str = Field(max_length=128)
    premise: str = Field(max_length=200, default="")
    chapters: list[ChapterOutline] = Field(default_factory=list)


# ── シリーズ企画 ───────────────────────────────────────────────────────

class VolumePlanItem(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128, default="")
    premise_str: str = Field(max_length=80, default="", alias="premise")


class SeriesPlan(BaseModel):
    title: str = ""
    slug: str = Field(default="", max_length=64, pattern=r"^[a-z0-9-]+$")
    logline: str = Field(default="", max_length=200)
    genre: str = ""
    target_audience: str = Field(default="", max_length=50)
    themes: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    world: dict[str, Any] = Field(default_factory=lambda: {"summary": "", "rules": []})
    main_characters: list[CharacterProfile] = Field(default_factory=list)
    planned_volumes: list[VolumePlanItem] = Field(default_factory=list)
    premise: str = ""
    keywords: list[str] = Field(default_factory=list)
    catchphrase: str = ""
    differentiation: str = ""


# ── シーン生成状況 ─────────────────────────────────────────────────────

class QualityGateResult(BaseModel):
    passed: bool = False
    score: float = Field(ge=0.0, le=10.0, default=0.0)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class SceneRecord(BaseModel):
    scene_number: int = Field(ge=1)
    status: str = Field(
        default="planned",
        pattern="^(planned|drafted|reviewed|revised|force_exported)$",
    )
    quality_retries: int = Field(ge=0, default=0)
    quality_gate: QualityGateResult = Field(default_factory=QualityGateResult)
    design: SceneDesign | None = None
    draft_path: str = ""
    review_path: str = ""


# ── プロジェクト状態 ───────────────────────────────────────────────────

class VolumeProgress(BaseModel):
    volume_number: int = Field(ge=1)
    status: str = Field(
        default="planned",
        pattern="^(planned|outlined|drafting|drafted|exported|finalized|force_exported)$",
    )
    word_count: int = Field(ge=0, default=0)
    target_word_count: int = Field(ge=0, default=80000)
    scenes: list[SceneRecord] = Field(default_factory=list)


class ProjectState(BaseModel):
    series_title: str = ""
    workdir: str = ""
    model: str = ""
    lang: str = "ja"
    current_volume: int = Field(ge=1, default=1)
    volumes: list[VolumeProgress] = Field(default_factory=list)
    status: str = Field(
        default="planned",
        pattern="^(planned|outlined|drafting|drafted|exported|finalized|force_exported)$",
    )
