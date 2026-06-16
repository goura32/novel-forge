from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ── 事実記録（Blackboard）──────────────────────────────────────────────

class Fact(BaseModel):
    subject: str
    predicate: str
    object: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class Blackboard(BaseModel):
    facts: list[Fact] = Field(default_factory=list)
    scene_summaries: dict[str, str] = Field(default_factory=dict)
    continuity_notes: list[str] = Field(default_factory=list)
    subplots: list[SubplotItem] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)  # [{"event": str, "scene_number": int, "timestamp": str}]


# ── 設定資料集（Bible）────────────────────────────────────────────────

class CharacterProfile(BaseModel):
    name: str
    role: str = ""
    arc: str = ""
    appearance: str = ""
    personality: str = ""
    motivation: str = ""
    state: str = ""


class GlossaryItem(BaseModel):
    term: str
    definition: str


class ForeshadowingItem(BaseModel):
    description: str
    resolved: bool = False


class RelationshipItem(BaseModel):
    character_a: str
    character_b: str
    relationship_type: str = ""  # 敵対・協力・恋愛・師弟・家族・ライバル etc
    status: str = ""  # 良好・緊張・悪化・修復・変化中
    change_direction: str = ""  # improved | worsened | changed | unchanged
    trigger_event: str = ""
    scene_number: int = 0  # 変化が起きたシーン番号


class SubplotItem(BaseModel):
    id: str
    name: str
    status: str = Field(default="not_started", pattern="^(not_started|in_progress|completed)$")
    progress_note: str = ""
    related_characters: list[str] = Field(default_factory=list)
    related_foreshadowing_ids: list[str] = Field(default_factory=list)


class Bible(BaseModel):
    characters: list[CharacterProfile] = Field(default_factory=list)
    glossary: list[GlossaryItem] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingItem] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    relationships: list[RelationshipItem] = Field(default_factory=list)
    subplots: list[SubplotItem] = Field(default_factory=list)


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
        pattern="^(導入|展開|転換|クライマックス|収束)$",
    )
    act_role: str = Field(
        default="",
        pattern="^(設定|対立|解決)$",
    )
    characters: list[str] = Field(default_factory=list)


# ── 巻アウトライン ─────────────────────────────────────────────────────

class SceneOutline(BaseModel):
    number: int = Field(ge=1)
    chapter_number: int = Field(ge=1)
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
        pattern="^(導入|展開|転換|クライマックス|収束)$",
    )


class VolumeOutline(BaseModel):
    volume_number: int = Field(ge=1)
    title: str = Field(max_length=128)
    premise: str = Field(max_length=200, default="")
    chapters: list[ChapterOutline] = Field(default_factory=list)
    scenes: list[SceneOutline] = Field(default_factory=list)


# ── シリーズ企画 ───────────────────────────────────────────────────────

class VolumePlanItem(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128, default="")
    premise_str: str = Field(max_length=80, default="", alias="premise")


class SeriesPlan(BaseModel):
    title: str = ""
    slug: str = Field(default="", max_length=256, pattern=r"^[a-z0-9-]+$")
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
    score: float = Field(ge=0.0, le=100.0, default=0.0)
    issues: list[dict[str, Any]] = Field(default_factory=list)


class SceneRecord(BaseModel):
    scene_number: int = Field(ge=1)
    status: str = Field(
        default="計画中",
        pattern="^(計画中|初稿済|レビュー済|修正済|強制出力済|エラー)$",
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
        default="計画中",
        pattern="^(計画中|アウトライン済|執筆中|初稿済|出力済|確定済|強制出力済)$",
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
        default="計画中",
        pattern="^(計画中|アウトライン済|執筆中|初稿済|出力済|確定済|強制出力済)$",
    )
