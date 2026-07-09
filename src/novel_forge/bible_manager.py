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

    # ── unresolved items ────────────────────────────────────────────

    def get_unresolved_foreshadowing(self) -> list[ForeshadowingItem]:
        return [fh for fh in self.bible.foreshadowing if not fh.resolved]

    def get_incomplete_subplots(self) -> list[SubplotItem]:
        return [sp for sp in self.bible.subplots if sp.status not in {"完了", "completed"}]

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
        bible = self.bible
        context = context or {}
        lines: list[str] = []

        if stage in ("volume", "chapter", "scene"):
            if bible.world_rules:
                lines.append("## 世界観ルール（遵守）")
                for rule in bible.world_rules:
                    lines.append(f"  - {rule}")

        if stage == "volume":
            if bible.subplots:
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
                (
                    c
                    for c in bible.characters
                    if c.name == new_name
                    or (len(new_name) >= 2 and new_name in c.name)
                    or (len(c.name) >= 2 and c.name in new_name)
                ),
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
                bible.characters.append(
                    CharacterProfile(
                        name=ch_data.get("name", ""),
                        role=ch_data.get("role", ""),
                        personality=ch_data.get("personality", ""),
                        appearance=ch_data.get("appearance", ""),
                        motivation=ch_data.get("motivation", ""),
                        flaw=ch_data.get("flaw", ""),
                        age=ch_data.get("age", ""),
                        occupation=ch_data.get("occupation", ""),
                        background=ch_data.get("background", ""),
                        arc=ch_data.get("arc") or "",
                    )
                )

        # Foreshadowing
        for fh_data in result.get("foreshadowing", []):
            if not isinstance(fh_data, dict):
                continue
            fh_type = fh_data.get("type", "設置")
            if fh_type in {"回収", "resolution"}:
                for fh in bible.foreshadowing:
                    if not fh.resolved and fh.description == fh_data.get("description", ""):
                        fh.resolved = True
                        break
            else:
                desc = fh_data.get("description", "").strip()
                if desc and desc not in {f.description.strip() for f in bible.foreshadowing}:
                    bible.foreshadowing.append(
                        ForeshadowingItem(
                            description=desc,
                            resolved=False,
                        )
                    )

        # Relationships
        for rel_data in result.get("relationships", []):
            if not isinstance(rel_data, dict):
                continue
            existing_rel = next(
                (
                    r
                    for r in bible.relationships
                    if {r.character_a, r.character_b}
                    == {
                        rel_data.get("character_a", ""),
                        rel_data.get("character_b", ""),
                    }
                ),
                None,
            )
            relationship_type = rel_data.get("relationship_type") or rel_data.get("type", "")
            if existing_rel:
                if relationship_type:
                    existing_rel.relationship_type = relationship_type
                if rel_data.get("change_direction"):
                    existing_rel.change_direction = rel_data["change_direction"]
                if rel_data.get("trigger_event"):
                    existing_rel.trigger_event = rel_data["trigger_event"]
                existing_rel.scene_number = scene_number
            else:
                bible.relationships.append(
                    RelationshipItem(
                        character_a=rel_data.get("character_a", ""),
                        character_b=rel_data.get("character_b", ""),
                        relationship_type=relationship_type,
                        change_direction=rel_data.get("change_direction", ""),
                        trigger_event=rel_data.get("trigger_event", ""),
                        scene_number=scene_number,
                    )
                )

        # Subplots
        for sp_data in result.get("subplots", []):
            if not isinstance(sp_data, dict):
                continue
            existing_subplot = next(
                (s for s in bible.subplots if s.id == sp_data.get("id", "")),
                None,
            )
            if existing_subplot:
                if sp_data.get("status"):
                    existing_subplot.status = sp_data["status"]
                if sp_data.get("progress_note"):
                    existing_subplot.progress_note = sp_data["progress_note"]
            else:
                bible.subplots.append(
                    SubplotItem(
                        id=sp_data.get("id", f"sp_{scene_number}"),
                        name=sp_data.get("name", ""),
                        status=sp_data.get("status", "進行中"),
                        progress_note=sp_data.get("progress_note", ""),
                        related_characters=sp_data.get("related_characters", []),
                        related_foreshadowing_ids=sp_data.get("related_foreshadowing_ids", []),
                    )
                )

        # Glossary
        for g_data in result.get("glossary", []):
            if not isinstance(g_data, dict):
                continue
            term = g_data.get("term", "")
            if term:
                existing_glossary = next((g for g in bible.glossary if g.term == term), None)
                if existing_glossary:
                    existing_glossary.definition = g_data.get("definition", existing_glossary.definition)
                else:
                    bible.glossary.append(
                        GlossaryItem(
                            term=term,
                            definition=g_data.get("definition", ""),
                        )
                    )

        # World rules
        for r_data in result.get("world_rules", []):
            if isinstance(r_data, str):
                rule = r_data.strip()
            elif isinstance(r_data, dict):
                # Backward compatibility with older outputs that used {"rule": "..."}.
                rule = str(r_data.get("rule", "")).strip()
            else:
                continue
            if rule and rule not in bible.world_rules:
                bible.world_rules.append(rule)

        self.save(bible)

    # ── apply design update (intentional, from design stage) ─────────

    def apply_design_update(
        self,
        stage: str,
        data: dict,
        context: dict | None = None,
    ) -> None:
        """Apply a design-stage update to Bible (intentional, idempotent).

        Unlike ``apply_update`` (which is driven by runtime draft extraction in
        write), this is driven by the design-stage *intent*: the design directly
        declares what it plants / resolves. Called after a scene/chapter/volume
        design is confirmed (review passed). Never reads draft text.

        Idempotency:
          - characters: matched by name; update in place, append if new.
          - foreshadowing (setup): keyed by ``description``; skip if already present.
          - foreshadowing (resolve): matched by ``description`` or ``id``; set resolved=True.
          - subplots: keyed by ``id``; update status/note in place, append if new.

        Args:
            stage: "scene" | "chapter" | "volume"
            data: design object as dict (SceneDesign / ChapterDesign / VolumeDesign).
            context: optional dict with keys like ``vol_num``, ``ch_num``, ``sc_num``.
        """
        bible = self.bible
        context = context or {}
        loc = (
            f"vol{context.get('vol_num', '?')}"
            f"/ch{context.get('ch_num', '?')}"
            f"/sc{context.get('sc_num', '?')}"
        )

        if stage == "scene":
            # 1. characters: update state / add new
            for name in data.get("characters", []) or []:
                if not isinstance(name, str) or not name.strip():
                    continue
                name = name.strip()
                existing = next((c for c in bible.characters if c.name == name), None)
                if existing:
                    # design は状態変化を意図して渡すので、state を上書き（冪等）
                    if data.get("notes"):
                        existing.state = data["notes"]
                else:
                    bible.characters.append(
                        CharacterProfile(name=name, state=data.get("notes", "") or "")
                    )

            # 2. foreshadowing setup: append if not already present (keyed by description)
            existing_descs = {f.description.strip() for f in bible.foreshadowing}
            for desc in data.get("foreshadowing", []) or []:
                if not isinstance(desc, str) or not desc.strip():
                    continue
                desc = desc.strip()
                if desc not in existing_descs:
                    bible.foreshadowing.append(
                        ForeshadowingItem(description=desc, resolved=False)
                    )
                    existing_descs.add(desc)

            # 3. resolves_foreshadowing: explicit resolution by description or id
            for key in data.get("resolves_foreshadowing", []) or []:
                if not isinstance(key, str) or not key.strip():
                    continue
                key = key.strip()
                for fh in bible.foreshadowing:
                    if not fh.resolved and (
                        fh.description.strip() == key
                        or fh.description.strip().endswith(key)
                        or key in fh.description.strip()
                    ):
                        fh.resolved = True
                        break

        elif stage == "chapter":
            # foreshadowing_notes → setup (idempotent by description)
            existing_descs = {f.description.strip() for f in bible.foreshadowing}
            for desc in data.get("foreshadowing_notes", []) or []:
                if not isinstance(desc, str) or not desc.strip():
                    continue
                desc = desc.strip()
                if desc not in existing_descs:
                    bible.foreshadowing.append(
                        ForeshadowingItem(description=desc, resolved=False)
                    )
                    existing_descs.add(desc)

            # subplot_notes → subplots (idempotent by name)
            existing_names = {s.name for s in bible.subplots}
            for note in data.get("subplot_notes", []) or []:
                if not isinstance(note, str) or not note.strip():
                    continue
                note = note.strip()
                if note not in existing_names:
                    bible.subplots.append(
                        SubplotItem(
                            id=f"sp_{len(bible.subplots) + 1:03d}",
                            name=note,
                            status="進行中",
                            progress_note=note,
                        )
                    )
                    existing_names.add(note)

        elif stage == "volume":
            # volume design intent: keep subplots progressing.
            # premise/logline は series_plan からの引き継ぎなのでここでは上書きしない。
            pass

        self.save(bible)
