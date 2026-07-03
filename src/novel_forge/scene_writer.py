"""Scene writer for drafting, reviewing, and revising scenes.

Handles the full scene writing pipeline: draft -> review -> quality gate -> revise.
Also manages scene summarization and Bible updates after each scene.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from novel_forge.bible_manager import BibleManager
from novel_forge.engine.review import format_review_text, generate_and_review
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
        self._strict = False

    # -- Bible helpers --

    def _get_bible(self) -> Bible:
        if self._bible_cache is None:
            self._bible_cache = self._bible_storage.load()
        return self._bible_cache

    def _invalidate_bible_cache(self) -> None:
        self._bible_cache = None

    def _get_subplots_text(self) -> str:
        bible = self._get_bible()
        if not bible.subplots:
            return "（なし）"
        lines = []
        for sp in bible.subplots:
            if sp.status != "completed":
                lines.append(f"- {sp.name}: {sp.progress_note or '進捗なし'}")
        return "\n".join(lines) if lines else "（進行中のサブプロットなし）"

    def _get_relationships_text(self) -> str:
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
        bible = self._get_bible()
        unresolved = [fh for fh in bible.foreshadowing if not fh.resolved]
        if not unresolved:
            return "（なし）"
        return "\n".join(f"- {fh.description}" for fh in unresolved)

    # -- main pipeline --
    def write_scene(
        self,
        design_obj: VolumeOutline,
        chapter,
        scene,
        record: SceneRecord,
        ctx: SceneWriteContext,
    ) -> dict[str, Any]:
        """Write scene drafts for a volume using generate_and_review."""
        system = self._prompts.render("system.md", {"lang": ctx.lang})
        user = self._prompts.render(
            "scene_draft.md",
            {
                "series_plan": ctx.get_series_plan_summary_fn(),
                "outline": ctx.get_outline_summary_fn(design_obj),
                "scene": ctx.get_scene_summary_fn(scene),
                "chapter_title": chapter.title,
                "chapter_purpose": chapter.purpose,
                "context": ctx.build_context_fn(),
                "continuity": ctx.build_continuity_fn(record.scene_number, ctx.vol_num),
                "subplots": self._get_subplots_text(),
                "relationships": self._get_relationships_text(),
                "foreshadowing_to_resolve": self._get_foreshadowing_to_resolve_text(),
                "lang": ctx.lang,
            },
        )

        def _generate_fn(prompt, seed_offset):
            result = self._llm.complete_json(
                "scene_draft", system, prompt, get_schema("scene_draft"), seed_offset=seed_offset
            )
            return result

        def _validate_fn(result: dict) -> list[str]:
            errors = []
            content = result.get("content", "")
            if len(content) < 3000:
                errors.append(f"content too short ({len(content)} < 3000)")
            return errors

        def _review_fn(result: dict, sys: str) -> dict:
            return self._call_review_api(result.get("content", ""), design_obj, scene, ctx)

        def _revise_fn(result: dict, review: dict, sys: str, seed_offset: int = 0) -> dict:
            revised_text = self._revise_scene(result.get("content", ""), review, ctx.lang, seed_offset=seed_offset)
            return {"content": revised_text}

        draft_result, review = generate_and_review(
            generate_fn=_generate_fn,
            validate_fn=_validate_fn,
            review_fn=_review_fn,
            revise_fn=_revise_fn,
            system=system,
            user_prompt=user,
            kind="scene_draft",
            llm=self._llm,
            quality=self._quality,
        )

        # Determine final status from review
        qg_result = self._quality.check_scene(review)
        if qg_result.passed:
            record.status = "修正済"
        else:
            record.status = "強制出力済"

        record.draft_version = 1
        record.draft_path = self.save_scene_draft(
            ctx.vol_num, record.scene_number, draft_result.get("content", ""), chapter.number, version=1
        )
        record.quality_retries = 1
        record.quality_gate = qg_result

        return {"scene_number": record.scene_number, "status": record.status}

    def _call_review_api(
        self,
        draft_text: str,
        design_obj: VolumeOutline,
        scene,
        ctx: SceneWriteContext,
    ) -> dict:
        """review API を呼び出す。リトライは3回まで。"""
        system = self._prompts.render("system.md", {"lang": ctx.lang})
        user = self._prompts.render(
            "scene_review.md",
            {
                "scene": draft_text,
                "outline": ctx.get_outline_summary_fn(design_obj),
                "context": ctx.build_context_fn(),
                "subplots": self._get_subplots_text(),
                "relationships": self._get_relationships_text(),
                "lang": ctx.lang,
            },
        )
        schema = get_schema("review")
        self._log.info("  [REVIEW START]")
        for attempt in range(3):
            try:
                result = self._llm.complete_json(
                    "scene_review", system, user, schema, seed_offset=0
                )
                self._log.info("  [REVIEW DONE] issues=%d", len(result.get("issues", [])))
                return result
            except Exception as e:
                if attempt < 2:
                    self._log.warning("  [REVIEW RETRY] attempt %d/3: %s", attempt + 1, e)
                    continue
                raise
        return {"issues": [], "revision_needed": True}

    # -- revise --

    def _revise_scene(self, draft_text: str, review: dict, lang: str, seed_offset: int = 0) -> str:
        system = self._prompts.render("system.md", {"lang": lang})
        review_text = format_review_text(review)
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

    # -- summarize --

    def summarize_and_update_bible(
        self,
        scene_number: int,
        draft_text: str,
        lang: str,
        get_bible_text_fn,
    ) -> None:
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

        bb = self._bb_storage.load()
        bb.scene_summaries[str(scene_number)] = result.get("summary", "")
        for fact_data in result.get("facts", []):
            bb.facts.append(Fact(**fact_data))
        bb.continuity_notes.extend(result.get("continuity_notes", []))
        self._bb_storage.save(bb)

        self._bible_mgr.apply_update(result, scene_number)
        self._invalidate_bible_cache()

    # -- file I/O --

    def save_scene_draft(
        self,
        vol_num: int,
        scene_number: int,
        text: str,
        chapter_number: int = 1,
        version: int = 1,
    ) -> str:
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
        ch_dir = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{chapter_number:02d}"
        if not ch_dir.exists():
            return ""
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
        plain = ch_dir / f"vol{vol_num:02d}_ch{chapter_number:02d}_sc{scene_number:02d}.md"
        if plain.exists():
            return plain.read_text(encoding="utf-8")
        return ""


