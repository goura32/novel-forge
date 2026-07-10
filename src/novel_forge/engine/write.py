"""Public v2 scene writing for NovelEngine.

The writer input boundary is deliberately narrow: persisted ``SceneDesign``
writer_context + narrative brief + the immediately preceding scene summary.
It never opens legacy outlines, Bible/Canon files, Blackboard, or prior drafts.
"""

from __future__ import annotations

import json
from typing import Any

from novel_forge.canon.design import SceneDesign
from novel_forge.canon.public_runtime import V2ProjectRuntime
from novel_forge.llm_client import LLMError
from novel_forge.schemas import get_schema


def _scene_brief(scene: SceneDesign) -> dict[str, Any]:
    return {
        "title": scene.title,
        "goal": scene.goal,
        "conflict": scene.conflict,
        "turning_point": scene.turning_point,
        "outcome": scene.outcome,
        "ending_hook": scene.ending_hook,
        "key_events": scene.key_events,
    }


def _summary_path(engine, volume: int):
    return engine._series_dir / f"vol{volume:02d}" / "scene_summaries.json"


def _load_summaries(engine, volume: int) -> dict[str, str]:
    path = _summary_path(engine, volume)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in raw.items()} if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_summaries(engine, volume: int, summaries: dict[str, str]) -> None:
    path = _summary_path(engine, volume)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _write_draft(engine, volume: int, scene: SceneDesign, content: str, version: int = 1) -> str:
    ch_dir = engine._series_dir / f"vol{volume:02d}" / f"vol{volume:02d}_ch{scene.chapter_number:02d}"
    ch_dir.mkdir(parents=True, exist_ok=True)
    path = ch_dir / f"vol{volume:02d}_ch{scene.chapter_number:02d}_sc{scene.scene_number:02d}_v{version}.md"
    path.write_text(content, encoding="utf-8")
    return str(path)


def _revise_scene_draft(engine, scene: SceneDesign, writer_context: str, brief: str,
                        content: str, review: dict, system: str, seed_offset: int = 0) -> str:
    """Apply review issues to the scene draft. Returns revised content."""
    prompt = engine._prompts.render(
        "scene_revision_v2.md",
        {
            "writer_context": writer_context,
            "scene_brief": brief,
            "scene": content,
            "review": json.dumps(review, ensure_ascii=False, indent=2),
            "schema": json.dumps(get_schema("scene_draft"), ensure_ascii=False),
        },
    )
    revised = engine._llm.complete_json("scene_draft", system, prompt, get_schema("scene_draft"), seed_offset=seed_offset)
    return str(revised.get("content", content))


def write(engine, volume_number: int | None = None) -> list[dict[str, Any]]:
    """Write persisted v2 SceneDesign artifacts through the writer boundary."""
    vol_num = volume_number or engine.state.current_volume
    runtime = V2ProjectRuntime(engine._series_dir)
    _payload, scenes = runtime.load_design(vol_num)
    scenes.sort(key=lambda item: (item.chapter_number, item.scene_number, item.scene_id))

    engine.state.current_volume = vol_num
    engine._state.status = "執筆中"
    vol = engine._current_volume()
    vol.status = "執筆中"
    summaries = _load_summaries(engine, vol_num)
    previous_summary = "（最初のシーン）"
    results: list[dict[str, Any]] = []
    system = engine._prompts.render("system.md", {"lang": engine._lang})

    for scene in scenes:
        if scene.writer_context is None:
            raise ValueError(f"v2 SceneDesign {scene.scene_id} has no writer_context")
        record = engine._get_or_create_scene_record(vol, scene.scene_number)
        if record.status in ("修正済", "強制出力済"):
            if scene.scene_id not in summaries:
                raise ValueError(f"completed v2 scene {scene.scene_id} has no persisted summary")
            previous_summary = summaries[scene.scene_id]
            continue

        writer_input = runtime.writer_payload(scene)
        writer_context = json.dumps(writer_input["writer_context"], ensure_ascii=False, indent=2)
        brief = json.dumps(writer_input["scene_brief"], ensure_ascii=False, indent=2)
        prompt = engine._prompts.render(
            "scene_draft_v2.md",
            {
                "writer_context": writer_context,
                "scene_brief": brief,
                "previous_scene_summary": previous_summary,
                "schema": json.dumps(get_schema("scene_draft"), ensure_ascii=False),
            },
        )
        generated = engine._llm.complete_json("scene_draft", system, prompt, get_schema("scene_draft"))
        content = str(generated.get("content", ""))

        review_prompt = engine._prompts.render(
            "scene_review_v2.md",
            {
                "writer_context": writer_context,
                "scene_brief": brief,
                "scene": content,
                "schema": json.dumps(get_schema("review"), ensure_ascii=False),
            },
        )
        try:
            review = engine._llm.complete_json("review", system, review_prompt, get_schema("review"))
        except LLMError as e:
            engine._log.warning("  [REVIEW ERROR] scene_draft: %s — 本文を維持して強制出力します", str(e)[:120])
            review = {"issues": []}
            qg_result = engine._quality.check_scene(review)
            record.status = "強制出力済"
            record.draft_version = 1
            record.draft_path = _write_draft(engine, vol_num, scene, content, version=1)
            record.quality_retries = 1
            record.quality_gate = qg_result
            summary = content[:500].strip() or "（本文なし）"
            summaries[scene.scene_id] = summary
            _save_summaries(engine, vol_num, summaries)
            previous_summary = summary
            results.append({"scene_id": scene.scene_id, "scene_number": scene.scene_number, "status": record.status})
            engine._save()
            continue

        # Review → revise loop (mirrors design phase quality assurance)
        # `passed` is sticky: once a cycle clears all critical issues, we keep
        # it True even if the next review adds only important/minor notes. This
        # avoids re-revising forever over non-blocking nitpicks (the 35B review
        # model over-labels severity, so a fully-passing scene is rare).
        qg_result = engine._quality.check_scene(review)
        passed = qg_result.passed
        revision_cycle = 0
        max_revisions = engine._quality.review_max_count
        while not passed and revision_cycle < max_revisions:
            try:
                content = _revise_scene_draft(
                    engine, scene, writer_context, brief, content, review, system, seed_offset=revision_cycle + 1
                )
            except LLMError as e:
                engine._log.warning("  [REVISE ERROR] scene_draft: %s — 改訂を断念します", str(e)[:120])
                break
            try:
                review_prompt = engine._prompts.render(
                    "scene_review_v2.md",
                    {
                        "writer_context": writer_context,
                        "scene_brief": brief,
                        "scene": content,
                        "schema": json.dumps(get_schema("review"), ensure_ascii=False),
                    },
                )
                review = engine._llm.complete_json("review", system, review_prompt, get_schema("review"))
            except LLMError as e:
                engine._log.warning("  [REVIEW ERROR] scene_draft: %s — 改訂結果を維持して強制出力します", str(e)[:120])
                review = {"issues": []}
            cycle_result = engine._quality.check_scene(review)
            # Persist the *final* review for human inspection even when it did
            # not pass the automated gate. `passed` remains sticky separately
            # so a later non-blocking note cannot re-open a cleared scene.
            qg_result = cycle_result
            if cycle_result.passed:
                passed = True
            revision_cycle += 1
            if not passed:
                engine._log.warning(
                    "  [REVIEW ABANDONED] scene_draft: 改訂が必要だが max_review_count に達したため改訂を諦めて次工程へ進みます (%d/%d)。",
                    revision_cycle, max_revisions,
                )

        record.status = "修正済" if passed else "強制出力済"
        record.draft_version = 1 + revision_cycle
        record.draft_path = _write_draft(engine, vol_num, scene, content, version=record.draft_version)
        record.quality_retries = 1 + revision_cycle
        record.quality_gate = qg_result

        # A scene summary is a writer-side continuity artifact only.  It is not
        # Canon data and is intentionally derived without reopening the draft.
        summary = content[:500].strip() or "（本文なし）"
        summaries[scene.scene_id] = summary
        _save_summaries(engine, vol_num, summaries)
        previous_summary = summary
        results.append({"scene_id": scene.scene_id, "scene_number": scene.scene_number, "status": record.status})
        engine._save()

    _save_summaries(engine, vol_num, summaries)
    vol.status = "初稿済"
    engine._state.status = "初稿済"
    engine._save()
    engine._log.info("✓ v2 Write: volume=%s scenes=%s", vol_num, len(results))
    return results
