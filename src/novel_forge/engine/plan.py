"""Series plan generation — 3-phase: concept → characters → volumes.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from novel_forge.engine.review import format_review_text, generate_and_review
from novel_forge.name_registry import load_used_names, record_names
from novel_forge.schemas import get_schema

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase


def _validate_plan_concept(concept: dict) -> list[str]:
    # Normalize slug before validation (LLM may output hyphens/whitespace which 
    # the schema regex ^[a-z0-9_]+$ rejects — normalize to underscores first).
    slug = concept.get("slug", "")
    if isinstance(slug, str):
        concept["slug"] = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    
    required = ["title", "slug", "logline", "genre", "target_audience", "themes", "selling_points", "world_summary", "world_rules"]
    errors = []
    for field in required:
        val = concept.get(field)
        if val is None:
            errors.append(f"{field} (missing)")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"{field} (empty)")
        elif isinstance(val, list) and len(val) == 0:
            errors.append(f"{field} (empty list)")
    return errors


def _validate_plan_characters(characters: dict) -> list[str]:
    required = ["main_characters"]
    errors = []
    for field in required:
        val = characters.get(field)
        if val is None:
            errors.append(f"{field} (missing)")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"{field} (empty)")
        elif isinstance(val, list) and len(val) == 0:
            errors.append(f"{field} (empty list)")
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
        if val is None:
            errors.append(f"{field} (missing)")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"{field} (empty)")
        elif isinstance(val, list) and len(val) == 0:
            errors.append(f"{field} (empty list)")
    if not errors:
        for i, v in enumerate(volumes["planned_volumes"]):
            if not v.get("title"):
                errors.append(f"planned_volumes[{i}].title")
    return errors


def _get_existing_slugs(engine: NovelEngineBase) -> set[str]:
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


def plan(engine: NovelEngineBase, keywords: str) -> dict[str, Any]:
    """Generate a complete series plan (concept → characters → volumes).

    The final series_plan.json is assembled entirely from LLM-generated values.
    No mechanical fallback values are used for content fields.
    """
    system = engine._prompts.render("system.md", {"lang": engine._lang})

    # Phase 1: Concept (title, logline, world)
    engine._log.info(f"▶ Plan: keywords='{keywords}'")
    existing_slugs = _get_existing_slugs(engine)
    concept, concept_review = _generate_plan_concept(engine, keywords, system, existing_slugs)

    # Use LLM-generated slug; fall back to LLM-generated title only if missing
    slug = concept.get("slug") or _slugify(concept.get("title", ""))
    # Normalize: replace hyphens/whitespace with underscores to match regex ^[a-z0-9_]+$
    slug = re.sub(r"[^a-z0-9_]", "_", slug.lower()) 
    slug = slug[:32]
    engine._slug = slug

    # Phase 2: Characters
    used_names = load_used_names(engine.workdir)
    characters, chars_review = _generate_plan_characters(engine, concept, system, used_names)

    # Phase 3: Volumes
    volumes, vols_review = _generate_plan_volumes(engine, concept, characters, system)

    # Add number to each volume (mechanical — not content)
    planned_volumes = []
    for i, v in enumerate(volumes.get("planned_volumes", []), 1):
        planned_volumes.append({**v, "number": i})

    # Save reviews
    engine._move_to_final_dir()
    engine._save_path(0, "series_concept_review.json", {"issues": concept_review.get("issues", [])})
    engine._save_path(0, "series_characters_review.json", {"issues": chars_review.get("issues", [])})
    engine._save_path(0, "series_volumes_review.json", {"issues": vols_review.get("issues", [])})

    # Assemble and save — all content comes from LLM
    result = {
        "title": concept.get("title", ""),
        "slug": slug,
        "logline": concept.get("logline", ""),
        "genre": concept.get("genre", []),
        "target_audience": concept.get("target_audience", ""),
        "themes": concept.get("themes", []),
        "selling_points": concept.get("selling_points", []),
        "world_summary": concept.get("world_summary", ""),
        "world_rules": concept.get("world_rules", []),
        "main_characters": characters.get("main_characters", []),
        "planned_volumes": planned_volumes,
    }

    engine._save_path(0, "series_plan.json", result)
    engine._state.status = "企画済"
    engine._save()
    engine._log.info(f"✓ Plan complete: title='{result['title']}' slug='{slug}'")

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


def _generate_plan_concept(engine: NovelEngineBase, keywords: str, system: str, existing_slugs: set[str]) -> tuple[dict, dict]:
    slugs_text = ", ".join(sorted(existing_slugs)) if existing_slugs else "（なし）"
    prompt = engine._prompts.render(
        "series_plan_concept.md",
        {"keywords": keywords, "lang": engine._lang, "existing_slugs": slugs_text},
    )
    return generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "series_plan_concept", system, p, get_schema("series_plan_concept"), seed_offset=s
        ),
        validate_fn=_validate_plan_concept,
        review_fn=lambda r, sys: _review_plan_concept(engine, r, sys, get_schema("review")),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_concept(engine, r, rv, sys, so, get_schema("series_plan_concept")),
        system=system,
        user_prompt=prompt,
        kind="series_plan_concept",
        llm=engine._llm,
        quality=engine._quality,
    )


def _review_plan_concept(engine: NovelEngineBase, concept: dict, system: str, schema: dict | None = None) -> dict:
    text = (
        f"タイトル: {concept.get('title', '')}\nあらすじ: {concept.get('logline', '')}\n"
        f"ジャンル: {', '.join(concept.get('genre', []))}\nターゲット読者: {concept.get('target_audience', '')}\n"
        f"テーマ: {', '.join(concept.get('themes', []))}\n売りポイント: {'; '.join(concept.get('selling_points', []))}\n"
        f"世界観: {concept.get('world_summary', '')}\n"
        f"世界観ルール: {'; '.join(concept.get('world_rules', []))}"
    )
    user = engine._prompts.render(
        "series_plan_concept_review.md", {"plan_text": text, "keywords": "", "lang": engine._lang}
    )
    return engine._llm.complete_json("review", system, user, schema)


def _revise_plan_concept(
    engine: NovelEngineBase, concept: dict, review: dict, system: str, seed_offset: int = 0, schema: dict | None = None
) -> dict:
    review_text = format_review_text(review)
    # Format current_plan in human-readable field-by-field format for LLM clarity
    plan_text = (
        f"タイトル: {concept.get('title', '')}\nあらすじ: {concept.get('logline', '')}\n"
        f"ジャンル: {', '.join(concept.get('genre', []))}\nターゲット読者: {concept.get('target_audience', '')}\n"
        f"テーマ: {', '.join(concept.get('themes', []))}\n売りポイント: {'; '.join(concept.get('selling_points', []))}\n"
        f"世界観: {concept.get('world_summary', '')}\n"
        f"世界観ルール: {'; '.join(concept.get('world_rules', []))}"
    )
    prompt = engine._prompts.render(
        "series_plan_concept_revision.md",
        {"current_plan": plan_text, "review": review_text, "keywords": ""},
    )
    return engine._llm.complete_json("series_plan_concept", system, prompt, schema)


def _generate_plan_characters(engine: NovelEngineBase, concept: dict, system: str, used_names: set[str]) -> tuple[dict, dict]:
    import json
    series_plan_json = json.dumps(concept, ensure_ascii=False, indent=2)
    prompt = engine._prompts.render(
        "series_plan_characters.md",
        {
            "series_plan_json": series_plan_json,
            "lang": engine._lang,
            "used_names": ", ".join(sorted(used_names)) if used_names else "（なし）",
        },
    )
    return generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "series_plan_characters",
            system,
            p,
            get_schema("series_plan_characters"),
            seed_offset=s,
        ),
        validate_fn=_validate_plan_characters,
        review_fn=lambda r, sys: _review_plan_characters(engine, r, concept, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_characters(engine, r, rv, sys, so),
        system=system,
        user_prompt=prompt,
        kind="series_plan_characters",
        llm=engine._llm,
        quality=engine._quality,
    )


def _review_plan_characters(engine: NovelEngineBase, characters: dict, concept: dict, system: str) -> dict:
    lines = ["世界観:", concept.get("world_summary", ""), "", "メインキャラクター:"]
    for c in characters.get("main_characters", []):
        lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
    text = "\n".join(lines)
    user = engine._prompts.render(
        "series_plan_characters_review.md", {"characters": text, "concept_json": json.dumps(concept, ensure_ascii=False), "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "review", system, user, get_schema("review"),
    )


def _revise_plan_characters(
    engine: NovelEngineBase, characters: dict, review: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "series_plan_characters_revision.md",
        {
            "current_characters": json.dumps(characters, ensure_ascii=False),
            "concept_text": "",
            "review": review_text,
        },
    )
    return engine._llm.complete_json(
        "series_plan_characters", system, prompt, get_schema("series_plan_characters")
    )


def _generate_plan_volumes(engine: NovelEngineBase, concept: dict, characters: dict, system: str) -> tuple[dict, dict]:
    char_lines = ["メインキャラクター:"]
    for c in characters.get("main_characters", []):
        char_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
    prompt = engine._prompts.render(
        "series_plan_volumes.md",
        {
            "core_text": f"タイトル: {concept.get('title', '')}\nあらすじ: {concept.get('logline', '')}\n世界観: {concept.get('world_summary', '')}",
            "characters_text": "\n".join(char_lines),
            "lang": engine._lang,
        },
    )
    return generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "series_plan_volumes", system, p, get_schema("series_plan_volumes"), seed_offset=s
        ),
        validate_fn=_validate_plan_volumes,
        review_fn=lambda r, sys: _review_plan_volumes(engine, r, concept, characters, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_volumes(engine, r, rv, sys, so),
        system=system,
        user_prompt=prompt,
        kind="series_plan_volumes",
        llm=engine._llm,
        quality=engine._quality,
    )


def _review_plan_volumes(
    engine: NovelEngineBase, volumes: dict, concept: dict, characters: dict, system: str
) -> dict:
    lines = [
        f"シリーズ構想:\n  タイトル: {concept.get('title', '')}\n  あらすじ: {concept.get('logline', '')}",
        "",
        "各巻:",
    ]
    for v in volumes.get("planned_volumes", []):
        lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
    text = "\n".join(lines)
    user = engine._prompts.render(
        "series_plan_volumes_review.md", {"volumes": text, "volumes_json": json.dumps(volumes, ensure_ascii=False), "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "review", system, user, get_schema("review")
    )


def _revise_plan_volumes(
    engine: NovelEngineBase, volumes: dict, review: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "series_plan_volumes_revision.md",
        {"current_volumes": json.dumps(volumes, ensure_ascii=False), "concept_text": "", "review": review_text},
    )
    return engine._llm.complete_json(
        "series_plan_volumes", system, prompt, get_schema("series_plan_volumes")
    )
