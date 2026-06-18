"""Scene writer for drafting, reviewing, and revising scenes.

Handles the full scene writing pipeline: draft → review → quality gate → revise.
Also manages scene summarization and Bible updates after each scene.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from novel_forge.bible_manager import BibleManager
from novel_forge.models import (
    Bible,
    CharacterProfile,
    Fact,
    ForeshadowingItem,
    GlossaryItem,
    RelationshipItem,
    SceneRecord,
    SceneWriteContext,
    SubplotItem,
    VolumeOutline,
)
from novel_forge.quality_gate import QualityGate
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
        series_dir: Path | None = None,
    ):
        self._workdir = workdir
        self._series_dir = series_dir or workdir
        self._llm = llm_client
        self._prompts = prompt_manager
        self._quality = quality
        self._bb_storage = blackboard_storage
        self._bible_storage = bible_storage
        self._bible_mgr = BibleManager(bible_storage)

    def _get_subplots_text(self) -> str:
        """Get current subplots as formatted text."""
        bible = self._bible_storage.load()
        if not bible.subplots:
            return "（なし）"
        lines = []
        for sp in bible.subplots:
            if sp.status != "completed":
                lines.append(f"- [{sp.status}] {sp.name}: {sp.progress_note or '進捗なし'}")
        return "\n".join(lines) if lines else "（進行中のサブプロットなし）"

    def _get_relationships_text(self) -> str:
        """Get current character relationships as formatted text."""
        bible = self._bible_storage.load()
        if not bible.relationships:
            return "（なし）"
        lines = []
        for r in bible.relationships:
            lines.append(
                f"- {r.character_a} ↔ {r.character_b}: "
                f"{r.relationship_type or '関係未設定'} / 状態: {r.status or '未設定'}"
            )
        return "\n".join(lines)

    def _get_foreshadowing_to_resolve_text(self) -> str:
        """Get unresolved foreshadowing as formatted text."""
        bible = self._bible_storage.load()
        unresolved = [fh for fh in bible.foreshadowing if not fh.resolved]
        if not unresolved:
            return "（なし）"
        return "\n".join(f"- {fh.description}" for fh in unresolved)

    # ── main write pipeline ──────────────────────────────────────────

    def write_scene(
        self,
        outline: VolumeOutline,
        chapter,
        scene,
        record: SceneRecord,
        ctx: "SceneWriteContext",
    ) -> dict[str, Any]:
            system = self._prompts.render("system.md", {"lang": ctx.lang})
            context = ctx.build_context_fn()
            continuity = ctx.build_continuity_fn(record.scene_number, ctx.vol_num)

            # Draft
            user = self._prompts.render(
                "scene_draft.md",
                {
                    "series_plan": ctx.get_series_plan_summary_fn(),
                    "outline": ctx.get_outline_summary_fn(outline),
                    "scene": ctx.get_scene_summary_fn(scene),
                    "chapter_title": chapter.title,
                    "chapter_purpose": chapter.purpose,
                    "context": context,
                    "continuity": continuity,
                    "subplots": self._get_subplots_text(),
                    "relationships": self._get_relationships_text(),
                    "foreshadowing_to_resolve": self._get_foreshadowing_to_resolve_text(),
                    "lang": ctx.lang,
                },
            )
            draft_schema = get_schema("scene_draft")
            draft_result = self._llm.complete_json("scene_draft", system, user, draft_schema)
            draft_text = draft_result.get("content", "")
            record.status = "初稿済"
            self.save_scene_draft(ctx.vol_num, record.scene_number, draft_text, chapter.number)

            # Review → Quality Gate → revise loop (max 3 retries)
            for retry in range(self._quality.max_retries + 1):
                review = self._review_scene(
                    draft_text, outline, scene, ctx.lang, ctx.build_context_fn,
                    ctx.get_outline_summary_fn,
                )
                qg_result = self._quality.check_scene(review)
                record.quality_retries = retry + 1

                if qg_result.passed:
                    record.status = "修正済"
                    record.quality_gate = qg_result
                    break

                if retry < self._quality.max_retries:
                    lang_issues = self._extract_language_issues(review)
                    if lang_issues:
                        review["language_issues"] = lang_issues
                    draft_text = self._revise_scene(draft_text, review, ctx.lang)
                    self.save_scene_draft(ctx.vol_num, record.scene_number, draft_text, chapter.number)
                else:
                    record.status = "強制出力済"
                    record.quality_gate = qg_result

            if record.status == "初稿済":
                print(f"  [WARNING] シーン{record.scene_number}: 品質ゲートループ後に初稿済のまま。強制出力済に変更。", file=sys.stderr, flush=True)
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
                "subplots": self._get_subplots_text(),
                "relationships": self._get_relationships_text(),
                "lang": lang,
            },
        )
        schema = get_schema("scene_review")
        # Retry up to 3 times on failure (timeout, parse error, etc.)
        for attempt in range(3):
            try:
                result = self._llm.complete_json("scene_review", system, user, schema)
                if "score" in result:
                    return result
            except Exception as e:
                if attempt < 2:
                    print(f"  [REVIEW RETRY] attempt {attempt+1}/3: {e}", flush=True)
                    continue
                raise
        return {"score": 0, "issues": [], "dimensions": [], "revision_needed": True}

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
        schema = get_schema("scene_revision")
        result = self._llm.complete_json("scene_revision", system, user, schema)
        return result.get("content", draft_text)

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
            bb.facts.append(Fact(**fact_data))
        bb.continuity_notes.extend(result.get("continuity_notes", []))
        self._bb_storage.save(bb)

    def summarize_and_update_bible(
        self,
        scene_number: int,
        draft_text: str,
        lang: str,
        get_bible_text_fn,
    ) -> None:
        """Combined summarize + bible update in a single LLM call.

        Uses scene_summary_and_bible_update.md prompt to extract both
        scene summary and bible updates simultaneously, reducing
        LLM calls from 2 to 1 per scene.
        """
        system = self._prompts.render("system.md", {"lang": lang})
        current_bible_text = get_bible_text_fn()

        user = self._prompts.render(
            "scene_summary_and_bible_update.md",
            {
                "scene": draft_text,
                "current_bible": current_bible_text,
                "lang": lang,
            },
        )
        schema = get_schema("scene_summary_and_bible_update")
        result = self._llm.complete_json("scene_summary_and_bible_update", system, user, schema)

        # Update blackboard (summary + facts + continuity)
        bb = self._bb_storage.load()
        bb.scene_summaries[str(scene_number)] = result.get("summary", "")
        for fact_data in result.get("facts", []):
            bb.facts.append(Fact(**fact_data))
        bb.continuity_notes.extend(result.get("continuity_notes", []))
        self._bb_storage.save(bb)

        # Update bible (delegated to BibleManager)
        self._bible_mgr.apply_update(result, scene_number)

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

        self._bible_mgr.apply_update(result, scene_number)

    # ── scene draft I/O ──────────────────────────────────────────────

    def save_scene_draft(
        self, vol_num: int, scene_number: int, text: str, chapter_number: int = 1
    ) -> None:
        path = (
            self._series_dir
            / f"vol{vol_num:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def load_scene_draft(
        self, vol_num: int, scene_number: int, chapter_number: int = 1
    ) -> str:
        path = (
            self._series_dir
            / f"vol{vol_num:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}"
            / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        )
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    # ── chapter assembly ─────────────────────────────────────────────

    def assemble_chapter(
        self, vol_num: int, chapter, scene_texts: list[str]
    ) -> None:
        import re
        vol_dir = self._series_dir / f"vol{vol_num:02d}"
        ch_path = vol_dir / f"vol{vol_num:02d}_ch{chapter.number:02d}" / f"vol{vol_num:02d}_ch{chapter.number:02d}.md"
        ch_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove scene markers like "シーンX（第Y章）:" or "シーンX:" from the beginning of each scene
        cleaned_texts = []
        for text in scene_texts:
            # Remove lines like "シーン1（第2章）:" or "シーン5:" at the start
            cleaned = re.sub(r'^シーン\d+（第\d+章）?[：:]\s*', '', text.strip())
            cleaned_texts.append(cleaned)
        content = f"# {chapter.title}\n\n" + "\n\n---\n\n".join(cleaned_texts)
        ch_path.write_text(content, encoding="utf-8")
