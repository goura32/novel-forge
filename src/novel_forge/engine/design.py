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

    DEFAULT_SCENE_COUNT: int = 3

    def design(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        self._state.status = "デザイン済"
        self._log.info(f"Design started: volume={vol_num}")

        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._ctx_builder.get_series_plan_summary()
        genre = self._ctx_builder.get_genre()

        # Phase 1: Volume design (chapters)
        self._log.info("  [PHASE START] volume_design")
        chapters = self._generate_volume_design(series_plan, genre, vol_num, system)
        self._log.info(f"  [PHASE END] volume_design: {len(chapters)} chapters")

        # Phase 2: Chapter design
        self._log.info("  [PHASE START] chapter_design")
        chapters = self._generate_chapter_designs(chapters, series_plan, vol_num, system)
        self._log.info(f"  [PHASE END] chapter_design")

        # Phase 3: Scene design
        self._log.info("  [PHASE START] scene_design")
        scenes = self._generate_scene_designs(chapters, series_plan, vol_num, system)
        self._log.info(f"  [PHASE END] scene_design: {len(scenes)} scenes")

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
        self._log.info(f"Design finished: volume={vol_num}")
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
    def _validate_chapters(data: dict) -> list[str]:
        errors = []
        chapters = data.get("chapters", [])
        if not chapters:
            errors.append("chapters: must contain at least one chapter")
        for i, ch in enumerate(chapters):
            if not ch.get("title"):
                errors.append(f"chapters[{i}].title")
            if ch.get("purpose") not in ("導入", "展開", "転換", "クライマックス", "収束"):
                errors.append(f"chapters[{i}].purpose")
        return errors

    def _review_volume_design(self, result: list[dict], system: str, seed_offset: int = 0) -> dict:
        text = "\n".join([f"第{ch['number']}章: {ch['title']}（{ch.get('purpose', '')}）" for ch in result])
        prompt = self._prompts.render("volume_design_review.md", {"chapters": text, "lang": self._lang})
        return self._llm.complete_json("volume_design_review", system, prompt, get_schema("volume_design_review"), seed_offset=seed_offset)

    def _revise_volume_design(self, result: list[dict], review: dict, system: str, seed_offset: int = 0) -> list[dict]:
        review_text = self._format_review_text(review)
        prompt = self._prompts.render("volume_design_revision.md",
                                      {"current_design": json.dumps(result, ensure_ascii=False), "review": review_text, "lang": self._lang})
        revised = self._llm.complete_json("volume_design_revision", system, prompt, get_schema("volume_design_revision"), seed_offset=seed_offset)
        if isinstance(revised, dict) and "chapters" in revised:
            return revised["chapters"]
        return revised if isinstance(revised, list) else result

    def _phase_volume_design(self, series_plan: str, genre: str, vol_num: int, system: str) -> list[dict]:
        chapters = self._generate_volume_design(series_plan, genre, vol_num, system)
        # Attach numbers
        for i, ch in enumerate(chapters, 1):
            ch["number"] = i
        result = {"chapters": chapters}
        errors = self._validate_chapters(result)
        if errors:
            self._log.warning("  [VALIDATION FAIL] volume_design: %s", errors)
        return chapters

    # ── Phase 2: Chapter design ─────────────────────────────────────────

    def _generate_chapter_designs(self, chapters: list[dict], series_plan: str, vol_num: int, system: str) -> list[dict]:
        designs = []
        result = {}
        for i, ch in enumerate(chapters, 1):
            ch_title = ch.get("title", f"第{i}章")
            ch_purpose = ch.get("purpose", "展開")
            prompt = self._prompts.render("chapter_design.md",
                                          {"series_plan": series_plan, "volume_number": str(vol_num), "chapter_number": str(i),
                                           "chapter_title": ch_title, "chapter_purpose": ch_purpose, "lang": self._lang})
            design = self._llm.complete_json("chapter_design", system, prompt, get_schema("chapter_design"))
            design["number"] = i
            design["title"] = ch_title
            designs.append(design)
        return designs

    @staticmethod
    def _validate_chapter_design(data: dict) -> list[str]:
        errors = []
        if not data.get("theme"):
            errors.append("theme")
        if not data.get("emotional_arc"):
            errors.append("emotional_arc")
        return errors

    def _review_chapter_design(self, design: dict, system: str, seed_offset: int = 0) -> dict:
        prompt = self._prompts.render("chapter_design_review.md",
                                      {"chapter_title": design.get("title", ""), "chapter_purpose": design.get("purpose", ""),
                                       "chapter_theme": design.get("theme", ""), "chapter_emotional_arc": design.get("emotional_arc", ""),
                                       "lang": self._lang})
        review = self._llm.complete_json("chapter_design_review", system, prompt, get_schema("chapter_design_review"))
        # Merge review fields into design
        if isinstance(review, dict):
            for k in ("issues", "strengths", "recommendations", "tones"):
                if k in review:
                    design[k] = review[k]
        return design

    def _revise_chapter_design(self, design: dict, review: dict, system: str, seed_offset: int = 0) -> dict:
        review_text = self._format_review_text(review)
        current = f"章タイトル: {design.get('title', '')}\n役割: {design.get('purpose', '')}\nテーマ: {design.get('theme', '')}\n感情の弧: {design.get('emotional_arc', '')}"
        prompt = self._prompts.render("chapter_design_revision.md",
                                      {"current_design": current, "review": review_text, "lang": self._lang})
        result = self._llm.complete_json("chapter_design_revision", system, prompt, get_schema("chapter_design_revision"))
        result["number"] = design.get("number")
        result["title"] = result.get("title", design.get("title", ""))
        return result

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

    @staticmethod
    def _validate_scene_design(data: dict) -> list[str]:
        errors = []
        if not data.get("goal"):
            errors.append("goal")
        if not data.get("outcome"):
            errors.append("outcome")
        return errors

    def _review_scene_design(self, scene: dict, system: str, seed_offset: int = 0) -> dict:
        prompt = self._prompts.render("scene_design_review.md",
                                      {"scene_title": scene.get("title", ""), "scene_goal": scene.get("goal", ""),
                                       "scene_outcome": scene.get("outcome", ""), "lang": self._lang})
        review = self._llm.complete_json("scene_design_review", system, prompt, get_schema("scene_design_review"))
        if isinstance(review, dict):
            for k in ("issues", "revisions_needed", "tones"):
                if k in review:
                    scene[k] = review[k]
        return scene

    def _revise_scene_design(self, scene: dict, review: dict, system: str, seed_offset: int = 0) -> dict:
        review_text = self._format_review_text(review)
        current = f"シーンタイトル: {scene.get('title', '')}\n目標: {scene.get('goal', '')}\n結果: {scene.get('outcome', '')}"
        prompt = self._prompts.render("scene_design_revision.md",
                                      {"current_design": current, "review": review_text, "lang": self._lang})
        result = self._llm.complete_json("scene_design_revision", system, prompt, get_schema("scene_design_revision"))
        result["chapter_number"] = scene.get("chapter_number")
        result["number"] = scene.get("number")
        return result

    # ── Utility ─────────────────────────────────────────────────────────

    @staticmethod
    def _format_review_text(review: dict) -> str:
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            sug = issue.get("suggestion", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
            if sug:
                lines.append(f"    提案: {sug}")
        for s in review.get("suggestions", []):
            lines.append(f"  推奨: {s}")
        return "\n".join(lines)
