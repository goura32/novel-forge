"""Scene writing — write method for NovelEngine."""

from __future__ import annotations

from typing import Any

from novel_forge.models import VolumeOutline, SceneWriteContext


class WriteMixin:
    """Scene writing methods for NovelEngine."""

    def write(self, volume_number: int | None = None, log_fn=None) -> list[dict[str, Any]]:
        import time as _time
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        outline_data = self._load_path(vol_num, "design.json")
        outline = VolumeOutline(**outline_data)

        # Deduplicate chapters
        seen_chapters = {}
        for ch in outline.chapters:
            if ch.number not in seen_chapters:
                seen_chapters[ch.number] = ch
        outline.chapters = sorted(seen_chapters.values(), key=lambda c: c.number)

        vol = self._current_volume()
        vol.status = "執筆中"
        results = []

        # Count total scenes
        total_scenes = len(outline.scenes)
        done_scenes = 0
        start_time = _time.time()

        def _log(msg: str):
            """Write to both stderr and optional log callback."""
            import sys as _sys
            _sys.stderr.write(msg)
            if log_fn:
                log_fn(msg.rstrip())

        def _progress(scene_num: int, status: str):
            nonlocal done_scenes
            done_scenes += 1
            elapsed = _time.time() - start_time
            avg = elapsed / done_scenes if done_scenes > 0 else 0
            remaining = avg * (total_scenes - done_scenes)
            elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s"
            remaining_str = f"{int(remaining // 60)}m {int(remaining % 60)}s"
            pct = done_scenes / total_scenes * 100 if total_scenes > 0 else 0
            bar_len = 20
            filled = int(bar_len * done_scenes / total_scenes) if total_scenes > 0 else 0
            bar = "█" * filled + "░" * (bar_len - filled)
            _log(
                f"  [{bar}] {pct:5.1f}% "
                f"({done_scenes}/{total_scenes}) "
                f"{status} "
                f"経過: {elapsed_str} "
                f"残り推定: {remaining_str}\n"
            )
        for chapter in outline.chapters:
            chapter_scenes: list[str] = []
            ch_scenes = [s for s in outline.scenes if s.chapter_number == chapter.number]
            for scene in ch_scenes:
                record = self._get_or_create_scene_record(vol, scene.number)
                if record.status in ("修正済", "強制出力済"):
                    chapter_scenes.append(
                        self._scene_writer.load_scene_draft(
                            vol_num, scene.number, chapter.number
                        )
                    )
                    _progress(scene.number, f"スキップ(済)")
                    continue
                _log(f"  [SCENE START] vol{vol_num} ch{chapter.number} sc{scene.number} t={_time.time()-start_time:.0f}s\n")
                result = self._scene_writer.write_scene(
                    outline=outline,
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
                # Post-scene: summarize + bible update (1 LLM call)
                _log(f"  [SUMMARY START] vol{vol_num} ch{chapter.number} sc{scene.number}\n")
                self._scene_writer.summarize_and_update_bible(
                    record.scene_number,
                    draft_text,
                    self._lang,
                    self._bible_mgr.to_text,
                )
                _log(f"  [SUMMARY END] vol{vol_num} ch{chapter.number} sc{scene.number}\n")
                _log(f"  [SCENE END] vol{vol_num} ch{chapter.number} sc{scene.number} t={_time.time()-start_time:.0f}s\n")
                self._save()

            self._scene_writer.assemble_chapter(vol_num, chapter, chapter_scenes)

        vol.status = "初稿済"
        self._state.status = "初稿済"
        self._save()
        return results
