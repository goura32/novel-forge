from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ── キャラクター ───────────────────────────────────────────────────────


class CharacterProfile(BaseModel):
    name: str
    role: str = ""
    arc: str = ""
    appearance: str = ""
    personality: str = ""
    motivation: str = ""
    flaw: str = ""
    age: str = ""
    occupation: str = ""
    background: str = ""
    state: str = ""


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
    hook: str = Field(max_length=300, default="")
    turning_point: str = Field(max_length=300, default="")
    ending_hook: str = Field(max_length=300, default="")
    sensory_focus: list[str] = Field(default_factory=list)
    subtext: str = Field(max_length=300, default="")
    foreshadowing: list[str] = Field(default_factory=list)
    resolves_foreshadowing: list[str] = Field(
        default_factory=list,
        description="このシーンで回収する伏線の識別情報（description または id）。設計者の意図による明示的回収。",
    )
    key_events: list[str] = Field(default_factory=list)
    setting: str = Field(max_length=200, default="")
    notes: str = Field(max_length=500, default="")


# ── 章設計 ─────────────────────────────────────────────────────────────


class ChapterDesign(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128)
    purpose: str = Field(
        default="",
        pattern="^(導入|展開|転換|クライマックス|収束)$",
    )
    theme: str = Field(max_length=200, default="")
    emotional_arc: str = Field(max_length=200, default="")
    chapter_turning_point: str = Field(max_length=300, default="")
    chapter_hook: str = Field(max_length=300, default="")
    foreshadowing_notes: list[str] = Field(default_factory=list)
    subplot_notes: list[str] = Field(default_factory=list)
    scene_summaries: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)


# ── 巻デザイン ─────────────────────────────────────────────────────


class SceneOutline(BaseModel):
    number: int = Field(ge=1)
    chapter_number: int = Field(ge=1)
    title: str = Field(max_length=128)
    pov: str = Field(max_length=64, default="")
    goal: str = ""
    conflict: str = Field(max_length=200, default="")
    outcome: str = Field(max_length=200, default="")
    characters: list[str] = Field(default_factory=list)
    emotional_arc: str = Field(max_length=200, default="")
    hook: str = Field(max_length=300, default="")
    turning_point: str = Field(max_length=300, default="")
    ending_hook: str = Field(max_length=300, default="")
    sensory_focus: list[str] = Field(default_factory=list)
    subtext: str = Field(max_length=300, default="")
    foreshadowing: list[str] = Field(default_factory=list)
    key_events: list[str] = Field(default_factory=list)
    setting: str = Field(max_length=200, default="")


class ChapterOutline(BaseModel):
    number: int = Field(ge=1)
    title: str = Field(max_length=128)
    purpose: str = Field(
        pattern="^(導入|展開|転換|クライマックス|収束)$",
    )


class VolumeOutline(BaseModel):
    volume_number: int = Field(ge=1)
    title: str = Field(default="", max_length=128)
    premise: str = Field(max_length=200, default="")
    chapters: list[ChapterOutline] = Field(default_factory=list)
    scenes: list[SceneOutline] = Field(default_factory=list)


# ── シリーズ企画 ───────────────────────────────────────────────────────


class VolumePlanItem(BaseModel):
    title: str = Field(max_length=128, default="")
    premise: str = Field(max_length=200, default="")
    theme: str = Field(max_length=200, default="")
    emotional_arc: str = Field(max_length=200, default="")
    key_events: list[str] = Field(default_factory=list)
    cliffhanger: str = Field(max_length=200, default="")


class SeriesPlan(BaseModel):
    title: str = ""
    slug: str = ""
    logline: str = Field(default="", max_length=400)
    genre: list[str] = Field(default_factory=list)
    target_audience: str = Field(default="", max_length=200)
    themes: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    world_summary: str = ""
    world_rules: list[str] = Field(default_factory=list)
    main_characters: list[CharacterProfile] = Field(default_factory=list)
    planned_volumes: list[VolumePlanItem] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    catchphrase: str = ""
    differentiation: str = ""


# ── シーン生成状況 ─────────────────────────────────────────────────────


class SceneRecord(BaseModel):
    scene_number: int = Field(ge=1)
    status: str = Field(
        default="計画中",
        pattern="^(計画中|初稿済|レビュー済|修正済|強制出力済|エラー)$",
    )
    quality_retries: int = Field(ge=0, default=0)
    draft_version: int = Field(ge=1, default=1)
    quality_gate: Any = Field(default_factory=lambda: {"passed": False, "issues": []})
    design: SceneDesign | None = None
    draft_path: str = ""
    review_path: str = ""


# ── プロジェクト状態 ───────────────────────────────────────────────────


class VolumeProgress(BaseModel):
    volume_number: int = Field(ge=1)
    status: str = Field(
        default="計画中",
        pattern="^(計画中|デザイン済|執筆中|初稿済|出力済|確定済|強制出力済)$",
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
        pattern="^(計画中|企画済|デザイン済|執筆中|初稿済|出力済|確定済|強制出力済)$",
    )
