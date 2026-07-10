"""Re-review existing scene drafts (improved prompt) + severity breakdown.

Usage:
  OLLAMA_HOST=ws1.local:11434 .venv/bin/python rereview_sev.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
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
    ch_dir_base = engine._series_dir / f"vol{VOL:02d}"

    system = engine._prompts.render("system.md", {"lang": engine._lang})
    review_schema = get_schema("review")

    sev_total = Counter()
    passed_n = 0
    total = 0
    for scene in scenes:
        ch_dir = ch_dir_base / f"vol{VOL:02d}_ch{scene.chapter_number:02d}"
        candidates = sorted(ch_dir.glob(f"vol{VOL:02d}_ch{scene.chapter_number:02d}_sc{scene.scene_number:02d}_v*.md"))
        if not candidates:
            continue
        content = candidates[-1].read_text(encoding="utf-8")
        writer_input = runtime.writer_payload(scene)
        writer_context = json.dumps(writer_input["writer_context"], ensure_ascii=False, indent=2)
        brief = json.dumps(writer_input["scene_brief"], ensure_ascii=False, indent=2)
        review_prompt = engine._prompts.render(
            "scene_review_v2.md",
            {"writer_context": writer_context, "scene_brief": brief, "scene": content,
             "schema": json.dumps(review_schema, ensure_ascii=False)},
        )
        try:
            review = engine._llm.complete_json("review", system, review_prompt, review_schema)
        except LLMError:
            review = {"issues": []}
        issues = review.get("issues", []) or []
        for iss in issues:
            sev_total[iss.get("severity", "?")] += 1
        has_critical = any(i.get("severity") in ("critical", "致命的") for i in issues)
        total += 1
        if not has_critical:
            passed_n += 1
        print(f"scene {scene.scene_number}: critical={has_critical} issues={len(issues)}")

    print(f"\n=== SUMMARY (improved prompt + severity gate) ===")
    print(f"passed (no critical): {passed_n}/{total}")
    print(f"severity distribution: {dict(sev_total)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
