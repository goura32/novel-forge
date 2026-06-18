"""Context builder for scene writing.

Builds context and continuity information from blackboard and bible
to provide LLM with comprehensive scene writing context.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novel_forge.models import VolumeOutline
from novel_forge.storage import BlackboardStorage, BibleStorage


class ContextBuilder:
    """Builds context and continuity strings for scene writing prompts."""

    def __init__(
        self,
        workdir: Path,
        blackboard_storage: BlackboardStorage,
        bible_storage: BibleStorage,
    ):
        self._workdir = workdir
        self._bb_storage = blackboard_storage
        self._bible_storage = bible_storage

    # ── series plan ──────────────────────────────────────────────────

    def get_series_plan_summary(self) -> str:
        plan_path = self._workdir / "series_plan.json"
        if not plan_path.exists():
            return ""
        data = json.loads(plan_path.read_text(encoding="utf-8"))
        lines = [
            f"タイトル: {data.get('title', '')}",
            f"あらすじ: {data.get('logline', '')}",
            f"ジャンル: {data.get('genre', '')}",
            f"ターゲット読者: {data.get('target_audience', '')}",
            f"テーマ: {', '.join(data.get('themes', []))}",
        ]
        world = data.get("world", {})
        if world:
            lines.append(f"世界観: {world.get('summary', '')}")
            for rule in world.get("rules", []):
                lines.append(f"  ルール: {rule}")
        chars = data.get("main_characters", [])
        if chars:
            lines.append("メインキャラクター:")
            for c in chars:
                lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        volumes = data.get("planned_volumes", [])
        if volumes:
            lines.append("各巻:")
            for v in volumes:
                lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
        return "\n".join(lines)

    def get_genre(self) -> str:
        plan_path = self._workdir / "series_plan.json"
        if plan_path.exists():
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            return data.get("genre", "fantasy")
        return "fantasy"

    # ── scene / outline summaries ────────────────────────────────────

    def get_scene_summary(self, scene) -> str:
        goal_text = scene.goal or ""
        if "|" in goal_text:
            state_part = goal_text.split("|")[0].strip()
            if state_part.startswith("State:"):
                goal_text = state_part[6:].strip()
        lines = [
            f"タイトル: {scene.title}",
            f"目標: {goal_text}",
            f"結果: {scene.outcome}",
            f"葛藤: {scene.conflict}",
            f"視点: {scene.pov}",
            f"登場人物: {', '.join(scene.characters) if scene.characters else 'なし'}",
        ]
        if scene.key_events:
            lines.append(f"主要イベント: {'; '.join(scene.key_events)}")
        if scene.setting:
            lines.append(f"舞台設定: {scene.setting}")
        return "\n".join(lines)

    def get_outline_summary(self, outline: VolumeOutline) -> str:
        lines = [f"タイトル: {outline.title}", f"前提: {outline.premise}", ""]
        for ch in outline.chapters:
            lines.append(f"第{ch.number}章: {ch.title}（{ch.purpose}）")
        lines.append("")
        for sc in outline.scenes:
            goal_text = sc.goal or ""
            if "|" in goal_text:
                state_part = goal_text.split("|")[0].strip()
                if state_part.startswith("State:"):
                    goal_text = state_part[6:].strip()
            lines.append(f"シーン{sc.number}（第{sc.chapter_number}章）: {sc.title}")
            lines.append(f"  目標: {goal_text}")
            lines.append(f"  結果: {sc.outcome}")
            lines.append(f"  登場人物: {', '.join(sc.characters) if sc.characters else 'なし'}")
        return "\n".join(lines)

    # ── context (Bible + Blackboard) ────────────────────────────────

    def build_context(self) -> str:
        bb = self._bb_storage.load()
        bible = self._bible_storage.load()
        parts = []
        if bb.facts:
            parts.append(
                "## 事実記録\n"
                + "\n".join(
                    f"- {f.subject} {f.predicate} {f.object}"
                    for f in bb.facts[-20:]
                )
            )
        if bible.characters:
            parts.append(
                "## キャラクター\n"
                + "\n".join(
                    f"- {c.name}（{c.role or ''}）: {c.personality or ''} / 動機: {c.motivation or ''}"
                    for c in bible.characters
                )
            )
        if bible.relationships:
            parts.append(
                "## キャラクター関係性\n"
                + "\n".join(
                    f"- {r.character_a} ↔ {r.character_b}: {r.relationship_type or '関係未設定'} / 状態: {r.status or '未設定'}"
                    for r in bible.relationships
                )
            )
        if bible.subplots:
            active_subplots = [sp for sp in bible.subplots if sp.status != "completed"]
            if active_subplots:
                parts.append(
                    "## サブプロット\n"
                    + "\n".join(
                        f"- {sp.name}: {sp.progress_note or '進捗なし'}"
                        for sp in active_subplots
                    )
                )
        if bible.glossary:
            parts.append(
                "## 用語\n"
                + "\n".join(f"- {g.term}: {g.definition}" for g in bible.glossary[-10:])
            )
        if bible.world_rules:
            parts.append(
                "## 世界観ルール\n" + "\n".join(f"- {r}" for r in bible.world_rules)
            )
        return "\n\n".join(parts)

    # ── continuity (previous scene info) ────────────────────────────

    def build_continuity(
        self,
        scene_number: int,
        vol_num: int,
        load_scene_draft_fn,
    ) -> str:
        bb = self._bb_storage.load()
        parts = []

        # 前シーン全文
        if scene_number > 1 and vol_num > 0:
            prev_draft = load_scene_draft_fn(vol_num, scene_number - 1)
            if prev_draft:
                parts.append(f"## 前シーン全文\n{prev_draft}")

        # 前々シーンまでの要約（直近 3 件）
        summaries = []
        for sn in range(max(1, scene_number - 3), scene_number - 1):
            s = bb.scene_summaries.get(str(sn), "")
            if s:
                summaries.append(f"  シーン{sn}: {s}")
        if summaries:
            parts.append("## 直近シーン要約\n" + "\n".join(summaries))

        # 引き継ぎメモ
        notes = "\n".join(bb.continuity_notes[-5:]) if bb.continuity_notes else ""
        if notes:
            parts.append(f"## 引き継ぎメモ\n{notes}")

        return "\n\n".join(parts) if parts else "（最初のシーン）"
