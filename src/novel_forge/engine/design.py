"""Volume design generation — 3-phase: volume → chapter → scene.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import json
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


def design(engine: "NovelEngineBase", volume_number: int | None = None) -> dict[str, Any]:
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

    engine._log.info(f"▶ Design: slug='{slug}' vol={vol_num}/{total_vol}")
    system = engine._prompts.render("system.md", {"lang": engine._lang})
    genre = engine._ctx_builder.get_genre()
    series_plan = engine._ctx_builder.get_series_plan_summary()

    # Phase 1: Volume design (chapters)
    engine._log.info(f"  ▶ volume_design — vol={vol_num}/{total_vol}")
    vol_design_data = generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "volume_design", system, p, get_schema("volume_design"), seed_offset=s),
        validate_fn=_validate_volume_design,
        review_fn=lambda r, sys: _review_volume_design(engine, r, sys),
        revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json(
            "volume_design", sys, engine._prompts.render("volume_design_revision.md",
                {"current_volume": json.dumps(r, ensure_ascii=False), "review": format_review_text(rv)}),
            get_schema("volume_design"), seed_offset=so),
        system=system,
        user_prompt=engine._prompts.render("volume_design.md",
            {"series_plan": series_plan, "volume_number": str(vol_num), "genre": genre, "lang": engine._lang}),
        kind="volume_design",
        llm=engine._llm,
        quality=engine._quality,
        strict=engine._strict,
    )
    if isinstance(vol_design_data, tuple):
        vol_design_data = vol_design_data[0]
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

    # Phase 2: Chapter design — one call per chapter
    engine._log.info(f"  ▶ chapter_design — vol={vol_num} {chapters_count} ch")
    chapter_results = []
    for ch_idx in range(1, chapters_count + 1):
        ch_data = chapters[ch_idx - 1] if ch_idx <= len(chapters) else {}
        ch_prompt = engine._prompts.render("chapter_design.md",
            {"series_plan": series_plan, "volume_number": str(vol_num),
             "chapter_number": str(ch_idx), "chapter_title": ch_data.get("title", ""),
             "chapter_purpose": ch_data.get("purpose", ""),
             "lang": engine._lang})
        ch_result = generate_and_review(
            generate_fn=lambda p, s: engine._llm.complete_json(
                "chapter_design", system, p, get_schema("chapter_design"), seed_offset=s),
            validate_fn=_validate_chapter_design,
            review_fn=lambda r, sys: _review_chapter_design(engine, r, sys),
            revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json(
                "chapter_design", sys, engine._prompts.render("chapter_design_revision.md",
                    {"current_chapter": json.dumps(r, ensure_ascii=False), "review": format_review_text(rv)}),
                get_schema("chapter_design"), seed_offset=so),
            system=system,
            user_prompt=ch_prompt,
            kind="chapter_design",
            llm=engine._llm,
            quality=engine._quality,
            strict=engine._strict,
        )
        if isinstance(ch_result, tuple):
            ch_result = ch_result[0]
        chapter_results.append(ch_result)
    chapters = chapter_results
    engine._log.info(f"  ✓ chapter_design — vol={vol_num} {len(chapters)}/{chapters_count} ch done")

    # Phase 3: Scene design — generate estimated number of scenes per chapter
    est_scenes = sum(_estimate_scene_count(ch.get("purpose", "展開")) for ch in chapters)
    engine._log.info(f"  ▶ scene_design — vol={vol_num} {chapters_count} ch (~{est_scenes} sc)")
    scenes: list[dict] = []
    scene_counter = 0
    for ch in chapters:
        ch_num = ch.get("number", 0)
        ch_purpose = ch.get("purpose", "展開")
        ch_est = _estimate_scene_count(ch_purpose)
        for _ in range(ch_est):
            scene_counter += 1
            sc_prompt = engine._prompts.render("scene_design.md",
                {"series_plan": series_plan, "volume_number": str(vol_num),
                 "chapter_number": str(ch_num), "scene_number": str(scene_counter),
                 "lang": engine._lang})
            sc_data = generate_and_review(
                generate_fn=lambda p, s: engine._llm.complete_json(
                    "scene_design", system, p, get_schema("scene_design"),
                    seed_offset=s),
                validate_fn=_validate_scene_design,
                review_fn=lambda r, sys: _review_scene_design(engine, r, sys),
                revise_fn=lambda r, rv, sys, so=0: engine._llm.complete_json(
                    "scene_design", sys, engine._prompts.render("scene_design_revision.md",
                        {"current_scene": json.dumps(r, ensure_ascii=False), "review": format_review_text(rv)}),
                    get_schema("scene_design"), seed_offset=so),
                system=system,
                user_prompt=sc_prompt,
                kind="scene_design",
                llm=engine._llm,
                quality=engine._quality,
                strict=engine._strict,
            )
            scene_obj = sc_data[0] if isinstance(sc_data, tuple) else sc_data
            if isinstance(scene_obj, dict):
                scene_obj["chapter_number"] = scene_obj.get("chapter_number", ch_num)
                scene_obj["number"] = scene_counter
                scenes.append(scene_obj)
    engine._log.info(f"  ✓ scene_design — vol={vol_num} {len(scenes)}/{est_scenes} sc done")

    # Build result
    chapters_with_scenes = []
    for i, ch in enumerate(chapters, 1):
        ch_scenes = [s for s in scenes if s.get("chapter_number") == i]
        chapters_with_scenes.append({
            "number": i,
            "title": ch.get("title", ""),
            "purpose": ch.get("purpose", ""),
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
def _review_volume_design(engine: "NovelEngineBase", data: dict, system: str) -> dict:
    text = f"巻設計:\n  タイトル: {data.get('title', '')}\n  章数: {len(data.get('chapters', []))}"
    user = engine._prompts.render("volume_design_review.md",
        {"design": text, "lang": engine._lang})
    return engine._llm.complete_json("volume_design_review", system, user,
                                       get_schema("volume_design_review"))


def _review_chapter_design(engine: "NovelEngineBase", data: dict, system: str) -> dict:
    text = f"章設計:\n  タイトル: {data.get('title', '')}\n  目的: {data.get('purpose', '')}"
    user = engine._prompts.render("chapter_design_review.md",
        {"design": text, "lang": engine._lang})
    return engine._llm.complete_json("chapter_design_review", system, user,
                                       get_schema("chapter_design_review"))


def _review_scene_design(engine: "NovelEngineBase", data: dict, system: str) -> dict:
    text = (f"シーン設計:\n  タイトル: {data.get('title', '')}\n"
            f"  目標: {data.get('goal', '')}\n  葛藤: {data.get('conflict', '')}\n"
            f"  結果: {data.get('outcome', '')}")
    user = engine._prompts.render("scene_design_review.md",
        {"design": text, "lang": engine._lang})
    return engine._llm.complete_json("scene_design_review", system, user,
                                       get_schema("scene_design_review"))


def _update_chapter_designs(engine: "NovelEngineBase", revised: dict, seed_offset: int) -> None:
    """Revised chapter design may update title/purpose."""
    pass


def _update_scene_designs(engine: "NovelEngineBase", revised: dict, seed_offset: int, chapters: list) -> None:
    """Revised scene design may update title/goal/outcome."""
    pass


def _default_purpose(i: int, total: int) -> str:
    if i == 1:
        return "導入"
    if i == total:
        return "収束"
    return "展開"


def _estimate_scene_count(purpose: str) -> int:
    counts = {"導入": 2, "展開": 3, "転換": 3, "クライマックス": 4, "収束": 2}
    return counts.get(purpose, 3)
