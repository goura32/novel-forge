"""Volume design generation — outline, orchestrate_design, _review_design, _revise_design."""

from __future__ import annotations

import json
from typing import Any

from novel_forge.models import VolumeOutline
from novel_forge.schemas import get_schema


class DesignMixin:
    """Volume design generation methods for NovelEngine."""

    def design(self, volume_number: int | None = None) -> dict[str, Any]:
        vol_num = volume_number or self._state.current_volume
        self._state.current_volume = vol_num
        system = self._prompts.render("system.md", {"lang": self._lang})
        series_plan = self._ctx_builder.get_series_plan_summary()
        genre = self._ctx_builder.get_genre()
        schema = get_schema("volume_design")
        previous_design = self._get_previous_volume_design(vol_num)

        result = self.orchestrate_design(series_plan, genre, vol_num, system, schema, previous_design)
        review = self._review_design(result, series_plan, previous_design)
        review = self._recalc_review_score(review)

        # Review → Revise loop (max 3 retries)
        for retry in range(3):
            score = review.get("score", 0)
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
            if score >= 70 and len(critical_issues) == 0:
                break
            import sys as _sys
            _sys.stderr.write(f"  [DESIGN REVIEW] score={score}, critical={len(critical_issues)}, retry={retry+1}/3\n")
            result = self._revise_design(result, review, series_plan, genre, vol_num, system, schema, previous_design)
            review = self._review_design(result, series_plan, previous_design)
            review = self._recalc_review_score(review)

        vol = self._current_volume()
        vol.status = "デザイン済"
        self._state.status = "デザイン済"
        result["volume_number"] = vol_num
        self._save_path(vol_num, "design.json", result)
        self._save()
        return result

    def _get_previous_volume_design(self, vol_num: int) -> str:
        """Get the outline summary of the previous volume, if it exists."""
        if vol_num <= 1:
            return ""
        prev_path = self._series_dir / f"vol{vol_num - 1:02d}" / "design.json"
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

        return chapter_designs

    # ── Phase 3: Scene designs ───────────────────────────────────────────

    def _generate_scene_designs(self, chapters_list: list[dict], chapter_designs: list[dict],
                                  series_plan: str, vol_num: int, system: str,
                                  previous_design: str,
                                  volume_title: str = "",
                                  volume_premise: str = "") -> list[dict]:
        """Phase 3: Generate scene-by-scene outlines for each chapter."""
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
                scene_counter += 1

        return all_scenes

    # ── Main outline orchestrator ──────────────────────────────────────

    def orchestrate_design(self, series_plan, genre, vol_num, system, schema, previous_design=""):
        """Multi-phase outline generation with per-chapter and per-scene review loops."""
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
        import json
        # _series_dir is provided by NovelEngineBase (MRO)
        plan_path = self._series_dir / "series_plan.json"  # type: ignore[attr-defined]
        if plan_path.exists():
            try:
                return json.loads(plan_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    @staticmethod
    def _estimate_scene_count(purpose: str) -> int:
        """Estimate number of scenes per chapter based on its role."""
        if purpose == "導入":
            return 2
        elif purpose == "クライマックス":
            return 4
        elif purpose == "収束":
            return 2
        else:  # 展開, 転換
            return 3

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

    def _recalc_review_score(self, review: dict) -> dict:
        """Python側でレビュースコアを再計算し、LLMの計算ミスを修正する。

        ルール:
        1. 各サブスコアの平均を計算
        2. critical issue があれば score ≤ 50
        3. major issue が3つ以上あれば score ≤ 65
        4. minor only であれば score ≥ 70
        """
        subs = ["structural_validity", "scene_coherence", "pace_analysis", "character_arc_review"]
        scores = []
        for key in subs:
            sub = review.get(key, {})
            s = sub.get("score", 0)
            if isinstance(s, (int, float)) and 0 <= s <= 100:
                scores.append(int(s))
            else:
                scores.append(0)

        if scores:
            avg = round(sum(scores) / len(scores))
        else:
            avg = 0

        # 深刻度による上限/下限
        issues = review.get("issues", [])
        has_critical = any(i.get("severity") in ("critical", "blocker") for i in issues)
        major_count = sum(1 for i in issues if i.get("severity") == "major")

        if has_critical:
            avg = min(avg, 50)
        elif major_count >= 3:
            avg = min(avg, 65)
        elif not has_critical and major_count == 0:
            avg = max(avg, 70)

        review["score"] = avg

        # force_breakdown を追加（デバッグ用）
        review["_score_breakdown"] = {
            "sub_scores": {k: review.get(k, {}).get("score", 0) for k in subs},
            "average": round(sum(scores) / len(scores)) if scores else 0,
            "capped": avg,
            "has_critical": has_critical,
            "major_count": major_count,
        }
        return review

    def _review_design(self, outline, series_plan, previous_design=""):
        system = self._prompts.render("system.md", {"lang": self._lang})
        lines = [f"シリーズ企画: {series_plan}", ""]
        if previous_design:
            lines.append(previous_design)
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
        user = self._prompts.render("volume_design_review.md", {"outline": outline_text, "lang": self._lang})
        schema = get_schema("volume_design_review")
        return self._llm.complete_json("volume_design_review", system, user, schema)

    # ── Chapter design review/revise ─────────────────────────────────────

    def _review_chapter_design(self, ch_design, ch_info, series_plan, vol_num, system,
                                volume_title="", volume_premise=""):
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
        return self._llm.complete_json("chapter_design_review", system, user, get_schema("chapter_design_review"))

    def _revise_chapter_design(self, ch_design, review, system):
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
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
        """Review and revise each chapter design (max 2 retries per chapter)."""
        for i, ch_design in enumerate(chapter_designs):
            ch_info = chapters_list[i] if i < len(chapters_list) else {}
            review = self._review_chapter_design(
                ch_design, ch_info, series_plan, vol_num, system,
                volume_title=volume_title, volume_premise=volume_premise,
            )
            for retry in range(2):
                score = review.get("score", 0)
                critical = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
                if score >= 70 and len(critical) == 0:
                    break
                import sys as _sys
                _sys.stderr.write(f"  [CH REVIEW] ch={i+1} score={score} critical={len(critical)} retry={retry+1}/2\n")
                ch_design = self._revise_chapter_design(ch_design, review, system)
                review = self._review_chapter_design(
                    ch_design, ch_info, series_plan, vol_num, system,
                    volume_title=volume_title, volume_premise=volume_premise,
                )
            chapter_designs[i] = ch_design
        return chapter_designs

    # ── Scene design review/revise ───────────────────────────────────────

    def _review_scene_design(self, scene, ch_info, series_plan, vol_num, system,
                              volume_title="", volume_premise="", previous_outcome=""):
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
        return self._llm.complete_json("scene_design_review", system, user, get_schema("scene_design_review"))

    def _revise_scene_design(self, scene, review, system):
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
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
        for i, scene in enumerate(all_scenes):
            ch_idx = scene.get("chapter_number", 1) - 1
            ch_info = chapters_list[ch_idx] if ch_idx < len(chapters_list) else {}
            review = self._review_scene_design(
                scene, ch_info, series_plan, vol_num, system,
                volume_title=volume_title, volume_premise=volume_premise,
                previous_outcome=previous_outcome,
            )
            for retry in range(2):
                score = review.get("score", 0)
                critical = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
                if score >= 70 and len(critical) == 0:
                    break
                import sys as _sys
                _sys.stderr.write(f"  [SC REVIEW] sc={i+1} score={score} critical={len(critical)} retry={retry+1}/2\n")
                scene = self._revise_scene_design(scene, review, system)
                review = self._review_scene_design(
                    scene, ch_info, series_plan, vol_num, system,
                    volume_title=volume_title, volume_premise=volume_premise,
                    previous_outcome=previous_outcome,
                )
            all_scenes[i] = scene
            previous_outcome = scene.get("outcome", "")
        return all_scenes

    def _revise_design(self, outline, review, series_plan, genre, vol_num, system, schema, previous_design=""):
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
            "volume_design_revision.md",
            {"current_outline": outline_text, "review": review_text, "series_plan": series_plan,
             "lang": self._lang, "previous_design": previous_design},
        )
        try:
            result = self._llm.complete_json("volume_design_revision", system, user, schema)
        except Exception:
            # LLMがスキーマ違反の出力をした場合（title/premise欠落など）→ フォールバック
            result = {
                "title": outline.get("title") or f"第{vol_num}巻",
                "premise": outline.get("premise") or "",
                "chapters": outline.get("chapters", []),
            }

        # Fallback: If title is missing (LLM sometimes omits it), use fallback values
        if not result.get("title"):
            result["title"] = outline.get("title") or f"第{vol_num}巻"
        if not result.get("premise"):
            result["premise"] = outline.get("premise") or ""
        return self._normalize_design_numbering(result)
