"""Scene writer for drafting, reviewing, and revising scenes.

Handles the full scene writing pipeline: draft → review → quality gate → revise.
Also manages scene summarization and Bible updates after each scene.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from novel_forge.bible_manager import BibleManager
from novel_forge.logging_config import get_logger
from novel_forge.models import (
    Bible,
    Fact,
    SceneRecord,
    SceneWriteContext,
    VolumeOutline,
)
from novel_forge.quality_gate import QualityGate
from novel_forge.schemas import get_schema
from novel_forge.storage import BibleStorage, BlackboardStorage


class SceneWriter:
    """Handles scene drafting, review, revision, and post-processing."""

    # Pre-compiled regex patterns for chapter assembly
    _RE_SCENE_MARKER_FULL = re.compile(r"^シーン\d+[\uff08\(]第\d+章[\uff09\)]\s*[：:]\s*")
    _RE_SCENE_MARKER_SIMPLE = re.compile(r"^シーン\d+\s*[：:]\s*")

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
        self._bible_cache: Bible | None = None
        self._log = get_logger("novel_forge.scene_writer")

    # ── Bible caching ──────────────────────────────────────────────────

    def _get_bible(self) -> Bible:
        """Get Bible, loading from storage only once per instance."""
        if self._bible_cache is None:
            self._bible_cache = self._bible_storage.load()
        return self._bible_cache

    def _invalidate_bible_cache(self) -> None:
        """Invalidate bible cache after updates."""
        self._bible_cache = None

    # ── Bible text helpers for prompts ─────────────────────────────────

    def _get_subplots_text(self) -> str:
        """Get current subplots as formatted text."""
        bible = self._get_bible()
        if not bible.subplots:
            return "（なし）"
        lines = []
        for sp in bible.subplots:
            if sp.status != "completed":
                lines.append(f"- {sp.name}: {sp.progress_note or '進捗なし'}")
        return "\n".join(lines) if lines else "（進行中のサブプロットなし）"

    def _get_relationships_text(self) -> str:
        """Get current character relationships as formatted text."""
        bible = self._get_bible()
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
        bible = self._get_bible()
        unresolved = [fh for fh in bible.foreshadowing if not fh.resolved]
        if not unresolved:
            return "（なし）"
        return "\n".join(f"- {fh.description}" for fh in unresolved)

    # ── main write pipeline ──────────────────────────────────────────

    def write_scene(
        self,
        design_obj: VolumeOutline,
        chapter,
        scene,
        record: SceneRecord,
        ctx: SceneWriteContext,
        log_fn=None,
    ) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": ctx.lang})
        context = ctx.build_context_fn()
        continuity = ctx.build_continuity_fn(record.scene_number, ctx.vol_num)

        # Draft
        self._log.info(
            "  [DRAFT START] vol%d ch%d sc%d", ctx.vol_num, chapter.number, record.scene_number
        )
        if log_fn:
            log_fn(f"  [DRAFT START] vol{ctx.vol_num} ch{chapter.number} sc{record.scene_number}")
        user = self._prompts.render(
            "scene_draft.md",
            {
                "series_plan": ctx.get_series_plan_summary_fn(),
                "outline": ctx.get_outline_summary_fn(design_obj),
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
        self._log.info(
            "  [DRAFT END] vol%d ch%d sc%d len=%d",
            ctx.vol_num,
            chapter.number,
            record.scene_number,
            len(draft_text),
        )
        if log_fn:
            log_fn(
                f"  [DRAFT END] vol{ctx.vol_num} ch{chapter.number} sc{record.scene_number} len={len(draft_text)}"
            )
        record.status = "初稿済"
        record.draft_version = 1
        draft_path = self.save_scene_draft(
            ctx.vol_num, record.scene_number, draft_text, chapter.number, version=1
        )
        record.draft_path = draft_path

        # Review → Quality Gate → revise loop
        draft_text, record = self._run_review_loop(
            draft_text, record, design_obj, scene, ctx, chapter.number, log_fn=log_fn
        )

        if record.status == "初稿済":
            self._log.warning(
                "  [WARNING] シーン%d: 品質ゲートループ後に初稿済のまま。強制出力済に変更。",
                record.scene_number,
            )
            record.status = "強制出力済"

        return {"scene_number": record.scene_number, "status": record.status}

    # ── review loop ───────────────────────────────────────────────────

    def _run_review_loop(
        self,
        draft_text: str,
        record: SceneRecord,
        design_obj: VolumeOutline,
        scene,
        ctx: SceneWriteContext,
        chapter_number: int,
        log_fn=None,
    ) -> tuple[str, SceneRecord]:
        """Run review → quality gate → revise loop. Returns (final_draft, updated_record)."""
        seed_offset = 0
        for retry in range(self._quality.max_retries):
            review = self._review_scene(
                draft_text,
                design_obj,
                scene,
                ctx.lang,
                ctx.build_context_fn,
                ctx.get_outline_summary_fn,
                seed_offset=seed_offset,
            )
            qg_result = self._quality.check_scene(review)
            record.quality_retries = retry + 1

            if qg_result.passed:
                record.status = "修正済"
                record.quality_gate = qg_result
                msg = f"  [REVIEW PASS] vol{ctx.vol_num} ch{chapter_number} sc{record.scene_number} issues={len(qg_result.issues)} retry={retry}"
                self._log.info(msg)
                if log_fn:
                    log_fn(msg)
                break

            if retry < self._quality.max_retries:
                msg = f"  [REVIEW FAIL] vol{ctx.vol_num} ch{chapter_number} sc{record.scene_number} blocker={qg_result.blocker_count} critical={qg_result.critical_count} major={qg_result.major_count} retry={retry}/{self._quality.max_retries}"
                self._log.warning(msg)
                if log_fn:
                    log_fn(msg)
                seed_offset += 1
                draft_text = self._revise_scene(
                    draft_text, review, ctx.lang, seed_offset=seed_offset
                )
                record.draft_version += 1
                draft_path = self.save_scene_draft(
                    ctx.vol_num,
                    record.scene_number,
                    draft_text,
                    chapter_number,
                    version=record.draft_version,
                )
                record.draft_path = draft_path
            else:
                record.status = "強制出力済"
                record.quality_gate = qg_result
                # 強制出力も版付きで保存
                record.draft_version += 1
                draft_path = self.save_scene_draft(
                    ctx.vol_num,
                    record.scene_number,
                    draft_text,
                    chapter_number,
                    version=record.draft_version,
                )
                record.draft_path = draft_path
                msg = f"  [REVIEW FORCED] vol{ctx.vol_num} ch{chapter_number} sc{record.scene_number} blocker={qg_result.blocker_count} critical={qg_result.critical_count} major={qg_result.major_count}"
                self._log.warning(msg)
                if log_fn:
                    log_fn(msg)

        return draft_text, record

    # ── review ───────────────────────────────────────────────────────

    def _review_scene(
        self,
        draft_text: str,
        design_obj: VolumeOutline,
        scene,
        lang: str,
        build_context_fn,
        get_outline_summary_fn,
        seed_offset: int = 0,
    ) -> dict:
        system = self._prompts.render("system.md", {"lang": lang})
        user = self._prompts.render(
            "scene_review.md",
            {
                "scene": draft_text,
                "outline": get_outline_summary_fn(design_obj),
                "context": build_context_fn(),
                "subplots": self._get_subplots_text(),
                "relationships": self._get_relationships_text(),
                "lang": lang,
            },
        )
        schema = get_schema("scene_review")
        self._log.info("  [REVIEW START]")
        # Retry up to 3 times on failure (timeout, parse error, etc.)
        for attempt in range(3):
            try:
                result = self._llm.complete_json(
                    "scene_review", system, user, schema, seed_offset=seed_offset
                )
                self._log.info("  [REVIEW DONE] issues=%d", len(result.get("issues", [])))
                return result
            except Exception as e:
                if attempt < 2:
                    self._log.warning("  [REVIEW RETRY] attempt %d/3: %s", attempt + 1, e)
                    continue
                raise
        return {"issues": [], "revision_needed": True}

    # ── revise ───────────────────────────────────────────────────────

    @staticmethod
    def _build_review_text(review: dict) -> str:
        """Build a human-readable review text from a review dict."""
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            sug = issue.get("suggestion", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
            if sug:
                lines.append(f"    提案: {sug}")
        return "\n".join(lines)

    def _revise_scene(self, draft_text: str, review: dict, lang: str, seed_offset: int = 0) -> str:
        system = self._prompts.render("system.md", {"lang": lang})
        review_text = self._build_review_text(review)
        user = self._prompts.render(
            "scene_revision.md",
            {
                "scene": draft_text,
                "review": review_text,
                "lang": lang,
            },
        )
        schema = get_schema("scene_draft")
        result = self._llm.complete_json(
            "scene_draft", system, user, schema, seed_offset=seed_offset
        )
        return result.get("content", draft_text)

    # ── summarize → blackboard update ───────────────────────────────

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
        self._invalidate_bible_cache()

    # ── bible update ─────────────────────────────────────────────────

    # ── scene draft I/O ──────────────────────────────────────────────

    def save_scene_draft(
        self,
        vol_num: int,
        scene_number: int,
        text: str,
        chapter_number: int = 1,
        version: int = 1,
    ) -> str:
        """シーン本文を保存し、ファイルパスを返す。

        版管理: version=1 → sc01_v1.md, version=2 → sc01_v2.md
        最終版: version=0 → sc01.md（assemble_chapter で使用）
        """
        vol_dir = self._series_dir / f"vol{vol_num:02d}"
        ch_dir = vol_dir / f"vol{vol_num:02d}_ch{chapter_number:02d}"
        ch_dir.mkdir(parents=True, exist_ok=True)

        if version > 0:
            fname = f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}_v{version}.md"
        else:
            fname = f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        path = ch_dir / fname
        path.write_text(text, encoding="utf-8")
        return str(path)

    def load_scene_draft(self, vol_num: int, scene_number: int, chapter_number: int = 1) -> str:
        """最新版のシーン本文を読み込む。

        優先順位: v2 > v1 > version=0（接尾辞なし）
        assemble_chapter が生成した最終版（version=0）も読める。
        """
        ch_dir = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{chapter_number:02d}"
        if not ch_dir.exists():
            return ""
        # 1. 最大バージョン付きファイルを探す（v1, v2, ...）
        max_version = 0
        for f in ch_dir.glob(f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}_v*.md"):
            try:
                v = int(f.stem.split("_v")[-1])
                if v > max_version:
                    max_version = v
            except ValueError:
                pass
        if max_version > 0:
            path = (
                ch_dir
                / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}_v{max_version}.md"
            )
            return path.read_text(encoding="utf-8")
        # 2. version=0（接尾辞なし）ファイルを探す
        plain = ch_dir / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        if plain.exists():
            return plain.read_text(encoding="utf-8")
        return ""

    # ── chapter assembly ─────────────────────────────────────────────

    def assemble_chapter(
        self, vol_num: int, chapter, scene_texts: list[str], scene_numbers: list[int] | None = None
    ) -> str:
        """章を組み立てて保存し、ファイルパスを返す。

        各シーンの最終版を version=0（接尾辞なし）でも保存する。
        scene_numbers: 各シーンの番号リスト。None の場合は 1, 2, ... を仮定。
        """
        vol_dir = self._series_dir / f"vol{vol_num:02d}"
        ch_dir = vol_dir / f"vol{vol_num:02d}_ch{chapter.number:02d}"
        ch_dir.mkdir(parents=True, exist_ok=True)

        # 各シーンの最終版を version=0 で保存
        if scene_numbers is None:
            scene_numbers = list(range(1, len(scene_texts) + 1))
        for sc_num, _text in zip(scene_numbers, scene_texts, strict=True):
            # 最新版の v*.md を探して、その内容で version=0 を保存
            max_version = 0
            for f in ch_dir.glob(f"vol{vol_num:02d}_ch{chapter.number:02d}_sc{sc_num:02d}_v*.md"):
                try:
                    v = int(f.stem.split("_v")[-1])
                    if v > max_version:
                        max_version = v
                except ValueError:
                    pass
            if max_version > 0:
                latest = (
                    ch_dir
                    / f"vol{vol_num:02d}_ch{chapter.number:02d}_sc{sc_num:02d}_v{max_version}.md"
                )
                final_path = ch_dir / f"vol{vol_num:02d}_ch{chapter.number:02d}_sc{sc_num:02d}.md"
                final_path.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")

        ch_path = ch_dir / f"vol{vol_num:02d}_ch{chapter.number:02d}.md"
        # Remove scene markers
        cleaned_texts = []
        for text in scene_texts:
            cleaned = self._RE_SCENE_MARKER_FULL.sub("", text.strip())
            cleaned = self._RE_SCENE_MARKER_SIMPLE.sub("", cleaned)
            cleaned_texts.append(cleaned)
        content = f"# {chapter.title}\n\n" + "\n\n---\n\n".join(cleaned_texts)
        ch_path.write_text(content, encoding="utf-8")
        return str(ch_path)
