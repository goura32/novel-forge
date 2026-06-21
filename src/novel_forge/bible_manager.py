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
                # Do NOT include status markers like [in_progress] — LLM may copy them into text
                lines.append(
                    f"  - {sp.name}: {sp.progress_note or '進捗なし'}"
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

    # ── apply update (from scene_summary_and_bible_update / bible_update) ──

    def apply_update(self, result: dict, scene_number: int) -> None:
        """Apply a bible update result to Bible.

        Args:
            result: Parsed JSON response from the LLM bible update prompt.
            scene_number: Current scene number for tracking relationship changes.
        """
        bible = self.bible

        # Characters
        for ch_data in result.get("characters", []):
            if not isinstance(ch_data, dict):
                continue
            new_name = ch_data.get("name", "").strip()
            if not new_name:
                continue
            # 完全一致または部分一致（既存キャラ名が新名に含まれる、または新名が既存キャラ名に含まれる）で重複チェック
            existing = next(
                (c for c in bible.characters
                 if c.name == new_name
                 or (len(new_name) >= 2 and new_name in c.name)
                 or (len(c.name) >= 2 and c.name in new_name)),
                None,
            )
            if existing:
                if ch_data.get("personality"):
                    existing.personality = ch_data["personality"]
                if ch_data.get("appearance"):
                    existing.appearance = ch_data["appearance"]
                if ch_data.get("motivation"):
                    existing.motivation = ch_data["motivation"]
                if ch_data.get("arc"):
                    existing.arc = ch_data["arc"]
                if ch_data.get("state"):
                    existing.state = ch_data["state"]
            elif ch_data.get("is_new", False) or (ch_data.get("name") and ch_data["name"].strip()):
                bible.characters.append(CharacterProfile(
                    name=ch_data.get("name", ""),
                    role=ch_data.get("role", ""),
                    personality=ch_data.get("personality", ""),
                    appearance=ch_data.get("appearance", ""),
                    motivation=ch_data.get("motivation", ""),
                    arc=ch_data.get("arc") or "",
                ))

        # Foreshadowing
        for fh_data in result.get("foreshadowing", []):
            if not isinstance(fh_data, dict):
                continue
            fh_type = fh_data.get("type", "setup")
            if fh_type == "resolution":
                for fh in bible.foreshadowing:
                    if not fh.resolved and fh.description == fh_data.get("description", ""):
                        fh.resolved = True
                        break
            else:
                desc = fh_data.get("description", "").strip()
                if desc and desc not in {f.description.strip() for f in bible.foreshadowing}:
                    bible.foreshadowing.append(ForeshadowingItem(
                        description=desc,
                        resolved=False,
                    ))

        # Relationships
        for rel_data in result.get("relationships", []):
            if not isinstance(rel_data, dict):
                continue
            existing = next(
                (r for r in bible.relationships
                 if {r.character_a, r.character_b} == {
                     rel_data.get("character_a", ""),
                     rel_data.get("character_b", ""),
                 }),
                None,
            )
            if existing:
                if rel_data.get("relationship_type"):
                    existing.relationship_type = rel_data["relationship_type"]
                if rel_data.get("change_direction"):
                    existing.change_direction = rel_data["change_direction"]
                if rel_data.get("trigger_event"):
                    existing.trigger_event = rel_data["trigger_event"]
                existing.scene_number = scene_number
            else:
                bible.relationships.append(RelationshipItem(
                    character_a=rel_data.get("character_a", ""),
                    character_b=rel_data.get("character_b", ""),
                    relationship_type=rel_data.get("relationship_type", ""),
                    change_direction=rel_data.get("change_direction", ""),
                    trigger_event=rel_data.get("trigger_event", ""),
                    scene_number=scene_number,
                ))

        # Subplots
        for sp_data in result.get("subplots", []):
            if not isinstance(sp_data, dict):
                continue
            existing = next(
                (s for s in bible.subplots if s.id == sp_data.get("id", "")),
                None,
            )
            if existing:
                if sp_data.get("status"):
                    existing.status = sp_data["status"]
                if sp_data.get("progress_note"):
                    existing.progress_note = sp_data["progress_note"]
            else:
                bible.subplots.append(SubplotItem(
                    id=sp_data.get("id", f"sp_{scene_number}"),
                    name=sp_data.get("name", ""),
                    status=sp_data.get("status", "進行中"),
                    progress_note=sp_data.get("progress_note", ""),
                    related_characters=sp_data.get("related_characters", []),
                    related_foreshadowing_ids=sp_data.get("related_foreshadowing_ids", []),
                ))

        # Glossary
        for g_data in result.get("glossary", []):
            if not isinstance(g_data, dict):
                continue
            term = g_data.get("term", "")
            if term:
                existing = next((g for g in bible.glossary if g.term == term), None)
                if existing:
                    existing.definition = g_data.get("definition", existing.definition)
                else:
                    bible.glossary.append(GlossaryItem(
                        term=term,
                        definition=g_data.get("definition", ""),
                    ))

        # World rules
        for r_data in result.get("world_rules", []):
            if not isinstance(r_data, dict):
                continue
            rule = r_data.get("rule", "")
            if rule and rule not in bible.world_rules:
                bible.world_rules.append(rule)

        self.save(bible)
