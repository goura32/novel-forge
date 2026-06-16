"""Bible manager for updating and querying the project bible.

Handles character profiles, foreshadowing, relationships, subplots,
glossary, and world rules.
"""
from __future__ import annotations

from novel_forge.models import (
    Bible,
    CharacterProfile,
    ForeshadowingItem,
    GlossaryItem,
    RelationshipItem,
    SubplotItem,
)
from novel_forge.quality import find_non_japanese_kanji
from novel_forge.storage import BibleStorage


class BibleManager:
    """Manages Bible updates and queries."""

    def __init__(self, bible_storage: BibleStorage):
        self._storage = bible_storage

    @property
    def bible(self) -> Bible:
        return self._storage.load()

    def save(self, bible: Bible) -> None:
        self._storage.save(bible)

    # ── finalize ─────────────────────────────────────────────────────

    def finalize(self, continuity_notes: list[str]) -> None:
        """Resolve foreshadowing items referenced in continuity notes."""
        bible = self.bible
        for note in continuity_notes:
            for fh in bible.foreshadowing:
                if not fh.resolved and fh.description in note:
                    fh.resolved = True
        self.save(bible)

    # ── kanji check ──────────────────────────────────────────────────

    def check_kanji(self) -> list[str]:
        bible = self.bible
        issues: list[str] = []

        def _scan(text: str, label: str) -> None:
            bad = find_non_japanese_kanji(text)
            if bad:
                unique = list(dict.fromkeys(bad))
                issues.append(
                    f"  {label}: {', '.join(f'{c}(U+{ord(c):04X})' for c in unique)} in 「{text[:40]}」"
                )

        for ch in bible.characters:
            _scan(ch.name, f"キャラクター名({ch.name})")
        for g in bible.glossary:
            _scan(g.term, f"用語({g.term})")
        for fh in bible.foreshadowing:
            _scan(fh.description, "伏線")

        return issues

    # ── unresolved items ────────────────────────────────────────────

    def get_unresolved_foreshadowing(self) -> list[ForeshadowingItem]:
        return [fh for fh in self.bible.foreshadowing if not fh.resolved]

    def get_incomplete_subplots(self) -> list[SubplotItem]:
        return [sp for sp in self.bible.subplots if sp.status != "completed"]

    # ── text serialization for prompts ──────────────────────────────

    def to_text(self) -> str:
        """Serialize current Bible to text for LLM prompts (no JSON keys)."""
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
            for sp in bible.subplots:
                lines.append(
                    f"  - [{sp.status}] {sp.name}: {sp.progress_note or '進捗なし'}"
                )
        if bible.glossary:
            lines.append("用語:")
            for g in bible.glossary[-10:]:
                lines.append(f"  - {g.term}: {g.definition}")
        if bible.world_rules:
            lines.append("世界観ルール:")
            for r in bible.world_rules:
                lines.append(f"  - {r}")
        return "\n".join(lines) if lines else "（Bible は空です）"
