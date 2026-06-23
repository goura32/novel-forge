"""Volume design generation — design, orchestrate_design, _review_design, _revise_design."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from novel_forge.models import VolumeOutline
from novel_forge.schemas import get_schema

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase
else:
    NovelEngineBase = object


class DesignMixin(NovelEngineBase):  # type: ignore[misc]
    """Volume design generation methods for NovelEngine."""

    # Scene count estimates by chapter purpose
    SCENE_COUNT_BY_PURPOSE: dict[str, int] = {
        "導入": 2,
        "展開": 3,
        "転換": 3,
        "クライマックス": 4,
        "収束": 2,
    }
    DEFAULT_SCENE_COUNT: int = 3

    @classmethod
    def _estimate_scene_count(cls, purpose: str) -> int:
        """Estimate number of scenes per chapter based on its role."""
        return cls.SCENE_COUNT_BY_PURPOSE.get(purpose, cls.DEFAULT_SCENE_COUNT)

    def _save_design_reviews(
        self, vol_num: int, ch_num: int, sc_num: int | None, reviews: list[dict]
    ) -> None:
        """Save review results to the appropriate directory.

        Args:
            vol_num: Volume number.
            ch_num: Chapter number.
            sc_num: Scene number (None for chapter-level reviews).
            reviews: List of review dicts with version/issues/suggestions.
        """
        base = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}"
        if sc_num is not None:
            base = base / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}"
        base.mkdir(parents=True, exist_ok=True)
        # base is the directory; build the review file name from vol/ch/sc parts
        review_name = f"vol{vol_num:02d}_ch{ch_num:02d}"
        if sc_num is not None:
            review_name += f"_sc{sc_num:02d}"
        review_path = base / (review_name + "_review.json")
        review_path.write_text(json.dumps({"reviews": reviews}, ensure_ascii=False, indent=2), encoding="utf-8")

    def design(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        slug = getattr(self, "_slug", "?")
        series_title = getattr(self, "_state", None)
        series_title = series_title.series_title if series_title else "?"
        self._log.info(f"Design started: series='{series_title}' volume={vol_num} slug='{slug}'")
        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._ctx_builder.get_series_plan_summary()
        genre = self._ctx_builder.get_genre()
        schema = get_schema("volume_design")
        previous_design = self._get_previous_volume_design(vol_num)

        result = self.orchestrate_design(series_plan, genre, vol_num, system, schema, previous_design)
        all_volume_reviews = []
        def _on_revise(revised, version):
            self._save_path(vol_num, f"vol{vol_num:02d}.json", revised, version=version)
            review = self._review_design(revised, series_plan, previous_design, seed_offset=version)
            all_volume_reviews.append({"version": version, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
        result = self._review_and_revise(
            item=result,
            review_fn=lambda item, sys, seed_offset=0: self._review_design(item, series_plan, previous_design, seed_offset=seed_offset),
            revise_fn=lambda item, review, sys, seed_offset=0: self._revise_design(item, review, series_plan, genre, vol_num, sys, schema, previous_design, seed_offset=seed_offset),
            system=system,
            label="DESIGN REVIEW",
            on_revise=_on_revise,
        )

        vol = self._current_volume()
        vol.status = "デザイン済"
        self._state.status = "デザイン済"
        result["volume_number"] = vol_num
        # 巻デザインを保存
        self._save_path(vol_num, f"vol{vol_num:02d}.json", result)
        # 章デザインを個別保存
        for ch in result.get("chapters", []):
            ch_num = ch.get("number", 0)
            ch_dir = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}"
            ch_dir.mkdir(parents=True, exist_ok=True)
            ch_path = ch_dir / f"vol{vol_num:02d}_ch{ch_num:02d}.json"
            ch_path.write_text(json.dumps(ch, ensure_ascii=False, indent=2), encoding="utf-8")
        # シーン設計を個別保存
        for sc in result.get("scenes", []):
            sc_num = sc.get("number", 0)
            ch_num = sc.get("chapter_number", 0)
            sc_dir = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}"
            sc_dir.mkdir(parents=True, exist_ok=True)
            sc_path = sc_dir / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}.json"
            sc_path.write_text(json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8")
        # レビュー結果を巻ディレクトリに保存（全履歴）
        vol_review_path = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_review.json"
        vol_review_path.write_text(json.dumps({"reviews": all_volume_reviews}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._save()
        self._log.info(f"Design finished: series='{series_title}' volume={vol_num} slug='{slug}'")
        return result

    def _get_previous_volume_design(self, vol_num: int) -> str:
        """Get the design summary of the previous volume, if it exists."""
        if vol_num <= 1:
            return ""
        prev_path = self._series_dir / f"vol{vol_num - 1:02d}" / f"vol{vol_num - 1:02d}.json"
        if not prev_path.exists():
            self._log.warning(
                "  前巻（第%d巻）のデザインが存在しません: %s。第%d巻のデザインを生成するには、先に前巻のデザインを生成してください。",
                vol_num - 1, prev_path, vol_num,
            )
            return ""
        try:
            data = json.loads(prev_path.read_text(encoding="utf-8"))
            lines = [f"前巻（第{vol_num - 1}巻）デザイン:",
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
                f"前巻（第{vol_num - 1}巻）のデザイン読み込みに失敗しました: {e}"
            ) from e

    # ── Phase 1: Volume design (chapter structure) ───────────────────────

    def _generate_volume_design(self, series_plan: str, genre: str, vol_num: int,
                                     system: str, previous_design: str) -> list[dict]:
        """Phase 1: Generate chapter structure (titles + purposes)."""
        chapter_schema = get_schema("volume_design")
        user = self._prompts.render(
            "volume_design.md",
            {"series_plan": series_plan, "volume_number": str(vol_num), "genre": genre,
             "lang": self._lang, "previous_design": previous_design},
        )
        chapters_result = self._llm.complete_json("volume_design", system, user, chapter_schema)

        if isinstance(chapters_result, dict):
            chapters_list = chapters_result.get("chapters", [chapters_result])
        elif isinstance(chapters_result, list):
            chapters_list = chapters_result
        else:
            raise RuntimeError(
                f"章構成の生成に失敗しました: 予期しない型 {type(chapters_result).__name__}"
            )
        return chapters_list

    # ── Phase 2: Chapter design ────────────────────────────────────────

    def _generate_chapter_designs(self, chapters_list: list[dict], series_plan: str,
                                   vol_num: int, system: str,
                                   previous_design: str,
                                   volume_title: str = "",
                                   volume_premise: str = "") -> list[dict]:
        """Phase 2: Generate detailed design for each chapter."""
        chapter_designs = []
        previous_chapter_outcome = ""
        prev_summary = previous_design[:500] if previous_design else ""

        for ch_idx, ch in enumerate(chapters_list, 1):
            ch_title = ch.get("title", f"第{ch_idx}章")
            ch_purpose = ch.get("purpose", "展開")
            self._log.info(f"  [CH DESIGN START] ch{ch_idx}/{len(chapters_list)} title='{ch_title}' purpose='{ch_purpose}'")

            user = self._prompts.render(
                "chapter_design.md",
                {
                    "series_plan": series_plan,
                    "volume_number": str(vol_num),
                    "volume_title": volume_title,
                    "volume_premise": volume_premise,
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
            self._log.info(f"  [CH DESIGN END] ch{ch_idx}/{len(chapters_list)} title='{ch_title}'")

        return chapter_designs

    # ── Phase 3: Scene designs ───────────────────────────────────────────

    def _generate_scene_designs(self, chapters_list: list[dict], chapter_designs: list[dict],
                                  series_plan: str, vol_num: int, system: str,
                                  previous_design: str,
                                  volume_title: str = "",
                                  volume_premise: str = "") -> list[dict]:
        """Phase 3: Generate scene-by-scene designs for each chapter."""
        all_scenes = []
        scene_counter = 1
        previous_outcome = ""
        prev_summary = previous_design[:500] if previous_design else ""

        for ch_idx, ch in enumerate(chapters_list, 1):
            ch_title = ch.get("title", f"第{ch_idx}章")
            ch_purpose = ch.get("purpose", "展開")
            ch_design = chapter_designs[ch_idx - 1] if ch_idx <= len(chapter_designs) else {}

            ch_scene_count = self._estimate_scene_count(ch_purpose)

            for sc_idx in range(ch_scene_count):
                self._log.info(f"  [SC DESIGN START] ch{ch_idx} sc{sc_idx + 1}/{ch_scene_count}")
                scene_number = scene_counter
                total_scenes = len(all_scenes) + ch_scene_count

                user = self._prompts.render(
                    "scene_design.md",
                    {
                        "series_plan": series_plan,
                        "volume_number": str(vol_num),
                        "volume_title": volume_title,
                        "volume_premise": volume_premise,
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
                scene_schema = get_schema("scene_design")
                scene_result = self._llm.complete_json("scene_design", system, user, scene_schema)

                scene_result["chapter_number"] = ch_idx
                scene_result["number"] = scene_number
                all_scenes.append(scene_result)

                previous_outcome = scene_result.get("outcome", "")
                self._log.info(f"  [SC DESIGN END] ch{ch_idx} sc{sc_idx + 1}/{ch_scene_count}")
                scene_counter += 1

        return all_scenes

    # ── Main design orchestrator ──────────────────────────────────────

    def orchestrate_design(self, series_plan, genre, vol_num, system, schema, previous_design=""):
        """Multi-phase design generation with per-chapter and per-scene review loops."""
        plan_data = self._get_plan_data()
        volume_title = f"第{vol_num}巻"
        volume_premise = ""
        if plan_data:
            volumes = plan_data.get("planned_volumes", [])
            if vol_num <= len(volumes):
                vol_item = volumes[vol_num - 1]
                volume_title = vol_item.get("title", volume_title) or volume_title
                volume_premise = vol_item.get("premise", "") or ""

        # Phase 1: Volume design (chapter structure)
        chapters_list = self._generate_volume_design(
            series_plan, genre, vol_num, system, previous_design
        )
        self._log.info(f"  [DESIGN PROGRESS] vol{vol_num}: {len(chapters_list)} chapters generated")

        # Phase 2: Chapter designs + review/revise loop
        chapter_designs = self._generate_chapter_designs(
            chapters_list, series_plan, vol_num, system, previous_design,
            volume_title=volume_title, volume_premise=volume_premise,
        )
        chapter_designs = self._review_and_revise_chapter_designs(
            chapter_designs, chapters_list, series_plan, vol_num, system,
            volume_title=volume_title, volume_premise=volume_premise,
        )

        # Phase 3: Scene designs + review/revise loop
        all_scenes = self._generate_scene_designs(
            chapters_list, chapter_designs, series_plan, vol_num, system, previous_design,
            volume_title=volume_title, volume_premise=volume_premise,
        )
        self._log.info(f"  [DESIGN PROGRESS] vol{vol_num}: {len(all_scenes)} scenes generated")
        all_scenes = self._review_and_revise_scene_designs(
            all_scenes, chapters_list, chapter_designs, series_plan, vol_num, system,
            volume_title=volume_title, volume_premise=volume_premise,
        )

        # Build result with scenes nested under chapters
        chapters_with_scenes = []
        for i, ch in enumerate(chapters_list):
            ch_scenes = [s for s in all_scenes if s.get("chapter_number") == i + 1]
            chapters_with_scenes.append({
                "number": i + 1,
                "title": ch.get("title", ""),
                "purpose": ch.get("purpose", ""),
                "scenes": ch_scenes,
            })

        title = volume_title
        premise = volume_premise
        if isinstance(chapters_list, dict):
            title = chapters_list.get("title", volume_title)
            premise = chapters_list.get("premise", volume_premise)

        result = {
            "title": title or f"第{vol_num}巻",
            "premise": premise or "",
            "chapters": chapters_with_scenes,
            "scenes": all_scenes,
        }
        return self._normalize_design_numbering(result)

    def _get_plan_data(self) -> dict:
        """Load series plan data from disk."""
        # _series_dir is provided by NovelEngineBase (MRO)
        plan_path = self._series_dir / "series_plan.json"  # type: ignore[attr-defined]
        if plan_path.exists():
            try:
                return json.loads(plan_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _normalize_design_numbering(self, result):
        """章・シーンに通し番号を振り、フラットな構造に正規化する。"""
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

    def _review_design(self, design_obj, series_plan, previous_design="", seed_offset: int = 0):
        system = self._prompts.render("system.md", {"lang": self._lang})
        lines = [f"シリーズ企画: {series_plan}", ""]
        if previous_design:
            lines.append(previous_design)
            lines.append("")
        lines.extend([f"巻タイトル: {design_obj.get('title', '未設定')}", f"前提: {design_obj.get('premise', '未設定')}", ""])
        for ch in design_obj.get("chapters", []):
            lines.append(f"第{ch['number']}章: {ch['title']}（{ch.get('purpose', '')}）")
            for sc in design_obj.get("scenes", []):
                if sc.get("chapter_number") == ch["number"]:
                    lines.append(f"  シーン{sc['number']}: {sc['title']}")
                    lines.append(f"    目標: {sc.get('goal', '')[:100]}")
                    lines.append(f"    結果: {sc.get('outcome', '')[:100]}")
        outline_text = "\n".join(lines)
        user = self._prompts.render("volume_design_review.md", {"design": outline_text, "lang": self._lang})
        schema = get_schema("volume_design_review")
        return self._llm.complete_json("volume_design_review", system, user, schema, seed_offset=seed_offset)

    # ── Chapter design review/revise ─────────────────────────────────────

    def _review_chapter_design(self, ch_design, ch_info, series_plan, vol_num, system,
                                volume_title="", volume_premise="", seed_offset: int = 0):
        user = self._prompts.render(
            "chapter_design_review.md",
            {
                "series_plan": series_plan,
                "volume_title": volume_title,
                "volume_premise": volume_premise,
                "chapter_number": str(ch_info.get("number", "")),
                "chapter_title": ch_info.get("title", ""),
                "chapter_purpose": ch_info.get("purpose", ""),
                "chapter_theme": ch_design.get("theme", ""),
                "chapter_emotional_arc": ch_design.get("emotional_arc", ""),
                "foreshadowing_notes": "; ".join(ch_design.get("foreshadowing_notes", [])),
                "subplot_notes": "; ".join(ch_design.get("subplot_notes", [])),
                "scene_list": "",  # filled by caller if needed
                "lang": self._lang,
            },
        )
        return self._llm.complete_json("chapter_design_review", system, user, get_schema("chapter_design_review"), seed_offset=seed_offset)

    def _revise_chapter_design(self, ch_design, review, system, seed_offset: int = 0):
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
        review_text = "\n".join(lines)
        current = (
            f"章タイトル: {ch_design.get('title', '')}\n"
            f"役割: {ch_design.get('purpose', '')}\n"
            f"テーマ: {ch_design.get('theme', '')}\n"
            f"感情の弧: {ch_design.get('emotional_arc', '')}"
        )
        user = self._prompts.render(
            "chapter_design_revision.md",
            {"current_design": current, "review": review_text, "lang": self._lang},
        )
        result = self._llm.complete_json("chapter_design_revision", system, user, get_schema("chapter_design_revision"))
        result["number"] = ch_design.get("number")
        result["title"] = result.get("title", ch_design.get("title", ""))
        return result

    def _review_and_revise_chapter_designs(self, chapter_designs, chapters_list, series_plan,
                                            vol_num, system, volume_title="", volume_premise=""):
        """Review and revise each chapter design."""
        total = len(chapter_designs)
        for i, ch_design in enumerate(chapter_designs):
            ch_info = chapters_list[i] if i < len(chapters_list) else {}
            seed_offset = 0
            self._log.info(f"  [CH DESIGN START] ch{i+1}/{total} title='{ch_info.get('title', '?')}' purpose='{ch_info.get('purpose', '?')}'")
            review = self._review_chapter_design(
                ch_design, ch_info, series_plan, vol_num, system,
                volume_title=volume_title, volume_premise=volume_premise,
            )
            ch_reviews = [{"version": 0, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])}]
            for retry in range(self._quality.max_retries):
                blocker = [i for i in review.get("issues", []) if i.get("severity") == self._BLOCKER]
                critical = [i for i in review.get("issues", []) if i.get("severity") == self._CRITICAL]
                major = [i for i in review.get("issues", []) if i.get("severity") == self._MAJOR]
                revision_needed = len(blocker) > 0 or len(critical) > 0 or len(major) >= 2
                if not revision_needed:
                    break
                _log = getattr(self, "_log", None)
                if _log is not None:
                    _log.warning(
                        "  [CH REVIEW] ch=%d blocker=%d critical=%d major=%d retry=%d/2",
                        i + 1, len(blocker), len(critical), len(major), retry + 1,
                    )
                seed_offset += 1
                ch_design = self._revise_chapter_design(ch_design, review, system, seed_offset=seed_offset)
                # 章デザインの修正版を版番号付きで保存
                ch_dir = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{i+1:02d}"
                ch_dir.mkdir(parents=True, exist_ok=True)
                ch_ver_path = ch_dir / f"vol{vol_num:02d}_ch{i+1:02d}_v{retry+1}.json"
                ch_ver_path.write_text(json.dumps(ch_design, ensure_ascii=False, indent=2), encoding="utf-8")
                # 巻デザインの chapters 部分も更新
                try:
                    vol_path = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}.json"
                    if vol_path.exists():
                        current = json.loads(vol_path.read_text(encoding="utf-8"))
                        current["chapters"] = chapter_designs
                        self._save_path(vol_num, f"vol{vol_num:02d}.json", current)
                except Exception as e:
                    self._log.debug("  [CH REVIEW] vol design update skipped: %s", e)
                review = self._review_chapter_design(
                    ch_design, ch_info, series_plan, vol_num, system,
                    volume_title=volume_title, volume_premise=volume_premise,
                )
                ch_reviews.append({"version": retry + 1, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
            chapter_designs[i] = ch_design
            self._save_design_reviews(vol_num, i + 1, None, ch_reviews)
        return chapter_designs

    # ── Scene design review/revise ───────────────────────────────────────

    def _review_scene_design(self, scene, ch_info, series_plan, vol_num, system,
                              volume_title="", volume_premise="", previous_outcome="", seed_offset: int = 0):
        user = self._prompts.render(
            "scene_design_review.md",
            {
                "series_plan": series_plan,
                "volume_title": volume_title,
                "volume_premise": volume_premise,
                "chapter_title": ch_info.get("title", ""),
                "chapter_purpose": ch_info.get("purpose", ""),
                "scene_title": scene.get("title", ""),
                "scene_goal": scene.get("goal", ""),
                "scene_outcome": scene.get("outcome", ""),
                "scene_conflict": scene.get("conflict", ""),
                "scene_pov": scene.get("pov", ""),
                "scene_characters": ", ".join(scene.get("characters", [])),
                "scene_key_events": "; ".join(scene.get("key_events", [])),
                "scene_setting": scene.get("setting", ""),
                "scene_emotional_arc": scene.get("emotional_arc", ""),
                "previous_outcome": previous_outcome,
                "lang": self._lang,
            },
        )
        return self._llm.complete_json("scene_design_review", system, user, get_schema("scene_design_review"), seed_offset=seed_offset)

    def _revise_scene_design(self, scene, review, system, seed_offset: int = 0):
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
        review_text = "\n".join(lines)
        current = (
            f"シーンタイトル: {scene.get('title', '')}\n"
            f"目標: {scene.get('goal', '')}\n"
            f"結果: {scene.get('outcome', '')}\n"
            f"葛藤: {scene.get('conflict', '')}\n"
            f"POV: {scene.get('pov', '')}"
        )
        user = self._prompts.render(
            "scene_design_revision.md",
            {"current_design": current, "review": review_text, "lang": self._lang},
        )
        result = self._llm.complete_json("scene_design_revision", system, user, get_schema("scene_design_revision"))
        result["chapter_number"] = scene.get("chapter_number")
        result["number"] = scene.get("number")
        return result

    def _review_and_revise_scene_designs(self, all_scenes, chapters_list, chapter_designs,
                                          series_plan, vol_num, system,
                                          volume_title="", volume_premise=""):
        """Review and revise each scene design (max 2 retries per scene)."""
        previous_outcome = ""
        total = len(all_scenes)
        for i, scene in enumerate(all_scenes):
            ch_idx = scene.get("chapter_number", 1) - 1
            ch_info = chapters_list[ch_idx] if ch_idx < len(chapters_list) else {}
            self._log.info(f"  [SC DESIGN START] sc{i+1}/{total} ch{scene.get('chapter_number', '?')} title='{scene.get('title', '?')}'")
            seed_offset = 0
            review = self._review_scene_design(
                scene, ch_info, series_plan, vol_num, system,
                volume_title=volume_title, volume_premise=volume_premise,
                previous_outcome=previous_outcome, seed_offset=seed_offset,
            )
            sc_reviews = [{"version": 0, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])}]
            for retry in range(self._quality.max_retries):
                blocker = [i for i in review.get("issues", []) if i.get("severity") == self._BLOCKER]
                critical = [i for i in review.get("issues", []) if i.get("severity") == self._CRITICAL]
                major = [i for i in review.get("issues", []) if i.get("severity") == self._MAJOR]
                revision_needed = len(blocker) > 0 or len(critical) > 0 or len(major) >= 2
                if not revision_needed:
                    break
                _log = getattr(self, "_log", None)
                if _log is not None:
                    _log.warning(
                        "  [SC REVIEW] sc=%d blocker=%d critical=%d major=%d retry=%d/2",
                        i + 1, len(blocker), len(critical), len(major), retry + 1,
                    )
                seed_offset += 1
                scene = self._revise_scene_design(scene, review, system, seed_offset=seed_offset)
                # シーン設計の修正版を版番号付きで保存
                sc_num = scene.get("number", i + 1)
                ch_num = scene.get("chapter_number", 0)
                sc_dir = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}" / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}"
                sc_dir.mkdir(parents=True, exist_ok=True)
                sc_ver_path = sc_dir / f"vol{vol_num:02d}_ch{ch_num:02d}_sc{sc_num:02d}_v{retry+1}.json"
                sc_ver_path.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
                # 巻デザインの scenes 部分も更新
                try:
                    vol_path = self._series_dir / f"vol{vol_num:02d}" / f"vol{vol_num:02d}.json"
                    if vol_path.exists():
                        current = json.loads(vol_path.read_text(encoding="utf-8"))
                        current["scenes"] = all_scenes
                        self._save_path(vol_num, f"vol{vol_num:02d}.json", current)
                except Exception as e:
                    self._log.debug("  [SC REVIEW] vol design update skipped: %s", e)
                review = self._review_scene_design(
                    scene, ch_info, series_plan, vol_num, system,
                    volume_title=volume_title, volume_premise=volume_premise,
                    previous_outcome=previous_outcome,
                )
                sc_reviews.append({"version": retry + 1, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
            all_scenes[i] = scene
            previous_outcome = scene.get("outcome", "")
            self._save_design_reviews(vol_num, scene.get("chapter_number", 0), scene.get("number", i + 1), sc_reviews)
        return all_scenes

    @staticmethod
    def _build_design_outline(design_obj) -> str:
        """Build a text outline from a design object for review/revise prompts."""
        lines = [f"巻タイトル: {design_obj.get('title', '')}", f"前提: {design_obj.get('premise', '')}", ""]
        for ch in design_obj.get("chapters", []):
            lines.append(f"第{ch['number']}章: {ch['title']}（{ch.get('purpose', '')}）")
            for sc in design_obj.get("scenes", []):
                if sc.get("chapter_number") == ch["number"]:
                    lines.append(f"  シーン{sc['number']}: {sc['title']}")
                    lines.append(f"    目標: {sc.get('goal', '')[:100]}")
                    lines.append(f"    結果: {sc.get('outcome', '')[:100]}")
        return "\n".join(lines)

    def _revise_design(self, design_obj, review, series_plan, genre, vol_num, system, schema, previous_design="", seed_offset: int = 0):
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
        review_text = "\n".join(lines)

        outline_text = self._build_design_outline(design_obj)

        user = self._prompts.render(
            "volume_design_revision.md",
            {"current_design": outline_text, "review": review_text, "series_plan": series_plan,
             "lang": self._lang, "previous_design": previous_design},
        )
        try:
            result = self._llm.complete_json("volume_design_revision", system, user, schema, seed_offset=seed_offset)
        except Exception as e:
            self._log.warning("  [DESIGN REVISE] LLM failed, using fallback: %s", e)
            result = {
                "title": design_obj.get("title") or f"第{vol_num}巻",
                "premise": design_obj.get("premise") or "",
                "chapters": design_obj.get("chapters", []),
            }

        # Fallback: If title is missing (LLM sometimes omits it), use fallback values
        if not result.get("title"):
            result["title"] = design_obj.get("title") or f"第{vol_num}巻"
        if not result.get("premise"):
            result["premise"] = design_obj.get("premise") or ""
        return self._normalize_design_numbering(result)
