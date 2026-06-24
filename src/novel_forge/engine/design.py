"""Volume design generation — 3-phase: volume → chapter → scene."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from novel_forge.schemas import get_schema

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase
else:
    NovelEngineBase = object


class DesignMixin(NovelEngineBase):  # type: ignore[misc]
    """Volume design generation methods for NovelEngine."""

    def design(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        self._state.status = "デザイン済"
        slug = self._slug
        if not slug:
            raise ValueError("Design: slug is empty — run 'plan' first or specify --series")

        # Plan info for progress
        plan_path = self._series_dir / "series_plan.json"
        total_vol = "?"
        if plan_path.exists():
            try:
                import json as _json
                plan = _json.loads(plan_path.read_text(encoding="utf-8"))
                total_vol = len(plan.get("planned_volumes", []))
            except Exception:
                pass

        self._log.info(f"▶ Design: slug='{slug}' vol={vol_num}/{total_vol}")
        system = self._prompts.render("system.md", {"lang": self._lang})
        genre = self._ctx_builder.get_genre()
        series_plan = self._ctx_builder.get_series_plan_summary()

        # Phase 1: Volume design (chapters)
        self._log.info(f"  ▶ volume_design — vol={vol_num}/{total_vol}")
        chapters = self._generate_volume_design(series_plan, genre, vol_num, system)
        chapters_count = len(chapters)
        self._log.info(f"  ✓ volume_design — vol={vol_num} {chapters_count} ch done")

        # Phase 2: Chapter design
        self._log.info(f"  ▶ chapter_design — vol={vol_num} {chapters_count} ch")
        chapters = self._generate_chapter_designs(chapters, series_plan, vol_num, system)
        self._log.info(f"  ✓ chapter_design — vol={vol_num} {len(chapters)}/{chapters_count} ch done")

        # Phase 3: Scene design — estimate total scenes
        est_scenes = sum(self._estimate_scene_count(ch.get("purpose", "展開")) for ch in chapters)
        self._log.info(f"  ▶ scene_design — vol={vol_num} {chapters_count} ch (~{est_scenes} sc)")
        scenes = self._generate_scene_designs(chapters, series_plan, vol_num, system)
        self._log.info(f"  ✓ scene_design — vol={vol_num} {len(scenes)}/{est_scenes} sc done")

        # Build result
        chapters_with_scenes = []
        for i, ch in enumerate(chapters, 1):
            ch_scenes = [s for s in scenes if s.get("chapter_number") == i]
            chapters_with_scenes.append({
                "number": i, "title": ch.get("title", ""),
                "purpose": ch.get("purpose", ""), "scenes": ch_scenes,
            })

        vol = self._current_volume()
        vol.status = "デザイン済"
        result = {"title": f"第{vol_num}巻", "premise": "", "chapters": chapters_with_scenes, "scenes": scenes}

        # Save
        vol_dir = self._series_dir / f"vol{vol_num:02d}"
        vol_dir.mkdir(parents=True, exist_ok=True)
        self._save_path(vol_num, f"vol{vol_num:02d}.json", result)

        for ch in result.get("chapters", []):
            ch_num = ch["number"]
            ch_path = vol_dir / f"vol{vol_num:02d}_ch{ch_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}.json"
            ch_path.parent.mkdir(parents=True, exist_ok=True)
            ch_path.write_text(json.dumps(ch, ensure_ascii=False, indent=2), encoding="utf-8")

        for sc in result.get("scenes", []):
            sc_num = sc.get("number", 0)
            ch_num = sc.get("chapter_number", 0)
            sc_path = vol_dir / f"vol{vol_num:02d}_ch{ch_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}.json"
            sc_path.parent.mkdir(parents=True, exist_ok=True)
            sc_path.write_text(json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")

        self._save()
        self._log.info(f"✓ Design: series='{slug}' vol={vol_num} — {len(chapters)} ch, {len(scenes)} sc")
        return result

    # ── Phase 1: Volume design ──────────────────────────────────────────

    def _generate_volume_design(self, series_plan: str, genre: str, vol_num: int, system: str) -> list[dict]:
        schema = get_schema("volume_design")
        prompt = self._prompts.render("volume_design.md",
                                      {"series_plan": series_plan, "volume_number": str(vol_num), "genre": genre, "lang": self._lang})
        result = self._llm.complete_json("volume_design", system, prompt, schema)
        if isinstance(result, dict):
            return result.get("chapters", [result]) if "chapters" in result else [result]
        elif isinstance(result, list):
            return result
        return []

    @staticmethod
    def _default_purpose(i: int, total: int) -> str:
        if i == 1:
            return "導入"
        if i == total:
            return "収束"
        return "展開"

    # ── Phase 2: Chapter design ─────────────────────────────────────────

    def _generate_chapter_designs(self, chapters: list[dict], series_plan: str, vol_num: int, system: str) -> list[dict]:
        designs = []
        total = len(chapters)
        for i, ch in enumerate(chapters, 1):
            ch_title = ch.get("title", f"第{i}章")
            ch_purpose = ch.get("purpose") or self._default_purpose(i, total)
            prompt = self._prompts.render("chapter_design.md",
                                          {"series_plan": series_plan, "volume_number": str(vol_num), "chapter_number": str(i),
                                           "chapter_title": ch_title, "chapter_purpose": ch_purpose, "lang": self._lang})
            design = self._llm.complete_json("chapter_design", system, prompt, get_schema("chapter_design"))
            design["number"] = i
            design["title"] = ch_title
            designs.append(design)
        return designs

    # ── Phase 3: Scene design ───────────────────────────────────────────

    def _generate_scene_designs(self, chapters: list[dict], series_plan: str, vol_num: int, system: str) -> list[dict]:
        scenes = []
        counter = 1
        for i, ch in enumerate(chapters, 1):
            ch_title = ch.get("title", f"第{i}章")
            ch_purpose = ch.get("purpose", "展開")
            scene_count = self._estimate_scene_count(ch_purpose)
            for sc_idx in range(scene_count):
                prompt = self._prompts.render("scene_design.md",
                                              {"series_plan": series_plan, "volume_number": str(vol_num),
                                               "chapter_title": ch_title, "chapter_purpose": ch_purpose,
                                               "scene_number": str(counter), "chapter_scene_number": str(sc_idx + 1),
                                               "chapter_scene_count": str(scene_count), "lang": self._lang})
                scene = self._llm.complete_json("scene_design", system, prompt, get_schema("scene_design"))
                scene["chapter_number"] = i
                scene["number"] = counter
                scenes.append(scene)
                counter += 1
        return scenes

    @staticmethod
    def _estimate_scene_count(purpose: str) -> int:
        counts = {"導入": 2, "展開": 3, "転換": 3, "クライマックス": 4, "収束": 2}
        return counts.get(purpose, 3)
