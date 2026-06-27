"""Scene writing — write method for NovelEngine.

Standalone function that accepts NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

from typing import Any

from novel_forge.models import SceneWriteContext, VolumeOutline


def write(engine, volume_number: int | None = None) -> list[dict[str, Any]]:
    """Write scene drafts for a volume."""
    vol_num = volume_number or engine.state.current_volume
    engine.state.current_volume = vol_num
    engine._state.status = "執筆中"
    slug = getattr(engine, "_slug", "?")
    design_data = engine._load_path(vol_num, f"vol{vol_num:02d}.json")
    vol_title = design_data.get("title", f"第{vol_num}巻")
    # Ensure purpose is set (fallback for legacy designs without purpose)
    chapters = design_data.get("chapters", [])
    for i, ch in enumerate(chapters, 1):
        if not ch.get("purpose"):
            ch["purpose"] = "導入" if i == 1 else ("収束" if i == len(chapters) else "展開")
    scenes = design_data.get("scenes", [])
    # Avoid nesting scenes inside chapters for VolumeOutline
    chapters_clean = []
    for ch in chapters:
        ch_copy = {k: v for k, v in ch.items() if k != "scenes"}
        chapters_clean.append(ch_copy)
    design_obj = VolumeOutline(
        volume_number=vol_num,
        title=design_data.get("title", ""),
        premise=design_data.get("premise", ""),
        chapters=chapters_clean,
        scenes=scenes,
    )
    engine._log.info(f"▶ Write: series='{slug}' vol={vol_num} title='{vol_title}'")
    engine._scene_writer._strict = getattr(engine, "_strict", False)

    # Deduplicate chapters
    seen = {}
    for ch in design_obj.chapters:
        if ch.number not in seen:
            seen[ch.number] = ch
    design_obj.chapters = sorted(seen.values(), key=lambda c: c.number)

    results = []
    total_ch = len(design_obj.chapters)
    total_scenes = len(design_obj.scenes)
    vol = engine._current_volume()

    engine._log.info(f"  ▶ Write: {total_ch} ch, {total_scenes} sc")

    for chapter in design_obj.chapters:
        ch_scenes = [s for s in design_obj.scenes if s.chapter_number == chapter.number]
        engine._log.info(f"    ▶ ch{chapter.number}/{total_ch} — {len(ch_scenes)} sc")

        for scene in ch_scenes:
            record = engine._get_or_create_scene_record(vol, scene.number)
            if record.status in ("修正済", "強制出力済"):
                engine._log.info(f"    ~ sc{scene.number}/{total_scenes} skip")
                continue

            engine._log.info(f"    ▶ sc{scene.number} — {scene.title}")
            result = engine._scene_writer.write_scene(
                design_obj=design_obj,
                chapter=chapter,
                scene=scene,
                record=record,
                ctx=SceneWriteContext(
                    lang=engine._lang,
                    vol_num=vol_num,
                    build_context_fn=engine._ctx_builder.build_context,
                    build_continuity_fn=lambda sn, vn: engine._ctx_builder.build_continuity(
                        sn, vn, engine._scene_writer.load_scene_draft
                    ),
                    get_series_plan_summary_fn=engine._ctx_builder.get_series_plan_summary,
                    get_outline_summary_fn=engine._ctx_builder.get_outline_summary,
                    get_scene_summary_fn=engine._ctx_builder.get_scene_summary,
                    get_bible_text_fn=engine._bible_mgr.to_text,
                    load_scene_draft_fn=engine._scene_writer.load_scene_draft,
                ),
            )
            results.append(result)
            draft_text = engine._scene_writer.load_scene_draft(
                vol_num, scene.number, chapter.number
            )
            engine._scene_writer.summarize_and_update_bible(
                record.scene_number, draft_text, engine._lang, engine._bible_mgr.to_text
            )
            engine._log.info(f"    ✓ sc{scene.number}")

        engine._log.info(f"  ✓ ch{chapter.number}/{total_ch}")

    vol = engine._current_volume()
    vol.status = "初稿済"
    engine._state.status = "初稿済"
    engine._save()
    engine._log.info(
        f"✓ Write: series='{slug}' vol={vol_num} — {len(results)}/{total_scenes} sc done"
    )
    return results
