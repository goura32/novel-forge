"""Scene writing — write method for NovelEngine."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from novel_forge.logging_config import console

from novel_forge.models import VolumeOutline, SceneWriteContext

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase
else:
    NovelEngineBase = object


class WriteMixin(NovelEngineBase):  # type: ignore[misc]
    """Scene writing methods for NovelEngine."""

    def write(self, volume_number: int | None = None, log_fn=None) -> list[dict[str, Any]]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        slug = getattr(self, "_slug", "?")
        series_title = getattr(self, "_state", None)
        series_title = series_title.series_title if series_title else "?"
        self._log.info(f"Write started: series='{series_title}' volume={vol_num} slug='{slug}'")
        design_data = self._load_path(vol_num, f"vol{vol_num:02d}.json")
        design_obj = VolumeOutline(**design_data)

        # Deduplicate chapters
        seen_chapters = {}
        for ch in design_obj.chapters:
            if ch.number not in seen_chapters:
                seen_chapters[ch.number] = ch
        design_obj.chapters = sorted(seen_chapters.values(), key=lambda c: c.number)

        vol = self._current_volume()
        vol.status = "執筆中"
        results = []

        # Count total scenes
        total_scenes = len(design_obj.scenes)
        done_scenes = 0
        skipped_scenes = 0
        start_time = time.time()

        def _progress(scene_num: int, status: str):
            nonlocal done_scenes, skipped_scenes
            elapsed = time.time() - start_time
            if status.startswith("スキップ"):
                skipped_scenes += 1
            else:
                done_scenes += 1
            completed = done_scenes + skipped_scenes
            avg = elapsed / completed if completed > 0 else 0
            remaining = avg * (total_scenes - completed)
            elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
            remaining_str = f"{int(remaining // 60)}m {int(remaining % 60)}s"
            pct = completed / total_scenes * 100 if total_scenes > 0 else 0
            bar_len = 20
            filled = int(bar_len * completed / total_scenes) if total_scenes > 0 else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            console.print(
                f"  [{bar}] {pct:5.1f}% "
                f"({completed}/{total_scenes}) "
                f"{status} "
                f"経過: {elapsed_str} "
                f"残り推定: {remaining_str}"
            )

        for chapter in design_obj.chapters:
            chapter_scenes: list[str] = []
            chapter_scene_numbers: list[int] = []
            ch_scenes = [s for s in design_obj.scenes if s.chapter_number == chapter.number]
            self._log.info(f"  [CHAPTER START] vol{vol_num} ch{chapter.number} title='{chapter.title}' scenes={len(ch_scenes)}")
            for scene in ch_scenes:
                record = self._get_or_create_scene_record(vol, scene.number)
                if record.status in ("修正済", "強制出力済"):
                    chapter_scenes.append(
                        self._scene_writer.load_scene_draft(
                            vol_num, scene.number, chapter.number
                        )
                    )
                    chapter_scene_numbers.append(scene.number)
                    _progress(scene.number, "スキップ(済)")
                    continue
                self._log.info(f"  [SCENE START] vol{vol_num} ch{chapter.number} sc{scene.number} title='{scene.title}'")
                result = self._scene_writer.write_scene(
                    design_obj=design_obj,
                    chapter=chapter,
                    scene=scene,
                    record=record,
                    ctx=SceneWriteContext(
                        lang=self._lang,
                        vol_num=vol_num,
                        build_context_fn=self._ctx_builder.build_context,
                        build_continuity_fn=lambda sn, vn: self._ctx_builder.build_continuity(
                            sn, vn, self._scene_writer.load_scene_draft
                        ),
                        get_series_plan_summary_fn=self._ctx_builder.get_series_plan_summary,
                        get_outline_summary_fn=self._ctx_builder.get_outline_summary,
                        get_scene_summary_fn=self._ctx_builder.get_scene_summary,
                        get_bible_text_fn=self._bible_mgr.to_text,
                        load_scene_draft_fn=self._scene_writer.load_scene_draft,
                    ),
                    log_fn=log_fn,
                )
                results.append(result)
                draft_text = self._scene_writer.load_scene_draft(
                    vol_num, scene.number, chapter.number
                )
                chapter_scenes.append(draft_text)
                chapter_scene_numbers.append(scene.number)
                # Post-scene: summarize + bible update (1 LLM call)
                self._log.info(f"  [SUMMARY START] vol{vol_num} ch{chapter.number} sc{scene.number}")
                self._scene_writer.summarize_and_update_bible(
                    record.scene_number,
                    draft_text,
                    self._lang,
                    self._bible_mgr.to_text,
                )
                self._log.info(f"  [SUMMARY END] vol{vol_num} ch{chapter.number} sc{scene.number}")
                _progress(scene.number, f"完了")
                _save = getattr(self, "_save", None)
                if _save:
                    _save()

            self._scene_writer.assemble_chapter(vol_num, chapter, chapter_scenes, chapter_scene_numbers)
            self._log.info(f"  [CHAPTER END] vol{vol_num} ch{chapter.number} title='{chapter.title}'")

        vol.status = "初稿済"
        _state = getattr(self, "_state", None)
        if _state:
            _state.status = "初稿済"
        _save = getattr(self, "_save", None)
        if _save:
            _save()
        elapsed_total = time.time() - start_time
        self._log.info(f"Write finished: series='{series_title}' volume={vol_num} slug='{slug}' scenes={total_scenes} done={done_scenes} skipped={skipped_scenes} elapsed={int(elapsed_total)}s")
        return results
