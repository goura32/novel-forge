"""Volume design generation — 3-phase: volume → chapter → scene.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import contextlib
import json
import os
from typing import TYPE_CHECKING, Any

from novel_forge.engine.review import format_review_text, generate_and_review
from novel_forge.schemas import get_schema

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase


def _validate_volume_design(data: dict) -> list[str]:
    errors = []
    if not data.get("chapters"):
        errors.append("chapters")
    return errors


def _validate_chapter_design(data: dict) -> list[str]:
    errors = []
    if not data.get("title"):
        errors.append("title")
    if not data.get("purpose"):
        errors.append("purpose")
    if not data.get("theme") or not str(data.get("theme", "")).strip():
        errors.append("theme (empty)")
    if not data.get("emotional_arc") or not str(data.get("emotional_arc", "")).strip():
        errors.append("emotional_arc (empty)")
    outcome = data.get("outcome")
    if not outcome or not str(outcome).strip() or str(outcome).strip().lower() == "none":
        errors.append("outcome (empty or None)")
    if not data.get("scenes"):
        errors.append("scenes (empty)")
    return errors


def _validate_scene_design(data: dict) -> list[str]:
    errors = []
    if not data.get("title"):
        errors.append("title")
    if not data.get("goal"):
        errors.append("goal")
    if not data.get("conflict"):
        errors.append("conflict")
    if not data.get("outcome"):
        errors.append("outcome")
    return errors


def design(engine: NovelEngineBase, volume_number: int | None = None) -> dict[str, Any]:
    """Generate a volume design (chapter/scene structure)."""
    vol_num = volume_number or engine.state.current_volume
    engine.state.current_volume = vol_num
    engine._state.status = "デザイン済"
    engine._slug = engine._slug or engine.workdir.name
    slug = engine._slug
    if not slug:
        raise ValueError("Design: slug is empty — run 'plan' first or specify --series")

    plan_path = engine._series_dir / "series_plan.json"
    total_vol = "?"
    if plan_path.exists():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            total_vol = len(plan.get("planned_volumes", []))
        except Exception:
            pass

    engine._log.info(f"▶ Design: slug='{slug}' vol={vol_num}/{total_vol} PID={os.getpid()}")
    system = engine._prompts.render("system.md", {"lang": engine._lang})
    genre = engine._ctx_builder.get_genre()
    series_plan = engine._ctx_builder.get_series_plan_summary()

    # Phase 1: Volume design (chapters only - title/purpose)
    engine._log.info(f"  ▶ volume_design — vol={vol_num}/{total_vol}")
    prev_design = ""
    if vol_num > 1:
        prev_vol_path = engine._series_dir / f"vol{vol_num - 1:02d}" / f"vol{vol_num - 1:02d}.json"
        if prev_vol_path.exists():
            with contextlib.suppress(Exception):
                prev_design = prev_vol_path.read_text(encoding="utf-8")
    vol_design_data = generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "volume_design", system, p, get_schema("volume_design"), seed_offset=s),
        validate_fn=_validate_volume_design,
        review_fn=lambda r, sys: _review_volume_design(engine, r, sys),
        revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json(
            "volume_design", sys, engine._prompts.render("volume_design_revision.md",
                {"concept_text": series_plan, "current_volume": json.dumps(r, ensure_ascii=False), 
                 "review": format_review_text(rv), "previous_design": prev_design,
                 "series_plan": series_plan}),
            get_schema("volume_design"), seed_offset=so),
        system=system,
        user_prompt=engine._prompts.render("volume_design.md",
            {"series_plan": series_plan, "volume_number": str(vol_num), "genre": genre,
             "previous_design": prev_design, "lang": engine._lang}),
        kind="volume_design",
        llm=engine._llm,
        quality=engine._quality,
    )
    vol_design_data = vol_design_data[0] if isinstance(vol_design_data, tuple) else vol_design_data
    if isinstance(vol_design_data, dict):
        chapters = vol_design_data.get("chapters", [vol_design_data])
        vol_title = vol_design_data.get("title", f"第{vol_num}巻")
        vol_premise = vol_design_data.get("premise", "")
    else:
        chapters = []
        vol_title = f"第{vol_num}巻"
        vol_premise = ""
    chapters_count = len(chapters)
    engine._log.info(f"  ✓ volume_design — vol={vol_num} {chapters_count} ch done")

    # Phase 2: Chapter design — one call per chapter (including scene generation)
    engine._log.info(f"  ▶ chapter_design — vol={vol_num} {chapters_count} ch")
    chapter_results = []
    prev_chapter_outcome = ""
    prev_volume_summary = ""
    if vol_num > 1:
        prev_vol_path = engine._series_dir / f"vol{vol_num - 1:02d}" / f"vol{vol_num - 1:02d}.json"
        if prev_vol_path.exists():
            try:
                prev_vol = json.loads(prev_vol_path.read_text(encoding="utf-8"))
                prev_volume_summary = prev_vol.get("summary", "") or prev_vol.get("premise", "")
            except Exception:
                pass
    for ch_idx in range(1, chapters_count + 1):
        ch_data = chapters[ch_idx - 1] if ch_idx <= len(chapters) else {}
        ch_prompt = engine._prompts.render("chapter_design.md",
            {"series_plan": series_plan, "volume_number": str(vol_num),
             "volume_title": vol_title, "volume_premise": vol_premise,
             "chapter_number": str(ch_idx), "chapter_title": ch_data.get("title", ""),
             "chapter_purpose": ch_data.get("purpose", ""),
             "previous_chapter_outcome": prev_chapter_outcome,
             "previous_volume_summary": prev_volume_summary,
             "lang": engine._lang})
        ch_result = generate_and_review(
                  generate_fn=lambda p, s: engine._llm.complete_json(
                      "chapter_design", system, p, get_schema("chapter_design"), seed_offset=s),
                  validate_fn=_validate_chapter_design,
                  review_fn=lambda r, sys: _review_chapter_design(engine, r, sys),
                  revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json(
                      "chapter_design", sys, engine._prompts.render("chapter_design_revision.md",
                          {"current_chapter": json.dumps(r, ensure_ascii=False), "series_plan": series_plan, "review": format_review_text(rv)}),
                      get_schema("chapter_design"), seed_offset=so),
                  system=system,
                  user_prompt=ch_prompt,
                  kind="chapter_design",
                  llm=engine._llm,
                  quality=engine._quality,
              )
        if isinstance(ch_result, tuple):
            ch_result = ch_result[0]
        chapter_results.append(ch_result)
        if isinstance(ch_result, dict):
            prev_chapter_outcome = ch_result.get("outcome", "") or ch_result.get("emotional_arc", "")
    chapters = chapter_results
    engine._log.info(f"  ✓ chapter_design — vol={vol_num} {len(chapters)}/{chapters_count} ch done")

    # Phase 3: Scene design — use scenes from chapter_design (no estimation)
    engine._log.info(f"  ▶ scene_design — vol={vol_num} {chapters_count} ch")
    scenes: list[dict] = []
    scene_counter = 0
    prev_outcome = ""
    for ch in chapters:
        ch_num = ch.get("number", 0)
        ch_scenes = ch.get("scenes", [])
        chapter_scene_count = len(ch_scenes)
        for chapter_scene_number, sc_data in enumerate(ch_scenes, 1):
            scene_counter += 1
            sc_prompt = engine._prompts.render("scene_design.md",
                {"series_plan": series_plan, "volume_number": str(vol_num),
                 "volume_title": vol_title, "volume_premise": vol_premise,
                 "chapter_number": str(ch_num), "scene_number": str(scene_counter),
                 "scene_count": str(chapter_scene_count),
                 "chapter_scene_number": str(chapter_scene_number),
                 "chapter_scene_count": str(chapter_scene_count),
                 "chapter_title": ch.get("title", ""),
                 "chapter_purpose": ch.get("purpose", ""),
                 "chapter_theme": ch.get("theme", ""),
                 "chapter_emotional_arc": ch.get("emotional_arc", ""),
                 "chapter_foreshadowing_notes": json.dumps(ch.get("foreshadowing_notes", []), ensure_ascii=False),
                 "chapter_subplot_notes": json.dumps(ch.get("subplot_notes", []), ensure_ascii=False),
                 "scene_seed": json.dumps(sc_data, ensure_ascii=False),
                 "previous_outcome": prev_outcome,
                 "previous_volume_summary": prev_volume_summary,
                 "lang": engine._lang})
            sc_result = generate_and_review(
                          generate_fn=lambda p, s: engine._llm.complete_json(
                              "scene_design", system, p, get_schema("scene_design"),
                              seed_offset=s),
                          validate_fn=_validate_scene_design,
                          review_fn=lambda r, sys: _review_scene_design(engine, r, sys),
                          revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json(
                              "scene_design", sys, engine._prompts.render("scene_design_revision.md",
                                  {"current_scene": json.dumps(r, ensure_ascii=False), "series_plan": series_plan, "review": format_review_text(rv)}),
                              get_schema("scene_design"), seed_offset=so),
                          system=system,
                          user_prompt=sc_prompt,
                          kind="scene_design",
                          llm=engine._llm,
                          quality=engine._quality,
                      )
            scene_obj = sc_result[0] if isinstance(sc_result, tuple) else sc_result
            if isinstance(scene_obj, dict):
                scene_obj["chapter_number"] = scene_obj.get("chapter_number", ch_num)
                scene_obj.setdefault("chapter_scene_number", chapter_scene_number)
                scene_obj["number"] = scene_counter
                scenes.append(scene_obj)
                prev_outcome = scene_obj.get("outcome", "")
    engine._log.info(f"  ✓ scene_design — vol={vol_num} {len(scenes)} sc done")

    # Build result
    chapters_with_scenes = []
    for i, ch in enumerate(chapters, 1):
        ch_scenes = [s for s in scenes if s.get("chapter_number") == i]
        chapters_with_scenes.append({
            "number": i,
            "title": ch.get("title", ""),
            "purpose": ch.get("purpose", ""),
            "theme": ch.get("theme", ""),
            "emotional_arc": ch.get("emotional_arc", ""),
            "outcome": ch.get("outcome", ""),
            "chapter_turning_point": ch.get("chapter_turning_point", ""),
            "chapter_hook": ch.get("chapter_hook", ""),
            "foreshadowing_notes": ch.get("foreshadowing_notes", []),
            "subplot_notes": ch.get("subplot_notes", []),
            "characters": ch.get("characters", []),
            "scenes": ch_scenes,
        })

    vol = engine._current_volume()
    vol.status = "デザイン済"
    # Use volume title from volume_design if available
    vol_title = engine._state.title if hasattr(engine._state, 'title') and engine._state.title else f"第{vol_num}巻"
    result = {
        "title": vol_title,
        "premise": vol_premise,
        "chapters": chapters_with_scenes,
        "scenes": scenes,
    }

    # Save
    engine._save_path(vol_num, f"vol{vol_num:02d}.json", result)

    for ch in result.get("chapters", []):
        ch_num = ch["number"]
        engine._save_path(vol_num, f"vol{vol_num:02d}_ch{ch_num:02d}.json", ch)

    for sc in result.get("scenes", []):
        sc_num = sc.get("number", 0)
        ch_num = sc.get("chapter_number", 0)
        engine._save_path(
            vol_num,
            f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}.json",
            sc,
        )

    engine._save()
    engine._log.info(f"✓ Design: series='{slug}' vol={vol_num} — {len(chapters)} ch, {len(scenes)} sc")
    return result


def _review_volume_design(engine: NovelEngineBase, data: dict, system: str) -> dict:
    chapters_info = ""
    for i, ch in enumerate(data.get("chapters", []), 1):
        chapters_info += f"\n  第{i}章: {ch.get('title', '')} (役割: {ch.get('purpose', '')})"
    text = f"巻設計:\n  タイトル: {data.get('title', '')}\n  章数: {len(data.get('chapters', []))}{chapters_info}"
    user = engine._prompts.render("volume_design_review.md",
        {"design": text, "concept_text": engine._ctx_builder.get_series_plan_summary(), "lang": engine._lang})
    return engine._llm.complete_json("review", system, user, get_schema("review"))


def _review_chapter_design(engine: NovelEngineBase, data: dict, system: str) -> dict:
    text = f"章設計:\\n  タイトル: {data.get('title', '')}\\n  目的: {data.get('purpose', '')}"
    user = engine._prompts.render("chapter_design_review.md",
        {"design": text, "series_plan": engine._ctx_builder.get_series_plan_summary(), "lang": engine._lang})
    return engine._llm.complete_json("review", system, user, get_schema("review"))


def _review_scene_design(engine: NovelEngineBase, data: dict, system: str) -> dict:
    text = (f"シーン設計:\\n  タイトル: {data.get('title', '')}\\n"
            f"  目標: {data.get('goal', '')}\\n  葛藤: {data.get('conflict', '')}\\n"
            f"  結果: {data.get('outcome', '')}")
    user = engine._prompts.render("scene_design_review.md",
        {"design": text, "series_plan": engine._ctx_builder.get_series_plan_summary(), "lang": engine._lang})
    return engine._llm.complete_json("review", system, user, get_schema("review"))


def _default_purpose(i: int, total: int) -> str:
    if i == 1:
        return "導入"
    if i == total:
        return "収束"
    return "展開"


def _estimate_scene_count(purpose: str) -> int:
    counts = {"導入": 2, "展開": 3, "転換": 3, "クライマックス": 4, "収束": 2}
    return counts.get(purpose, 3)