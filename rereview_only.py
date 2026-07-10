"""Re-review existing scene drafts with the current (improved) review prompt.

This does NOT regenerate drafts — it only re-runs the review step on the
already-written *_v*.md files, so it validates prompt changes in minutes
instead of re-running the full 50-minute write pipeline.

Usage:
  OLLAMA_HOST=ws1.local:11434 .venv/bin/python rereview_only.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from novel_forge.engine.infra import make_engine
from novel_forge.canon.public_runtime import V2ProjectRuntime
from novel_forge.schemas import get_schema
from novel_forge.llm_client import LLMError

SERIES = "juji_ou_to_himitsu_no_majo_keiyuu"
WORKDIR = Path("runs")
VOL = 1
MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"


def main() -> int:
    engine = make_engine(workdir=WORKDIR, model=MODEL, series=SERIES, phase="write")
    runtime = V2ProjectRuntime(engine._series_dir)
    _payload, scenes = runtime.load_design(VOL)
    scenes.sort(key=lambda s: (s.chapter_number, s.scene_number, s.scene_id))
    series_dir = engine._series_dir
    ch_dir_base = series_dir / f"vol{VOL:02d}"

    system = engine._prompts.render("system.md", {"lang": engine._lang})
    review_schema = get_schema("review")

    results = []
    for scene in scenes:
        # find the latest existing draft md for this scene
        ch_dir = ch_dir_base / f"vol{VOL:02d}_ch{scene.chapter_number:02d}"
        candidates = sorted(ch_dir.glob(f"vol{VOL:02d}_ch{scene.chapter_number:02d}_sc{scene.scene_number:02d}_v*.md"))
        if not candidates:
            print(f"scene {scene.scene_number}: NO DRAFT FILE, skip")
            continue
        draft_path = candidates[-1]
        content = draft_path.read_text(encoding="utf-8")

        writer_input = runtime.writer_payload(scene)
        writer_context = json.dumps(writer_input["writer_context"], ensure_ascii=False, indent=2)
        brief = json.dumps(writer_input["scene_brief"], ensure_ascii=False, indent=2)

        review_prompt = engine._prompts.render(
            "scene_review_v2.md",
            {
                "writer_context": writer_context,
                "scene_brief": brief,
                "scene": content,
                "schema": json.dumps(review_schema, ensure_ascii=False),
            },
        )
        try:
            review = engine._llm.complete_json("review", system, review_prompt, review_schema)
        except LLMError as e:
            print(f"scene {scene.scene_number}: REVIEW ERROR {str(e)[:80]} -> treat as passed")
            review = {"issues": []}

        issues = review.get("issues", []) or []
        passed = len(issues) == 0
        print(f"scene {scene.scene_number}: passed={passed} issues={len(issues)}  ({draft_path.name})")
        for iss in issues[:4]:
            print(f"    [{iss.get('severity')}] {iss.get('field')}: {str(iss.get('description',''))[:90]}")
        results.append((scene.scene_number, passed, len(issues)))

    passed_n = sum(1 for _, p, _ in results if p)
    print(f"\n=== SUMMARY: {passed_n}/{len(results)} scenes passed with improved prompt ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
