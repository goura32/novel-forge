"""Semantic validators for cross-field artifact consistency.

JSON Schema catches local shape/type errors. These validators catch constraints that
span multiple fields or lists, such as duplicate sequence numbers and broken
chapter/scene references.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

_SWAP_TITLE_MARKERS = ("入れ替わり", "入れ替わる", "入れ替え")
_SWAP_MECHANISM_MARKERS = (
    "入れ替わり",
    "入れ替わる",
    "入れ替え",
    "入れ替えられ",
    "交換",
)
_SUBSTITUTION_ONLY_MARKERS = ("身代わり", "代役", "替え玉")


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _iter_text_values(value: Any, path: str = ""):
    if isinstance(value, str):
        yield path or "(root)", value
    elif isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _iter_text_values(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]"
            yield from _iter_text_values(item, child_path)


def validate_series_plan_concept_semantics(data: dict[str, Any]) -> list[str]:
    """Validate cross-field concept consistency."""
    errors: list[str] = []

    title = data.get("title")
    if isinstance(title, str) and any(marker in title for marker in _SWAP_TITLE_MARKERS):
        world_rules = data.get("world_rules")
        if not isinstance(world_rules, list):
            world_rules = []
        core_values = [
            data.get("logline", ""),
            data.get("world_summary", ""),
            *world_rules,
        ]
        core_text = "\n".join(value for value in core_values if isinstance(value, str))
        has_swap_mechanism = any(marker in core_text for marker in _SWAP_MECHANISM_MARKERS)
        has_substitution_only = any(marker in core_text for marker in _SUBSTITUTION_ONLY_MARKERS)
        if not has_swap_mechanism:
            detail = (
                "substitution-only wording is present" if has_substitution_only else "core fields omit the swap mechanism"
            )
            errors.append(
                "[series_plan_concept] swap gimmick mismatch: title promises 入れ替わり, "
                f"but logline/world_summary/world_rules do not define a concrete swap mechanism ({detail})."
            )
    return errors


def validate_volume_design_semantics(data: dict[str, Any]) -> list[str]:
    """Validate final volume design chapter/scene numbering consistency."""
    errors: list[str] = []

    chapters = data.get("chapters", [])
    scenes = data.get("scenes", [])
    if not isinstance(chapters, list):
        chapters = []
    if not isinstance(scenes, list):
        scenes = []

    chapter_numbers: list[int] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter_number = _positive_int(chapter.get("number"))
        if chapter_number is not None:
            chapter_numbers.append(chapter_number)

    for number, count in sorted(Counter(chapter_numbers).items()):
        if count > 1:
            errors.append(f"duplicate chapter number: {number}")

    top_level_scene_numbers: list[int] = []
    top_level_scene_refs: dict[int, int] = {}
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_number = _positive_int(scene.get("number") or scene.get("scene_number"))
        chapter_number = _positive_int(scene.get("chapter_number"))
        if scene_number is not None:
            top_level_scene_numbers.append(scene_number)
            if chapter_number is not None:
                top_level_scene_refs[scene_number] = chapter_number

    for number, count in sorted(Counter(top_level_scene_numbers).items()):
        if count > 1:
            errors.append(f"duplicate scene number: {number}")

    known_chapters = set(chapter_numbers)
    for scene_number, chapter_number in sorted(top_level_scene_refs.items()):
        if known_chapters and chapter_number not in known_chapters:
            errors.append(
                f"scene {scene_number} references missing chapter {chapter_number}"
            )

    chapter_scene_refs: set[int] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        chapter_number = _positive_int(chapter.get("number"))
        if chapter_number is None:
            continue
        chapter_scenes = chapter.get("scenes", [])
        if not isinstance(chapter_scenes, list):
            continue
        local_numbers: list[int] = []
        for scene in chapter_scenes:
            if not isinstance(scene, dict):
                continue
            scene_number = _positive_int(scene.get("number") or scene.get("scene_number"))
            if scene_number is None:
                continue
            local_numbers.append(scene_number)
            chapter_scene_refs.add(scene_number)
            embedded_chapter = _positive_int(scene.get("chapter_number"))
            if embedded_chapter is not None and embedded_chapter != chapter_number:
                errors.append(
                    f"chapter {chapter_number} contains scene {scene_number} "
                    f"with chapter_number={embedded_chapter}"
                )
            top_chapter = top_level_scene_refs.get(scene_number)
            if top_chapter is None:
                errors.append(
                    f"chapter {chapter_number} references scene {scene_number} "
                    "missing from top-level scenes"
                )
            elif top_chapter != chapter_number:
                errors.append(
                    f"chapter {chapter_number} references scene {scene_number} "
                    f"but top-level scene has chapter_number={top_chapter}"
                )
        for number, count in sorted(Counter(local_numbers).items()):
            if count > 1:
                errors.append(f"chapter {chapter_number} has duplicate scene number: {number}")

    if chapter_scene_refs:
        for scene_number in sorted(set(top_level_scene_numbers) - chapter_scene_refs):
            errors.append(f"top-level scene {scene_number} is not referenced by any chapter")

    return errors
