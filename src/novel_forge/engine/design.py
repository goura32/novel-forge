"""Volume design generation — 3-phase: volume → chapter → scene.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import copy
import json
import os
from typing import TYPE_CHECKING, Any, cast

from novel_forge.canon.design import ChapterDesign as V2ChapterDesign
from novel_forge.canon.design import VolumeDesign as V2VolumeDesign
from novel_forge.canon.public_runtime import V2ProjectRuntime
from novel_forge.engine.review import format_review_text, generate_and_review
from novel_forge.runtime import get_schema_resource

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase


DESIGN_PURPOSE_ENUM = ("導入", "展開", "転換", "クライマックス", "収束")


def _normalize_design_purpose(value: object) -> str:
    purpose = str(value or "")
    if purpose in DESIGN_PURPOSE_ENUM:
        return purpose
    for valid in DESIGN_PURPOSE_ENUM:
        if valid in purpose:
            return valid
    return purpose


def _relax_nested_chapter_purpose_enum(schema: dict) -> dict:
    relaxed = copy.deepcopy(schema)
    (
        relaxed.get("properties", {})
        .get("chapters", {})
        .get("items", {})
        .get("properties", {})
        .get("purpose", {})
        .pop("enum", None)
    )
    return relaxed


def _validate_volume_design(data: dict) -> list[str]:
    errors = []
    if not data.get("chapters"):
        errors.append("chapters")
    return errors


def _has_vague_next_clue_placeholder(text: object) -> bool:
    value = str(text or "")
    return any(
        phrase in value
        for phrase in (
            "次章へ繋がる重要手掛かり",
            "次章へつながる重要手掛かり",
            "次への手がかり",
            "何か（次への手がかり）",
        )
    )


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
    if _has_vague_next_clue_placeholder(data.get("chapter_hook")):
        errors.append("chapter_hook (vague placeholder)")
    scenes = data.get("scenes")
    if not scenes:
        errors.append("scenes (empty)")
    else:
        for idx, scene in enumerate(scenes):
            if isinstance(scene, dict) and _has_vague_next_clue_placeholder(scene.get("outcome")):
                errors.append(f"scenes[{idx}].outcome (vague placeholder)")
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

    # P18-47 root cause: scene_design outcome used the specific incoherent
    # phrase "警備員から奪われた古鏡...". Keep this guard narrow so valid
    # story actions such as recovering an item are not rejected.
    if data.get("outcome"):
        outcome = str(data["outcome"])
        if "警備員から奪われた" in outcome:
            errors.append("outcome (incoherent stolen-from-guard phrasing)")

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

    plan: dict[str, Any] = {}
    total_vol = "?"
    planned_volume_title = ""
    plan = engine._load_series_plan()
    if plan:
        planned_volumes = plan.get("planned_volumes", [])
        total_vol = str(len(planned_volumes))
        if isinstance(planned_volumes, list) and 1 <= vol_num <= len(planned_volumes):
            planned_volume = planned_volumes[vol_num - 1]
            if isinstance(planned_volume, dict):
                planned_volume_title = str(planned_volume.get("title", "") or "")

    engine._log.info(f"▶ Design: slug='{slug}' vol={vol_num}/{total_vol} PID={os.getpid()}")
    system = engine._prompts.render("system.md", {"lang": engine._lang})
    # Public design reads author-side Canon projections only.  The series plan
    # is a derived planning artifact; it is never used as the Canon SSOT.
    runtime = V2ProjectRuntime(engine._series_dir)
    canon = runtime.canon()
    default_scope = runtime.default_scope(canon)
    genre = ", ".join(plan.get("genre", []))
    series_plan = json.dumps(plan, ensure_ascii=False, indent=2) if plan else "{}"

    # Phase 1: Volume design (chapters only - title/purpose)
    engine._log.info(f"  ▶ volume_design — vol={vol_num}/{total_vol}")
    prev_design = ""
    if vol_num > 1:
        prev_vol_path = engine._series_dir / f"vol{vol_num - 1:02d}" / f"vol{vol_num - 1:02d}.json"
        if prev_vol_path.exists():
            try:
                prev_design = prev_vol_path.read_text(encoding="utf-8")
            except Exception as exc:
                engine._log.warning("Failed to read previous volume design: %s", prev_vol_path, exc_info=exc)
    volume_schema = get_schema_resource("design.volume.generate")
    volume_generation_schema = _relax_nested_chapter_purpose_enum(volume_schema)

    def _normalize_volume_design(data: dict) -> dict:
        if planned_volume_title:
            data["title"] = planned_volume_title
        for chapter in data.get("chapters", []):
            if isinstance(chapter, dict) and "purpose" in chapter:
                chapter["purpose"] = _normalize_design_purpose(chapter.get("purpose"))
        return data

    def _generate_volume_design(prompt: str, seed_offset: int) -> dict:
        data = engine._llm.complete_json(
            "design.volume.generate", system, prompt, volume_generation_schema, seed_offset=seed_offset)
        return _normalize_volume_design(data)

    def _revise_volume_design(data: dict, review: dict, sys: str, seed_offset: int = 0) -> dict:
        revised = engine._llm.complete_json(
            "design.volume.revise", sys, engine._prompts.render("design_volume_revise.md",
                {"concept_text": series_plan, "current_volume": json.dumps(data, ensure_ascii=False, indent=2),
                 "review": format_review_text(review), "previous_design": prev_design,
                 "series_plan": series_plan}),
            volume_generation_schema, seed_offset=seed_offset)
        # 機械的な before→after 置換は行わない（指摘箇所以外との不整合防止）
        return _normalize_volume_design(revised)

    vol_design_data, _vol_review = generate_and_review(
        generate_fn=_generate_volume_design,
        validate_fn=_validate_volume_design,
        review_fn=lambda r, sys: _review_volume_design(engine, r, sys),
        revise_fn=_revise_volume_design,
        system=system,
        user_prompt=engine._prompts.render("design_volume_generate.md",
            {"series_plan": series_plan, "volume_number": str(vol_num),
             "volume_title": planned_volume_title or f"第{vol_num}巻", "genre": genre,
             "previous_design": prev_design, "lang": engine._lang,
             "bible": runtime.author_context_text("volume", default_scope, canon)}),
        kind="design.volume",
        llm=engine._llm,
        engine=engine,
        quality=engine._quality,
    )
    if isinstance(vol_design_data, dict):
        # 巻設計確定（v2 では design intent は Canon へ、Bible への書き戻しは廃止・§10）
        raw_chapters = vol_design_data.get("chapters", [vol_design_data])
        chapters: list[dict[str, Any]] = [
            chapter for chapter in raw_chapters if isinstance(chapter, dict)
        ]
        vol_title = str(vol_design_data.get("title", f"第{vol_num}巻"))
        vol_premise = str(vol_design_data.get("premise", ""))
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
            except Exception as exc:
                engine._log.warning("Failed to read previous volume summary: %s", prev_vol_path, exc_info=exc)
    chapter_schema = get_schema_resource("design.chapter.generate")
    chapter_generation_schema = copy.deepcopy(chapter_schema)
    chapter_generation_schema.get("properties", {}).get("purpose", {}).pop("enum", None)
    purpose_enum = set(chapter_schema.get("properties", {}).get("purpose", {}).get("enum", []))
    for ch_idx in range(1, chapters_count + 1):
        ch_data = chapters[ch_idx - 1] if ch_idx <= len(chapters) else {}
        fallback_chapter_purpose = str(ch_data.get("purpose", "") or "")

        def _normalize_invalid_chapter_purpose(
            data: dict,
            fallback_purpose: str = fallback_chapter_purpose,
        ) -> dict:
            purpose = str(data.get("purpose", "") or "")
            if purpose not in purpose_enum and fallback_purpose in purpose_enum:
                data["purpose"] = fallback_purpose
            return data

        def _generate_chapter_design(prompt: str, seed_offset: int) -> dict:
            data = engine._llm.complete_json(
                "design.chapter.generate", system, prompt, chapter_generation_schema, seed_offset=seed_offset)
            return _normalize_invalid_chapter_purpose(data)

        def _revise_chapter_design(data: dict, review: dict, sys: str, seed_offset: int = 0) -> dict:
            revised = engine._llm.complete_json(
                "design.chapter.revise", sys, engine._prompts.render("design_chapter_revise.md",
                    {"current_chapter": json.dumps(data, ensure_ascii=False, indent=2), "series_plan": series_plan,
                     "review": format_review_text(review)}),
                chapter_generation_schema, seed_offset=seed_offset)
            # 機械的な before→after 置換は行わない（指摘箇所以外との不整合防止）
            return _normalize_invalid_chapter_purpose(revised)

        ch_prompt = engine._prompts.render("design_chapter_generate.md",
            {"series_plan": series_plan, "volume_number": str(vol_num),
             "volume_title": vol_title, "volume_premise": vol_premise,
             "chapter_number": str(ch_idx), "chapter_title": ch_data.get("title", ""),
             "chapter_purpose": ch_data.get("purpose", ""),
             "previous_chapter_outcome": prev_chapter_outcome,
             "previous_volume_summary": prev_volume_summary,
             "lang": engine._lang,
             "bible": runtime.author_context_text("chapter", default_scope, canon)})
        ch_result, _ch_review = generate_and_review(
                  generate_fn=_generate_chapter_design,
                  validate_fn=_validate_chapter_design,
                  review_fn=lambda r, sys: _review_chapter_design(engine, r, sys),
                  revise_fn=_revise_chapter_design,
                  system=system,
                  user_prompt=ch_prompt,
                  kind="design.chapter",
                  llm=engine._llm,
                  quality=engine._quality,
              )
        chapter_results.append(ch_result)
        if isinstance(ch_result, dict):
            # 章設計確定（v2 では Canon へ、Bible 書き戻し廃止・§10）
            prev_chapter_outcome = ch_result.get("outcome", "") or ch_result.get("emotional_arc", "")
    chapters = chapter_results
    engine._log.info(f"  ✓ chapter_design — vol={vol_num} {len(chapters)}/{chapters_count} ch done")

    # Phase 3: Scene design — use scenes from chapter_design (no estimation)
    engine._log.info(f"  ▶ scene_design — vol={vol_num} {chapters_count} ch")
    scenes: list[dict] = []
    scene_counter = 0
    prev_outcome = ""
    for ch_index, ch in enumerate(chapters, 1):
        ch_num = ch.get("number") or ch_index
        ch_scenes = ch.get("scenes", [])
        chapter_scene_count = len(ch_scenes)
        for chapter_scene_number, sc_data in enumerate(ch_scenes, 1):
            scene_counter += 1
            seed_names = sc_data.get("characters", []) if isinstance(sc_data, dict) else []
            scene_scope = runtime.default_scope(
                canon,
                [str(name) for name in seed_names if isinstance(name, str)],
                str(sc_data.get("setting", "")) if isinstance(sc_data, dict) else "",
            )
            sc_prompt = engine._prompts.render("design_scene_generate.md",
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
                 "lang": engine._lang,
                 "bible": runtime.author_context_text("scene", scene_scope, canon)})
            def _revise_scene_design(data: dict, review: dict, sys: str, seed_offset: int = 0) -> dict:
                revised = engine._llm.complete_json(
                    "design.scene.revise", sys, engine._prompts.render("design_scene_revise.md",
                        {"current_scene": json.dumps(data, ensure_ascii=False, indent=2), "series_plan": series_plan,
                         "review": format_review_text(review)}),
                    get_schema_resource("design.scene.generate"), seed_offset=seed_offset)
                # 機械的な before→after 置換は行わない（指摘箇所以外との不整合防止）
                return cast(dict, revised)

            scene_obj, _sc_review = generate_and_review(
                          generate_fn=lambda p, s: engine._llm.complete_json(
                              "design.scene.generate", system, p, get_schema_resource("design.scene.generate"),
                              seed_offset=s),
                          validate_fn=_validate_scene_design,
                          review_fn=lambda r, sys: _review_scene_design(engine, r, sys),
                          revise_fn=_revise_scene_design,
                          system=system,
                          user_prompt=sc_prompt,
                          kind="design.scene",
                          llm=engine._llm,
                          quality=engine._quality,
                      )
            if isinstance(scene_obj, dict):
                if not scene_obj.get("chapter_number"):
                    scene_obj["chapter_number"] = ch_num
                scene_obj.setdefault("chapter_scene_number", chapter_scene_number)
                scene_obj["number"] = scene_counter
                scenes.append(scene_obj)
                # シーン設計確定（v2 では Canon へ、Bible 書き戻し廃止・§10）
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
    vol.scenes.clear()
    for sc in scenes:
        sc_num = int(sc.get("number") or len(vol.scenes) + 1)
        engine._get_or_create_scene_record(vol, sc_num)
    result: dict[str, Any] = {
        "title": vol_title,
        "premise": vol_premise,
        "chapters": chapters_with_scenes,
        "scenes": scenes,
    }

    # Persist the v2 source artifacts.  These—not the compatibility JSON below—
    # are the inputs to public write().  No Canon mutation happens in design.
    v2_volume = V2VolumeDesign(
        volume_id=f"vol{vol_num:02d}",
        context_scope=default_scope,
    )
    v2_chapters = [
        V2ChapterDesign(
            chapter_id=f"vol{vol_num:02d}_ch{index:02d}",
            context_scope=default_scope,
            scene_seeds=list(chapter.get("scenes", [])),
        )
        for index, chapter in enumerate(chapters_with_scenes, 1)
    ]
    v2_scenes = [
        runtime.scene_artifact(
            volume=vol_num,
            chapter=int(scene.get("chapter_number") or 1),
            scene=int(scene.get("number") or index),
            raw=scene,
            canon=canon,
        )
        for index, scene in enumerate(scenes, 1)
    ]
    runtime.save_design(vol_num, v2_volume, v2_chapters, v2_scenes)
    result["version"] = 2

    # Compatibility presentation artifact for export tools that have not yet
    # been switched to v2.  Public design/write never read it back.
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
    text = json.dumps(data, ensure_ascii=False, indent=2)
    user = engine._prompts.render("design_volume_review.md",
        {"design": text, "concept_text": _series_plan_text(engine), "lang": engine._lang})
    return engine._llm.complete_json("design.volume.review", system, user)


def _review_chapter_design(engine: NovelEngineBase, data: dict, system: str) -> dict:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    user = engine._prompts.render("design_chapter_review.md",
        {"design": text, "series_plan": _series_plan_text(engine), "lang": engine._lang})
    return engine._llm.complete_json("design.chapter.review", system, user)


def _review_scene_design(engine: NovelEngineBase, data: dict, system: str) -> dict:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    user = engine._prompts.render("design_scene_review.md",
        {"design": text, "series_plan": _series_plan_text(engine), "lang": engine._lang})
    return engine._llm.complete_json("design.scene.review", system, user)


def _series_plan_text(engine: NovelEngineBase) -> str:
    plan = engine._load_series_plan()
    if not plan:
        return "{}"
    try:
        return json.dumps(plan, ensure_ascii=False, indent=2)
    except (OSError, json.JSONDecodeError):
        return "{}"


def _default_purpose(i: int, total: int) -> str:
    if i == 1:
        return "導入"
    if i == total:
        return "収束"
    return "展開"


def _estimate_scene_count(purpose: str) -> int:
    counts = {"導入": 2, "展開": 3, "転換": 3, "クライマックス": 4, "収束": 2}
    return counts.get(purpose, 3)