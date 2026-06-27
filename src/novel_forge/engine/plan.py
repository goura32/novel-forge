"""Series plan generation — 3-phase: core → characters → volumes.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from novel_forge.engine.review import format_review_text
from novel_forge.name_registry import load_used_names, record_names
from novel_forge.schemas import get_schema

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase


def _validate_plan_core(core: dict) -> list[str]:
    required = ["title", "logline", "genre", "world"]
    errors = []
    for field in required:
        val = core.get(field)
        if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
            errors.append(field)
    if isinstance(core.get("world"), dict):
        if not core["world"].get("summary"):
            errors.append("world.summary")
    else:
        errors.append("world")
    return errors


def _validate_plan_characters(characters: dict) -> list[str]:
    required = ["main_characters"]
    errors = []
    for field in required:
        val = characters.get(field)
        if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
            errors.append(field)
    if not errors:
        for i, c in enumerate(characters["main_characters"]):
            if not c.get("name"):
                errors.append(f"main_characters[{i}].name")
            if not c.get("role"):
                errors.append(f"main_characters[{i}].role")
    return errors


def _validate_plan_volumes(volumes: dict) -> list[str]:
    required = ["planned_volumes"]
    errors = []
    for field in required:
        val = volumes.get(field)
        if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
            errors.append(field)
    if not errors:
        for i, v in enumerate(volumes["planned_volumes"]):
            if not v.get("title"):
                errors.append(f"planned_volumes[{i}].title")
    return errors


def _get_existing_slugs(engine: "NovelEngineBase") -> set[str]:
    existing = set()
    workdir = engine.workdir
    if not workdir.exists():
        return existing
    for d in workdir.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        plan_path = d / "series_plan.json"
        if plan_path.exists():
            try:
                data = json.loads(plan_path.read_text(encoding="utf-8"))
                slug = data.get("slug", "")
                if slug:
                    existing.add(slug)
            except Exception:
                pass
    return existing


def plan(engine: "NovelEngineBase", keywords: str) -> dict[str, Any]:
    """Generate a complete series plan (core → characters → volumes)."""
    system = engine._prompts.render("system.md", {"lang": engine._lang})

    # Phase 1: Core (title, logline, world)
    engine._log.info(f"▶ Plan: keywords='{keywords}'")
    existing_slugs = _get_existing_slugs(engine)
    core, core_review = _generate_plan_core(engine, keywords, system, existing_slugs)
    title = core.get("title", "")
    slug = core.get("slug", "")
    if not slug:
        slug = _slugify(title)
    slug = slug[:32]
    engine._slug = slug

    # Phase 2: Characters
    used_names = load_used_names(engine.workdir)
    characters, chars_review = _generate_plan_characters(engine, core, system, used_names)

    # Phase 3: Volumes
    volumes, vols_review = _generate_plan_volumes(engine, core, characters, system)

    # Add number to each volume
    planned_volumes = []
    for i, v in enumerate(volumes.get("planned_volumes", []), 1):
        planned_volumes.append({**v, "number": i})

    # Save reviews
    engine._move_to_final_dir()
    engine._save_path(0, "series_core_review.json", {"issues": core_review.get("issues", [])})
    engine._save_path(0, "series_characters_review.json", {"issues": chars_review.get("issues", [])})
    engine._save_path(0, "series_volumes_review.json", {"issues": vols_review.get("issues", [])})

    # Assemble and save
    result = {
        "title": title,
        "slug": slug,
        **characters,
        "main_characters": characters.get("main_characters", []),
        "planned_volumes": planned_volumes,
    }

    engine._save_path(0, "series_plan.json", result)
    engine._state.status = "企画済"
    engine._save()
    engine._log.info(f"✓ Plan complete: title='{title}' slug='{slug}'")

    # Record character names for future dedup
    new_names = {c.get("name", "") for c in characters.get("main_characters", []) if c.get("name")}
    if new_names:
        record_names(engine.workdir, new_names)

    return result


def _slugify(title: str) -> str:
    """フォールバック用slug生成。英数字がなければハッシュを使用。"""
    romaji_parts = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", title)
    if romaji_parts:
        slug = "_".join(p.lower() for p in romaji_parts)
        slug = re.sub(r"[^a-z0-9_]", "", slug)
        if slug:
            return slug[:32]
    h = hashlib.md5(title.encode()).hexdigest()[:12]
    return f"series_{h}"


def _generate_plan_core(engine: "NovelEngineBase", keywords: str, system: str, existing_slugs: set[str]) -> tuple[dict, dict]:
    hint = ""
    if existing_slugs:
        hint = f"\n\n## 注意: 以下のslugは既存シリーズで使用済み: {', '.join(sorted(existing_slugs))}\n重複しないslugを生成すること。"
    prompt = (
        engine._prompts.render("series_plan_core.md", {"keywords": keywords, "lang": engine._lang})
        + hint
    )
    return engine._generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "series_plan_core", system, p, get_schema("series_plan_core"), seed_offset=s
        ),
        validate_fn=_validate_plan_core,
        review_fn=lambda r, sys: _review_plan_core(engine, r, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_core(engine, r, rv, sys, so),
        system=system,
        user_prompt=prompt,
        kind="series_plan_core",
    )


def _review_plan_core(engine: "NovelEngineBase", core: dict, system: str) -> dict:
    text = (
        f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n"
        f"ジャンル: {', '.join(core.get('genre', []))}\nターゲット読者: {core.get('target_audience', '')}\n"
        f"テーマ: {', '.join(core.get('themes', []))}\n売りポイント: {'; '.join(core.get('selling_points', []))}\n"
        f"世界観: {core.get('world', {}).get('summary', '')}\n"
        f"世界観ルール: {'; '.join(core.get('world', {}).get('rules', []))}"
    )
    user = engine._prompts.render(
        "series_plan_core_review.md", {"plan_text": text, "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "series_plan_core_review", system, user, get_schema("series_plan_core_review")
    )


def _revise_plan_core(
    engine: "NovelEngineBase", core: dict, review: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "series_plan_core_revision.md",
        {"current_plan": json.dumps(core, ensure_ascii=False), "review": review_text},
    )
    return engine._llm.complete_json(
        "series_plan_core", system, prompt, get_schema("series_plan_core")
    )


def _generate_plan_characters(engine: "NovelEngineBase", core: dict, system: str, used_names: set[str]) -> tuple[dict, dict]:
    existing_hint = ""
    if used_names:
        existing_hint = f"\n\n## 注意: 以下の名前は既存シリーズで使用済みのため使用不可: {', '.join(sorted(used_names))}\n新しいキャラクターには、これらの名前と重複しない名前を割り当てること。"
    prompt = (
        engine._prompts.render(
            "series_plan_characters.md",
            {
                "world_summary": core.get("world", {}).get("summary", ""),
                "world_rules": "; ".join(core.get("world", {}).get("rules", [])),
                "lang": engine._lang,
            },
        )
        + existing_hint
    )
    return engine._generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "series_plan_characters",
            system,
            p,
            get_schema("series_plan_characters"),
            seed_offset=s,
        ),
        validate_fn=_validate_plan_characters,
        review_fn=lambda r, sys: _review_plan_characters(engine, r, core, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_characters(engine, r, rv, sys, so),
        system=system,
        user_prompt=prompt,
        kind="series_plan_characters",
    )


def _review_plan_characters(engine: "NovelEngineBase", characters: dict, core: dict, system: str) -> dict:
    lines = ["世界観:", core.get("world", {}).get("summary", ""), "", "メインキャラクター:"]
    for c in characters.get("main_characters", []):
        lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
    text = "\n".join(lines)
    user = engine._prompts.render(
        "series_plan_characters_review.md", {"characters": text, "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "series_plan_characters_review",
        system,
        user,
        get_schema("series_plan_characters_review"),
    )


def _revise_plan_characters(
    engine: "NovelEngineBase", characters: dict, review: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "series_plan_characters_revision.md",
        {
            "current_characters": json.dumps(characters, ensure_ascii=False),
            "review": review_text,
        },
    )
    return engine._llm.complete_json(
        "series_plan_characters", system, prompt, get_schema("series_plan_characters")
    )


def _generate_plan_volumes(engine: "NovelEngineBase", core: dict, characters: dict, system: str) -> tuple[dict, dict]:
    char_lines = ["メインキャラクター:"]
    for c in characters.get("main_characters", []):
        char_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
    prompt = engine._prompts.render(
        "series_plan_volumes.md",
        {
            "core_text": f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n世界観: {core.get('world', {}).get('summary', '')}",
            "characters_text": "\n".join(char_lines),
            "lang": engine._lang,
        },
    )
    return engine._generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "series_plan_volumes", system, p, get_schema("series_plan_volumes"), seed_offset=s
        ),
        validate_fn=_validate_plan_volumes,
        review_fn=lambda r, sys: _review_plan_volumes(engine, r, core, characters, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_volumes(engine, r, rv, sys, so),
        system=system,
        user_prompt=prompt,
        kind="series_plan_volumes",
    )


def _review_plan_volumes(
    engine: "NovelEngineBase", volumes: dict, core: dict, characters: dict, system: str
) -> dict:
    lines = [
        f"シリーズ核:\n  タイトル: {core.get('title', '')}\n  あらすじ: {core.get('logline', '')}",
        "",
        "各巻:",
    ]
    for v in volumes.get("planned_volumes", []):
        lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
    text = "\n".join(lines)
    user = engine._prompts.render(
        "series_plan_volumes_review.md", {"volumes": text, "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "series_plan_volumes_review", system, user, get_schema("series_plan_volumes_review")
    )


def _revise_plan_volumes(
    engine: "NovelEngineBase", volumes: dict, review: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "series_plan_volumes_revision.md",
        {"current_volumes": json.dumps(volumes, ensure_ascii=False), "review": review_text},
    )
    return engine._llm.complete_json(
        "series_plan_volumes", system, prompt, get_schema("series_plan_volumes")
    )
