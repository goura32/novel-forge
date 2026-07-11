"""Series plan generation — 3-phase: concept → characters → volumes.

Standalone functions that accept NovelEngine as first argument.
No mixin classes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, cast

from novel_forge.canon.store import BibleFactory, CanonEventStore
from novel_forge.engine.review import format_review_text, generate_and_review
from novel_forge.name_registry import load_used_names, record_names
from novel_forge.runtime import get_schema_resource

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase


MAX_SERIES_SLUG_LENGTH = 128


def _validate_plan_concept(concept: dict) -> list[str]:
    # Normalize slug before validation (LLM may output hyphens/whitespace which 
    # the schema regex ^[a-z0-9_]+$ rejects — normalize to underscores first).
    slug = concept.get("slug", "")
    if isinstance(slug, str):
        concept["slug"] = re.sub(r"[^a-z0-9_]", "_", slug.lower())
    
    required = ["title", "slug", "logline", "genre", "target_audience", "themes", "selling_points", "world_summary", "world_rules", "locations"]
    errors = []
    for field in required:
        val = concept.get(field)
        if val is None:
            errors.append(f"{field} (missing)")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"{field} (empty)")
        elif isinstance(val, list) and len(val) == 0:
            errors.append(f"{field} (empty list)")
    locations = concept.get("locations")
    if isinstance(locations, list):
        for index, location in enumerate(locations):
            if not isinstance(location, dict):
                errors.append(f"locations[{index}] (must be object)")
                continue
            for key in ("name", "kind", "current_state"):
                if not isinstance(location.get(key), str) or not location[key].strip():
                    errors.append(f"locations[{index}].{key}")
            constraints = location.get("immutable_constraints")
            if not isinstance(constraints, list) or not constraints or not all(isinstance(item, str) and item.strip() for item in constraints):
                errors.append(f"locations[{index}].immutable_constraints")
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
    return engine._existing_slugs()


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
    slug = slug[:MAX_SERIES_SLUG_LENGTH]
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

    # Commit reviews as immutable artifacts (each needs its own attempt)
    engine._move_to_final_dir()
    engine._begin_attempt("plan.concept.review", "review")
    engine._commit_artifact(artifact_type="review", logical_key="series_concept_review", payload={"issues": concept_review.get("issues", [])}, payload_name="series_concept_review.json")
    engine._begin_attempt("plan.characters.review", "review")
    engine._commit_artifact(artifact_type="review", logical_key="series_characters_review", payload={"issues": chars_review.get("issues", [])}, payload_name="series_characters_review.json")
    engine._begin_attempt("plan.volumes.review", "review")
    engine._commit_artifact(artifact_type="review", logical_key="series_volumes_review", payload={"issues": vols_review.get("issues", [])}, payload_name="series_volumes_review.json")

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
        "locations": concept.get("locations", []),
        "main_characters": characters.get("main_characters", []),
        "planned_volumes": planned_volumes,
    }

    engine._begin_attempt("plan", "assemble")
    engine._commit_artifact(artifact_type="plan", logical_key="series_plan", payload=result, payload_name="series_plan.json")
    engine._state.status = "企画済"

    # ── Series Bible v2 seed (the canonical source of truth) ──────────────
    # Every later Canon change must be an event replayed from this immutable
    # seed.  Legacy bible.json is NOT written: v2 projects have a single
    # mutation route (Canon Events); the materialized canon/bible.json is a
    # regenerable cache, never a second write path.
    CanonEventStore(engine._series_dir / "canon").write_seed(BibleFactory.create_seed(result))
    engine._log.info(f"✓ Canon v2 seed created: title='{result['title']}'")

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
            return slug[:MAX_SERIES_SLUG_LENGTH]
    h = hashlib.md5(title.encode()).hexdigest()[:12]
    return f"series_{h}"


def _generate_plan_concept(engine: NovelEngineBase, keywords: str, system: str, existing_slugs: set[str]) -> tuple[dict, dict]:
    slugs_text = ", ".join(sorted(existing_slugs)) if existing_slugs else "（なし）"
    prompt = engine._prompts.render(
        "plan_concept_generate.md",
        {"keywords": keywords, "lang": engine._lang, "existing_slugs": slugs_text},
    )
    return generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "plan.concept.generate", system, p, get_schema_resource("plan.concept.generate"), seed_offset=s
        ),
        validate_fn=_validate_plan_concept,
        review_fn=lambda r, sys: _review_plan_concept(engine, r, sys, keywords),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_concept(engine, r, rv, sys, keywords, so),
        system=system,
        user_prompt=prompt,
        engine=engine,
        kind="plan.concept",
        llm=engine._llm,
        quality=engine._quality,
    )


def _review_plan_concept(
    engine: NovelEngineBase,
    concept: dict,
    system: str,
    keywords: str,
) -> dict:
    text = json.dumps(concept, ensure_ascii=False, indent=2)
    user = engine._prompts.render(
        "plan_concept_review.md", {"plan_text": text, "keywords": keywords, "lang": engine._lang}
    )
    return engine._llm.complete_json("plan.concept.review", system, user)


def _revise_plan_concept(
    engine: NovelEngineBase,
    concept: dict,
    review: dict,
    system: str,
    keywords: str,
    seed_offset: int = 0,
) -> dict:
    review_text = format_review_text(review)
    # Pass full JSON so the LLM can locate exact before/after text from review
    prompt = engine._prompts.render(
        "plan_concept_revise.md",
        {"current_plan": json.dumps(concept, ensure_ascii=False, indent=2),
         "review": review_text, "keywords": keywords},
    )
    return engine._llm.complete_json("plan.concept.revise", system, prompt)


def _generate_plan_characters(engine: NovelEngineBase, concept: dict, system: str, used_names: set[str]) -> tuple[dict, dict]:
    import json
    series_plan_json = json.dumps(concept, ensure_ascii=False, indent=2)
    prompt = engine._prompts.render(
        "plan_characters_generate.md",
        {
            "series_plan_json": series_plan_json,
            "lang": engine._lang,
            "used_names": ", ".join(sorted(used_names)) if used_names else "（なし）",
        },
    )
    return generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "plan.characters.generate",
            system,
            p,
            get_schema_resource("plan.characters.generate"),
            seed_offset=s,
        ),
        validate_fn=_validate_plan_characters,
        review_fn=lambda r, sys: _review_plan_characters(engine, r, concept, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_characters(engine, r, rv, concept, sys, so),
        system=system,
        user_prompt=prompt,
        engine=engine,
        kind="plan.characters",
        llm=engine._llm,
        quality=engine._quality,
    )


def _review_plan_characters(engine: NovelEngineBase, characters: dict, concept: dict, system: str) -> dict:
    text = json.dumps(characters, ensure_ascii=False, indent=2)
    user = engine._prompts.render(
        "plan_characters_review.md", {"characters": text, "concept_json": json.dumps(concept, ensure_ascii=False, indent=2), "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "plan.characters.review", system, user,
    )


def _revise_plan_characters(
    engine: NovelEngineBase, characters: dict, review: dict, concept: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "plan_characters_revise.md",
        {
            "current_characters": json.dumps(characters, ensure_ascii=False, indent=2),
            "concept_text": json.dumps(concept, ensure_ascii=False, indent=2),
            "review": review_text,
        },
    )
    return engine._llm.complete_json(
        "plan.characters.revise", system, prompt
    )


def _generate_plan_volumes(engine: NovelEngineBase, concept: dict, characters: dict, system: str) -> tuple[dict, dict]:
    char_lines = ["メインキャラクター:"]
    for c in characters.get("main_characters", []):
        char_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
    prompt = engine._prompts.render(
        "plan_volumes_generate.md",
        {
            "core_text": f"タイトル: {concept.get('title', '')}\nあらすじ: {concept.get('logline', '')}\n世界観: {concept.get('world_summary', '')}",
            "characters_text": "\n".join(char_lines),
            "lang": engine._lang,
        },
    )
    return generate_and_review(
        generate_fn=lambda p, s: engine._llm.complete_json(
            "plan.volumes.generate", system, p, get_schema_resource("plan.volumes.generate"), seed_offset=s
        ),
        validate_fn=_validate_plan_volumes,
        review_fn=lambda r, sys: _review_plan_volumes(engine, r, concept, characters, sys),
        revise_fn=lambda r, rv, sys, so=0: _revise_plan_volumes(engine, r, rv, concept, sys, so),
        system=system,
        user_prompt=prompt,
        engine=engine,
        kind="plan.volumes",
        llm=engine._llm,
        quality=engine._quality,
    )


def _review_plan_volumes(
    engine: NovelEngineBase, volumes: dict, concept: dict, characters: dict, system: str
) -> dict:
    text = json.dumps(volumes, ensure_ascii=False, indent=2)
    user = engine._prompts.render(
        "plan_volumes_review.md", {"volumes": text, "volumes_json": json.dumps(volumes, ensure_ascii=False, indent=2), "lang": engine._lang}
    )
    return engine._llm.complete_json(
        "plan.volumes.review", system, user,
    )


def _revise_plan_volumes(
    engine: NovelEngineBase, volumes: dict, review: dict, concept: dict, system: str, seed_offset: int = 0
) -> dict:
    review_text = format_review_text(review)
    prompt = engine._prompts.render(
        "plan_volumes_revise.md",
        {
            "current_volumes": json.dumps(volumes, ensure_ascii=False, indent=2),
            "concept_text": json.dumps(concept, ensure_ascii=False, indent=2),
            "review": review_text,
        },
    )
    revised = engine._llm.complete_json(
        "plan.volumes.revise", system, prompt
    )
    # NOTE: 機械的な before→after 置換は行わない。
    # 指摘箇所以外との不整合を防ぐため、LLM の改訂出力をそのまま使用する。
    return cast(dict, revised)
