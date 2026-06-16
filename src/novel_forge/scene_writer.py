"""Scene writer for drafting, reviewing, and revising scenes.

Handles the full scene writing pipeline: draft → review → quality gate → revise.
Also manages scene summarization and Bible updates after each scene.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from novel_forge.models import (
    Bible,
    CharacterProfile,
    ForeshadowingItem,
    GlossaryItem,
    RelationshipItem,
    SceneRecord,
    SubplotItem,
    VolumeOutline,
)
from novel_forge.quality import QualityGate
from novel_forge.schemas import get_schema
from novel_forge.storage import BlackboardStorage, BibleStorage


class SceneWriter:
    """Handles scene drafting, review, revision, and post-processing."""

    def __init__(
        self,
        workdir: Path,
        llm_client,
        prompt_manager,
        quality: QualityGate,
        blackboard_storage: BlackboardStorage,
        bible_storage: BibleStorage,
    ):
        self._workdir = workdir
        self._llm = llm_client
        self._prompts = prompt_manager
        self._quality = quality
        self._bb_storage = blackboard_storage
        self._bible_storage = bible_storage

    # ── main write pipeline ──────────────────────────────────────────

    def write_scene(
        self,
        outline: VolumeOutline,
        chapter,
        scene,
        record: SceneRecord,
        vol_num: int,
        lang: str,
        build_context_fn,
        build_continuity_fn,
        get_series_plan_summary_fn,
        get_outline_summary_fn,
        get_scene_summary_fn,
        load_scene_draft_fn=None,
    ) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": lang})
        context = build_context_fn()
        continuity = build_continuity_fn(record.scene_number, vol_num, load_scene_draft_fn)

        # Draft
        user = self._prompts.render(
            "scene_draft.md",
            {
                "series_plan": get_series_plan_summary_fn(),
                "outline": get_outline_summary_fn(outline),
                "scene": get_scene_summary_fn(scene),
                "context": context,
                "continuity": continuity,
                "lang": lang,
            },
        )
        draft_text = self._llm.complete_text("scene_draft", system, user)
        draft_text = self._post_process_text(draft_text)
        record.status = "初稿済"
        self.save_scene_draft(vol_num, record.scene_number, draft_text, chapter.number)

        # Review → Quality Gate → revise loop (max 3 retries)
        kanji_retries = 0
        for retry in range(QualityGate.MAX_RETRIES + 1):
            review = self._review_scene(
                draft_text, outline, scene, lang, build_context_fn,
                get_outline_summary_fn,
            )
            qg_result = self._quality.check_scene(review)
            record.quality_retries = retry + 1

            if qg_result.passed:
                non_jp_kanji = self._quality.check_kanji(draft_text)
                if not non_jp_kanji:
                    record.status = "修正済"
                    record.quality_gate = qg_result
                    break
                kanji_retries += 1
                if kanji_retries <= 2:
                    review["kanji_issues"] = list(set(non_jp_kanji))
                    draft_text = self._revise_scene(draft_text, review, lang)
                    draft_text = self._post_process_text(draft_text)
                    self.save_scene_draft(vol_num, record.scene_number, draft_text, chapter.number)
                    continue
                else:
                    record.status = "強制出力済"
                    record.quality_gate = qg_result
                    break

            if retry < QualityGate.MAX_RETRIES:
                lang_issues = self._extract_language_issues(review)
                if lang_issues:
                    review["language_issues"] = lang_issues
                draft_text = self._revise_scene(draft_text, review, lang)
                draft_text = self._post_process_text(draft_text)
                self.save_scene_draft(vol_num, record.scene_number, draft_text, chapter.number)
            else:
                record.status = "強制出力済"
                record.quality_gate = qg_result

        if record.status == "初稿済":
            record.status = "強制出力済"

        return {"scene_number": record.scene_number, "status": record.status}

    # ── review ───────────────────────────────────────────────────────

    def _review_scene(
        self,
        draft_text: str,
        outline: VolumeOutline,
        scene,
        lang: str,
        build_context_fn,
        get_outline_summary_fn,
    ) -> dict:
        system = self._prompts.render("system.md", {"lang": lang})
        user = self._prompts.render(
            "scene_review.md",
            {
                "scene": draft_text,
                "outline": get_outline_summary_fn(outline),
                "context": build_context_fn(),
                "lang": lang,
            },
        )
        schema = get_schema("scene_review")
        return self._llm.complete_json("scene_review", system, user, schema)

    # ── language issue extraction ────────────────────────────────────

    def _extract_language_issues(self, review: dict) -> list[str]:
        issues = review.get("issues", [])
        lang_issues = []
        for issue in issues:
            desc = issue.get("description", "")
            if any(kw in desc for kw in [
                "言語", "英語", "簡体字", "ハングル", "中国語",
                "language_purity", "langue",
            ]):
                lang_issues.append(desc)
        return lang_issues

    # ── post-process ─────────────────────────────────────────────────

    def _post_process_text(self, text: str) -> str:
        # Build translation table once (class-level would be better but
        # keeps it simple for now)
        if not hasattr(self, "_kanji_table"):
            replacements = [
                ('标记', '標識'), ('诊所', '診療所'), ('搜索', '捜索'),
                ('调查', '調査'), ('转', '転'), ('间', '間'),
                ('门', '門'), ('东', '東'), ('车', '車'),
                ('马', '馬'), ('鱼', '魚'), ('鸟', '鳥'), ('龙', '龍'),
            ]
            self._kanji_table = str.maketrans(
                {k[0]: v[0] for k, v in replacements if len(k) == 1 and len(v) == 1}
            )
            self._kanji_multi = [(k, v) for k, v in replacements if len(k) > 1]
        text = text.translate(self._kanji_table)
        for simp, jpn in self._kanji_multi:
            text = text.replace(simp, jpn)
        return text

    # ── revise ───────────────────────────────────────────────────────

    def _revise_scene(self, draft_text: str, review: dict, lang: str) -> str:
        system = self._prompts.render("system.md", {"lang": lang})
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            sug = issue.get("suggestion", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
            if sug:
                lines.append(f"    提案: {sug}")
        for s in review.get("strengths", []):
            lines.append(f"  強み: {s}")
        for r in review.get("recommendations", []):
            lines.append(f"  推奨: {r}")
        if review.get("kanji_issues"):
            lines.append(f"  簡体字問題: {', '.join(review['kanji_issues'])}")
        if review.get("language_issues"):
            lines.append(f"  言語問題: {'; '.join(review['language_issues'])}")
        review_text = "\n".join(lines)
        user = self._prompts.render(
            "scene_revision.md",
            {
                "scene": draft_text,
                "review": review_text,
                "lang": lang,
            },
        )
        return self._llm.complete_text("scene_revision", system, user)

    # ── summarize → blackboard update ───────────────────────────────

    def summarize_scene(self, scene_number: int, draft_text: str, lang: str) -> None:
        system = self._prompts.render("system.md", {"lang": lang})
        user = self._prompts.render(
            "scene_summary.md",
            {"scene": draft_text, "lang": lang},
        )
        schema = get_schema("scene_summary")
        result = self._llm.complete_json("scene_summary", system, user, schema)
        bb = self._bb_storage.load()
        bb.scene_summaries[str(scene_number)] = result.get("summary", "")
        for fact_data in result.get("facts", []):
            from novel_forge.models import Fact
            bb.facts.append(Fact(**fact_data))
        bb.continuity_notes.extend(result.get("continuity_notes", []))
        self._bb_storage.save(bb)

    # ── bible update ─────────────────────────────────────────────────

    def update_bible_from_scene(
        self,
        scene_number: int,
        draft_text: str,
        lang: str,
        get_bible_text_fn,
    ) -> None:
        system = self._prompts.render("system.md", {"lang": lang})
        current_bible_text = get_bible_text_fn()

        user = self._prompts.render(
            "bible_update.md",
            {
                "scene_text": draft_text,
                "current_bible": current_bible_text,
                "lang": lang,
            },
        )
        schema = get_schema("bible_update")
        result = self._llm.complete_json("bible_update", system, user, schema)

        bible = self._bible_storage.load()

        # Characters
        for ch_data in result.get("characters", []):
            existing = next(
                (c for c in bible.characters if c.name == ch_data.get("name", "")),
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
                    arc=ch_data.get("arc", ""),
                ))

        # Foreshadowing
        for fh_data in result.get("foreshadowing", []):
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
            existing = next(
                (r for r in bible.relationships
                 if {r.character_a, r.character_b} == {
                     rel_data.get("character_a", ""),
                     rel_data.get("character_b", ""),
                 }),
                None,
            )
            if existing:
                if rel_data.get("type"):
                    existing.relationship_type = rel_data["type"]
                if rel_data.get("change_direction"):
                    existing.change_direction = rel_data["change_direction"]
                if rel_data.get("trigger_event"):
                    existing.trigger_event = rel_data["trigger_event"]
                existing.scene_number = scene_number
            else:
                bible.relationships.append(RelationshipItem(
                    character_a=rel_data.get("character_a", ""),
                    character_b=rel_data.get("character_b", ""),
                    relationship_type=rel_data.get("type", ""),
                    change_direction=rel_data.get("change_direction", ""),
                    trigger_event=rel_data.get("trigger_event", ""),
                    scene_number=scene_number,
                ))

        # Subplots
        for sp_data in result.get("subplots", []):
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
                    status=sp_data.get("status", "in_progress"),
                    progress_note=sp_data.get("progress_note", ""),
                    related_characters=sp_data.get("related_characters", []),
                    related_foreshadowing_ids=sp_data.get("related_foreshadowing_ids", []),
                ))

        # Glossary
        for g_data in result.get("glossary", []):
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
            rule = r_data.get("rule", "")
            if rule and rule not in bible.world_rules:
                bible.world_rules.append(rule)

        self._bible_storage.save(bible)

        # Sync subplots to blackboard
        bb = self._bb_storage.load()
        if result.get("subplots"):
            for sp_data in result["subplots"]:
                existing = next(
                    (s for s in bb.subplots if s.id == sp_data.get("id", "")),
                    None,
                )
                if existing:
                    if sp_data.get("status"):
                        existing.status = sp_data["status"]
                    if sp_data.get("progress_note"):
                        existing.progress_note = sp_data["progress_note"]
                else:
                    bb.subplots.append(SubplotItem(
                        id=sp_data.get("id", f"sp_{scene_number}"),
                        name=sp_data.get("name", ""),
                        status=sp_data.get("status", "in_progress"),
                        progress_note=sp_data.get("progress_note", ""),
                    ))
            self._bb_storage.save(bb)

    # ── scene draft I/O ──────────────────────────────────────────────

    def save_scene_draft(
        self, vol_num: int, scene_number: int, text: str, chapter_number: int = 1
    ) -> None:
        path = (
            self._workdir
            / ".novel-forge"
            / "volumes"
            / f"vol{vol_num:02d}"
            / "scenes"
            / f"ch{chapter_number:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def load_scene_draft(
        self, vol_num: int, scene_number: int, chapter_number: int = 1
    ) -> str:
        path = (
            self._workdir
            / ".novel-forge"
            / "volumes"
            / f"vol{vol_num:02d}"
            / "scenes"
            / f"ch{chapter_number:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        )
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    # ── chapter assembly ─────────────────────────────────────────────

    def assemble_chapter(
        self, vol_num: int, chapter, scene_texts: list[str]
    ) -> None:
        vol_dir = self._workdir / ".novel-forge" / "volumes" / f"vol{vol_num:02d}"
        ch_path = vol_dir / "chapters" / f"ch{chapter.number:02d}.md"
        ch_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"# {chapter.title}\n\n" + "\n\n---\n\n".join(scene_texts)
        ch_path.write_text(content, encoding="utf-8")
