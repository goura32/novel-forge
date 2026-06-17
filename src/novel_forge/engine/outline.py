"""Volume outline generation — outline, _generate_outline, _review_outline, _revise_outline."""

from __future__ import annotations

import json
from typing import Any

from novel_forge.models import VolumeOutline
from novel_forge.schemas import get_schema


class OutlineMixin:
    """Volume outline generation methods for NovelEngine."""

    def outline(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._ctx_builder.get_series_plan_summary()
        genre = self._ctx_builder.get_genre()
        schema = get_schema("volume_outline")
        previous_outline = self._get_previous_volume_outline(vol_num)

        result = self._generate_outline(series_plan, genre, vol_num, system, schema, previous_outline)
        review = self._review_outline(result, series_plan, previous_outline)

        # Review → Revise loop (max 3 retries)
        for retry in range(3):
            score = review.get("score", 0)
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
            if score >= 70 and len(critical_issues) == 0:
                break
            print(f"  [OUTLINE REVIEW] score={score}, critical={len(critical_issues)}, retry={retry+1}/3", flush=True)
            result = self._revise_outline(result, review, series_plan, genre, vol_num, system, schema, previous_outline)
            review = self._review_outline(result, series_plan, previous_outline)

        vol = self._current_volume()
        vol.status = "アウトライン済"
        self._state.status = "アウトライン済"
        result["volume_number"] = vol_num
        self._save_path(vol_num, "outline.json", result)
        self._save()
        return result

    def _get_previous_volume_outline(self, vol_num: int) -> str:
        """Get the outline summary of the previous volume, if it exists."""
        if vol_num <= 1:
            return ""
        prev_path = self._series_dir / f"vol{vol_num - 1:02d}" / "outline.json"
        if not prev_path.exists():
            raise RuntimeError(
                f"前巻（第{vol_num - 1}巻）のアウトラインが存在しません: {prev_path}\n"
                f"第{vol_num}巻のアウトラインを生成するには、先に第{vol_num - 1}巻のアウトラインを生成してください。"
            )
        try:
            data = json.loads(prev_path.read_text(encoding="utf-8"))
            lines = [f"前巻（第{vol_num - 1}巻）アウトライン:",
                     f"  タイトル: {data.get('title', '')}",
                     f"  前提: {data.get('premise', '')}", ""]
            for ch in data.get("chapters", []):
                lines.append(f"  第{ch['number']}章: {ch['title']}（{ch.get('purpose', '')}）")
                for sc in data.get("scenes", []):
                    if sc.get("chapter_number") == ch["number"]:
                        lines.append(f"    シーン{sc['number']}: {sc['title']}")
                        lines.append(f"      目標: {sc.get('goal', '')[:80]}")
                        lines.append(f"      結果: {sc.get('outcome', '')[:80]}")
            return "\n".join(lines)
        except (json.JSONDecodeError, KeyError) as e:
            raise RuntimeError(
                f"前巻（第{vol_num - 1}巻）のアウトライン読み込みに失敗しました: {e}"
            ) from e

    def _generate_outline(self, series_plan, genre, vol_num, system, schema, previous_outline=""):
        """Three-phase outline generation: chapter structure, chapter design, then scene-by-scene."""
        # Phase 1: Generate chapter structure
        chapter_schema = get_schema("chapter_outline")
        user = self._prompts.render(
            "chapter_outline.md",
            {"series_plan": series_plan, "volume_number": str(vol_num), "genre": genre,
             "lang": self._lang, "previous_outline": previous_outline},
        )
        chapters_result = self._llm.complete_json("chapter_outline", system, user, chapter_schema)

        # Normalize chapters_result to list of chapter dicts
        if isinstance(chapters_result, dict):
            chapters_list = chapters_result.get("chapters", [chapters_result])
        elif isinstance(chapters_result, list):
            chapters_list = chapters_result
        else:
            raise RuntimeError(
                f"章構成の生成に失敗しました: 予期しない型 {type(chapters_result).__name__}"
            )

        # Phase 2: Generate detailed chapter design for each chapter
        chapter_designs = []
        previous_chapter_outcome = ""
        prev_summary = previous_outline[:500] if previous_outline else ""

        for ch_idx, ch in enumerate(chapters_list, 1):
            ch_title = ch.get("title", f"第{ch_idx}章")
            ch_purpose = ch.get("purpose", "展開")

            user = self._prompts.render(
                "chapter_design.md",
                {
                    "series_plan": series_plan,
                    "volume_number": str(vol_num),
                    "volume_title": "",
                    "volume_premise": "",
                    "chapter_number": str(ch_idx),
                    "chapter_title": ch_title,
                    "chapter_purpose": ch_purpose,
                    "previous_chapter_outcome": previous_chapter_outcome,
                    "previous_volume_summary": prev_summary,
                    "lang": self._lang,
                },
            )
            design_schema = get_schema("chapter_design")
            design_result = self._llm.complete_json("chapter_design", system, user, design_schema)
            design_result["number"] = ch_idx
            design_result["title"] = ch_title
            chapter_designs.append(design_result)
            previous_chapter_outcome = design_result.get("emotional_arc", "")

        # Phase 3: Generate scenes for each chapter, one at a time
        all_scenes = []
        scene_counter = 1
        previous_outcome = ""

        # Build previous volume summary for context
        prev_summary = ""
        if previous_outline:
            prev_summary = previous_outline[:500]  # Truncate for context length

        for ch_idx, ch in enumerate(chapters_list, 1):
            ch_title = ch.get("title", f"第{ch_idx}章")
            ch_purpose = ch.get("purpose", "展開")
            ch_design = chapter_designs[ch_idx - 1] if ch_idx <= len(chapter_designs) else {}

            # Determine number of scenes for this chapter (2-4)
            ch_scene_count = self._estimate_scene_count(ch_purpose)

            for sc_idx in range(ch_scene_count):
                scene_number = scene_counter
                total_scenes = len(all_scenes) + ch_scene_count  # Estimate

                user = self._prompts.render(
                    "scene_outline.md",
                    {
                        "series_plan": series_plan,
                        "volume_number": str(vol_num),
                        "volume_title": "",
                        "volume_premise": "",
                        "chapter_number": str(ch_idx),
                        "chapter_title": ch_title,
                        "chapter_purpose": ch_purpose,
                        "chapter_theme": ch_design.get("theme", ""),
                        "chapter_emotional_arc": ch_design.get("emotional_arc", ""),
                        "chapter_foreshadowing_notes": ch_design.get("foreshadowing_notes", ""),
                        "chapter_subplot_notes": ch_design.get("subplot_notes", ""),
                        "scene_number": str(scene_number),
                        "scene_count": str(total_scenes),
                        "chapter_scene_number": str(sc_idx + 1),
                        "chapter_scene_count": str(ch_scene_count),
                        "previous_outcome": previous_outcome,
                        "previous_volume_summary": prev_summary,
                        "lang": self._lang,
                    },
                )
                scene_schema = get_schema("scene_outline")
                scene_result = self._llm.complete_json("scene_outline", system, user, scene_schema)

                scene_result["chapter_number"] = ch_idx
                scene_result["number"] = scene_number
                all_scenes.append(scene_result)

                previous_outcome = scene_result.get("outcome", "")
                scene_counter += 1

        # Build final result with scenes nested under chapters
        chapters_with_scenes = []
        for i, ch in enumerate(chapters_list):
            ch_scenes = [s for s in all_scenes if s.get("chapter_number") == i + 1]
            chapters_with_scenes.append({
                "number": i + 1,
                "title": ch.get("title", ""),
                "purpose": ch.get("purpose", ""),
                "scenes": ch_scenes,
            })

        result = {
            "title": chapters_result.get("title", f"第{vol_num}巻") if isinstance(chapters_result, dict) else f"第{vol_num}巻",
            "premise": chapters_result.get("premise", "") if isinstance(chapters_result, dict) else "",
            "chapters": chapters_with_scenes,
            "scenes": all_scenes,
        }
        return self._flatten_outline(result)

    def _estimate_scene_count(self, purpose: str) -> int:
        """Estimate number of scenes per chapter based on its role."""
        if purpose == "導入":
            return 2
        elif purpose == "クライマックス":
            return 4
        elif purpose == "収束":
            return 2
        else:  # 展開, 転換
            return 3

    def _flatten_outline(self, result):
        flat_chapters = []
        flat_scenes = []
        scene_counter = 1
        for ch_idx, ch in enumerate(result.get("chapters", []), 1):
            ch["number"] = ch_idx
            flat_chapters.append(ch)
            for sc in ch.get("scenes", []):
                sc["number"] = scene_counter
                sc["chapter_number"] = ch_idx
                flat_scenes.append(sc)
                scene_counter += 1
        result["chapters"] = flat_chapters
        result["scenes"] = flat_scenes
        return result

    def _review_outline(self, outline, series_plan, previous_outline=""):
        system = self._prompts.render("system.md", {"lang": self._lang})
        lines = [f"シリーズ企画: {series_plan}", ""]
        if previous_outline:
            lines.append(previous_outline)
            lines.append("")
        lines.extend([f"巻タイトル: {outline.get('title', '未設定')}", f"前提: {outline.get('premise', '未設定')}", ""])
        for ch in outline.get("chapters", []):
            lines.append(f"第{ch['number']}章: {ch['title']}（{ch.get('purpose', '')}）")
            for sc in outline.get("scenes", []):
                if sc.get("chapter_number") == ch["number"]:
                    lines.append(f"  シーン{sc['number']}: {sc['title']}")
                    lines.append(f"    目標: {sc.get('goal', '')[:100]}")
                    lines.append(f"    結果: {sc.get('outcome', '')[:100]}")
        outline_text = "\n".join(lines)
        user = self._prompts.render("volume_outline_review.md", {"outline": outline_text, "lang": self._lang})
        schema = get_schema("volume_outline_review")
        return self._llm.complete_json("volume_outline_review", system, user, schema)

    def _revise_outline(self, outline, review, series_plan, genre, vol_num, system, schema, previous_outline=""):
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            sug = issue.get("suggestion", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
            if sug:
                lines.append(f"    提案: {sug}")
        review_text = "\n".join(lines)

        outline_lines = [f"巻タイトル: {outline.get('title', '')}", f"前提: {outline.get('premise', '')}", ""]
        for ch in outline.get("chapters", []):
            outline_lines.append(f"第{ch['number']}章: {ch['title']}（{ch.get('purpose', '')}）")
            for sc in outline.get("scenes", []):
                if sc.get("chapter_number") == ch["number"]:
                    outline_lines.append(f"  シーン{sc['number']}: {sc['title']}")
        outline_text = "\n".join(outline_lines)

        user = self._prompts.render(
            "volume_outline_revision.md",
            {"current_outline": outline_text, "review": review_text, "series_plan": series_plan,
             "lang": self._lang, "previous_outline": previous_outline},
        )
        result = self._llm.complete_json("volume_outline_revision", system, user, schema)
        return self._flatten_outline(result)
