"""Bible manager for updating and querying the project bible.

Handles character profiles, foreshadowing, relationships, subplots,
glossary, and world rules.
"""

from __future__ import annotations

from novel_forge.models import (
    Bible,
    ForeshadowingItem,
    SubplotItem,
)
from novel_forge.storage import BibleStorage


class BibleManager:
    """Manages Bible updates and queries."""

    def __init__(self, bible_storage: BibleStorage):
        self._storage = bible_storage
        self._series_dir = bible_storage._path.parent

    def _active_canon(self):
        """Load the materialized v2 Canon when this project has migrated."""
        canon_path = self._series_dir / "canon" / "bible.json"
        if not canon_path.exists():
            return None
        from novel_forge.canon.store import CanonEventStore

        return CanonEventStore(self._series_dir / "canon").recover()

    def _canon_text(self, stage: str, context: dict | None = None) -> str:
        """Prompt-safe v2 projection; no IDs or author-only internal fields."""
        canon = self._active_canon()
        if canon is None:
            return ""
        context = context or {}
        lines: list[str] = []
        if canon.world_rules:
            lines.append("## 世界観ルール（遵守）")
            lines.extend(f"  - {rule.statement}" for rule in canon.world_rules)
        if stage in {"chapter", "scene"}:
            active_fh = [f for f in canon.foreshadowing if f.status != "resolved"]
            if active_fh:
                lines.append("## 未回収伏線（この章/シーンで回収するなら明示）")
                lines.extend(f"  - {f.description}" for f in active_fh)
        if stage == "volume":
            active_sp = [s for s in canon.subplots if s.status == "active"]
            if active_sp:
                lines.append("## 進行中サブプロット")
                lines.extend(f"  - {s.name}: {s.current_state}" for s in active_sp)
        if stage == "scene":
            names = set(context.get("character_names", []) or [])
            chars = [c for c in canon.characters if not names or c.identity.display_name in names]
            if chars:
                lines.append("## 登場人物の現在状態")
                lines.extend(
                    f"  - {c.identity.display_name}（{c.narrative_function}） / 現在: {c.continuity_card.current_state}"
                    for c in chars
                )
            if canon.relationships:
                lines.append("## 人物関係")
                lines.extend(
                    f"  - {r.shared_state.current_arrangement or r.shared_state.central_tension}"
                    for r in canon.relationships
                )
        return "\n".join(lines) if lines else "（参照すべき聖典情報はありません）"


    @property
    def bible(self) -> Bible:
        return self._storage.load()

    def save(self, bible: Bible) -> None:
        # A v2 project has a single mutation route: Canon Events.  Legacy
        # bible.json remains a one-time compatibility projection only.
        if (self._series_dir / "canon" / "bible_seed.json").exists():
            raise RuntimeError(
                "v2 projects have a single mutation route; legacy Bible mutation is disabled; apply a reviewed CanonPatch instead"
            )
        self._storage.save(bible)

    # ── unresolved items ────────────────────────────────────────────

    def get_unresolved_foreshadowing(self) -> list[ForeshadowingItem]:
        return [fh for fh in self.bible.foreshadowing if not fh.resolved]

    def get_incomplete_subplots(self) -> list[SubplotItem]:
        return [sp for sp in self.bible.subplots if sp.status not in {"完了", "completed"}]

    # ── text serialization for prompts ──────────────────────────────

    def to_text(self) -> str:
        """Serialize current Bible to text for LLM prompts (no JSON keys)."""
        if (canon_text := self._canon_text("scene")):
            return canon_text
        bible = self.bible
        lines = []
        if bible.characters:
            lines.append("キャラクター:")
            for c in bible.characters:
                lines.append(
                    f"  - {c.name}（{c.role or '役割未設定'}）: "
                    f"{c.personality or '性格未設定'} / "
                    f"動機: {c.motivation or '未設定'} / "
                    f"外見: {c.appearance or '未設定'}"
                    + (f" / 現在: {c.state}" if c.state else "")
                )
        if bible.foreshadowing:
            lines.append("伏線:")
            for fh in bible.foreshadowing:
                status_str = "回収済" if fh.resolved else "未回収"
                lines.append(f"  - [{status_str}] {fh.description}")
        if bible.relationships:
            lines.append("キャラクター関係性:")
            for r in bible.relationships:
                lines.append(
                    f"  - {r.character_a} ↔ {r.character_b}: "
                    f"{r.relationship_type or '関係未設定'} / "
                    f"状態: {r.status or '未設定'}"
                )
        if bible.subplots:
            lines.append("サブプロット:")
            # Do NOT include status markers like [in_progress] — LLM may copy them into text
            for sp in bible.subplots:
                lines.append(f"  - {sp.name}: {sp.progress_note or '進捗なし'}")
        if bible.glossary:
            lines.append("用語:")
            for g in bible.glossary[-10:]:
                lines.append(f"  - {g.term}: {g.definition}")
        if bible.world_rules:
            lines.append("世界観ルール:")
            for rule_text in bible.world_rules:
                lines.append(f"  - {rule_text}")
        return "\n".join(lines) if lines else "（Bible は空です）"

    # ── staged slice for design prompts ────────────────────────────

    def to_text_slice(self, stage: str, context: dict | None = None) -> str:
        """Serialize a stage-specific slice of Bible for design prompts.

        Design reads only the slice relevant to the current stage:
          - volume:  meta (logline/world_rules) + 進行中 subplots
          - chapter: global constraints + 進行中 subplots + 未回収 foreshadowing
          - scene:   global constraints + 登場 characters + 未回収 foreshadowing + relationships

        Args:
            stage: "volume" | "chapter" | "scene"
            context: optional dict with keys used to narrow (e.g. character_names)
        """
        canon_text = self._canon_text(stage, context)
        if canon_text:
            return canon_text
        bible = self.bible
        context = context or {}
        lines: list[str] = []

        if stage in ("volume", "chapter", "scene") and bible.world_rules:
            lines.append("## 世界観ルール（遵守）")
            for rule in bible.world_rules:
                lines.append(f"  - {rule}")

        if stage == "volume" and bible.subplots:
            active = [s for s in bible.subplots if s.status != "完了"]
            if active:
                lines.append("## 進行中サブプロット")
                for s in active:
                    lines.append(f"  - {s.name}: {s.progress_note or ''}")

        if stage in ("chapter", "scene"):
            unresolved = [f for f in bible.foreshadowing if not f.resolved]
            if unresolved:
                lines.append("## 未回収伏線（この章/シーンで回収するなら明示）")
                for f in unresolved:
                    lines.append(f"  - {f.description}")

        if stage == "scene":
            char_names = set(context.get("character_names", []) or [])
            if bible.characters:
                if char_names:
                    relevant = [c for c in bible.characters if c.name in char_names]
                else:
                    relevant = bible.characters
                if relevant:
                    lines.append("## 登場人物の現在状態")
                    for c in relevant:
                        state = f" / 現在: {c.state}" if c.state else ""
                        lines.append(f"  - {c.name}（{c.role or ''}）{state}")
            if bible.relationships:
                lines.append("## 人物関係")
                for r in bible.relationships:
                    lines.append(
                        f"  - {r.character_a} ↔ {r.character_b}: "
                        f"{r.relationship_type or ''}"
                        + (f" / {r.status}" if r.status else "")
                    )

        return "\n".join(lines) if lines else "（参照すべき聖典情報はありません）"
