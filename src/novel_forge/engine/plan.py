"""Series plan generation — 3-phase: core → characters → volumes, each with review/revise loop."""

from __future__ import annotations

import json
from typing import Any

from novel_forge.bible_manager import BibleManager
from novel_forge.schemas import get_schema
from novel_forge.storage import BibleStorage, BlackboardStorage


class PlanMixin:
    """Series plan generation methods for NovelEngine."""

    def plan(self, keywords: str) -> dict[str, Any]:
        """3-phase series plan: core → characters → volumes, each with review/revise."""
        self._ensure_config()
        system = self._prompts.render("system.md", {"lang": self._lang})

        # Phase 1: Core (title, logline, genre, themes, world)
        core = self._generate_plan_core(keywords, system)
        core = self._review_and_revise_plan_core(core, system)

        # Phase 2: Characters (based on core world/setting)
        characters = self._generate_plan_characters(core, system)
        characters = self._review_and_revise_plan_characters(characters, core, system)

        # Phase 3: Volumes (based on core + characters)
        volumes = self._generate_plan_volumes(core, characters, system)
        volumes = self._review_and_revise_plan_volumes(volumes, core, characters, system)

        # Merge all phases into final series_plan
        result = {**core, **characters, **volumes}

        # Slug fallback
        if not result.get("slug"):
            result["slug"] = self._slugify(result.get("title", ""))
        if result.get("slug") and len(result["slug"]) > 200:
            result["slug"] = result["slug"][:200].rstrip("-")

        # Auto-number volumes
        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i

        self._state.series_title = result.get("title", "")
        self._state.status = "計画中"
        self._slug = result.get("slug", "")
        self._move_to_final_dir()
        self._scene_writer._series_dir = self._series_dir
        self._ctx_builder._workdir = self._series_dir
        self._bb_storage = BlackboardStorage(self._series_dir)
        self._bible_storage = BibleStorage(self._series_dir)
        self._bible_mgr = BibleManager(self._bible_storage)
        self._scene_writer._bb_storage = self._bb_storage
        self._scene_writer._bible_storage = self._bible_storage
        self._scene_writer._bible_mgr = self._bible_mgr
        # 各phase別ファイル + 統合ファイルを保存
        self._save_path(0, "series_core.json", core)
        self._save_path(0, "series_characters.json", characters)
        self._save_path(0, "series_volumes.json", volumes)
        self._save_path(0, "series_plan.json", result)
        self._save()
        return result

    # ── Phase 1: Core ────────────────────────────────────────────────────

    def _generate_plan_core(self, keywords: str, system: str) -> dict:
        user = self._prompts.render("series_plan_core.md", {"keywords": keywords, "lang": self._lang})
        return self._llm.complete_json("series_plan_core", system, user, get_schema("series_plan_core"))

    def _review_plan_core(self, core: dict, system: str) -> dict:
        plan_text = (
            f"タイトル: {core.get('title', '')}\n"
            f"あらすじ: {core.get('logline', '')}\n"
            f"ジャンル: {', '.join(core.get('genre', []))}\n"
            f"ターゲット読者: {core.get('target_audience', '')}\n"
            f"テーマ: {', '.join(core.get('themes', []))}\n"
            f"売りポイント: {'; '.join(core.get('selling_points', []))}\n"
            f"世界観: {core.get('world', {}).get('summary', '')}\n"
            f"世界観ルール: {'; '.join(core.get('world', {}).get('rules', []))}"
        )
        user = self._prompts.render("series_plan_core_review.md", {"plan_text": plan_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_core_review", system, user, get_schema("series_plan_core_review"))

    def _revise_plan_core(self, core: dict, review: dict, system: str) -> dict:
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            lines.append(f"  [{issue.get('severity', '')}] {issue.get('category', '')}: {issue.get('description', '')}")
        for s in review.get("suggestions", []):
            lines.append(f"  推奨: {s}")
        review_text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_core_revision.md",
            {"current_plan": json.dumps(core, ensure_ascii=False), "review": review_text, "lang": self._lang},
        )
        return self._llm.complete_json("series_plan_core_revision", system, user, get_schema("series_plan_core"))

    def _review_and_revise_plan_core(self, core: dict, system: str) -> dict:
        review = self._review_plan_core(core, system)
        all_reviews = [{"version": 0, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])}]
        for retry in range(3):
            blocker_issues = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
            major_issues = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
            revision_needed = len(blocker_issues) > 0 or len(critical_issues) > 0 or len(major_issues) >= 2
            if not revision_needed:
                break
            self._log.warning(
                "  [CORE REVIEW] blocker=%d critical=%d major=%d retry=%d/3",
                len(blocker_issues), len(critical_issues), len(major_issues), retry + 1,
            )
            core = self._revise_plan_core(core, review, system)
            # 修正版を版番号付きで保存
            self._save_path(0, "series_core.json", core, version=retry + 1)
            review = self._review_plan_core(core, system)
            all_reviews.append({"version": retry + 1, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
        # レビュー結果を保存（全履歴）
        review_dir = self._series_dir / "review"
        self._save_review(review_dir, "series_core_review", {"reviews": all_reviews})
        return core

    # ── Phase 2: Characters ──────────────────────────────────────────────

    def _generate_plan_characters(self, core: dict, system: str) -> dict:
        world_text = core.get("world", {}).get("summary", "")
        rules_text = "; ".join(core.get("world", {}).get("rules", []))
        user = self._prompts.render(
            "series_plan_characters.md",
            {"world_summary": world_text, "world_rules": rules_text, "lang": self._lang},
        )
        return self._llm.complete_json("series_plan_characters", system, user, get_schema("series_plan_characters"))

    def _review_plan_characters(self, characters: dict, core: dict, system: str) -> dict:
        lines = ["世界観:", core.get("world", {}).get("summary", ""), "", "メインキャラクター:"]
        for c in characters.get("main_characters", []):
            lines.append("  - {}（{}）: {}".format(c.get('name', ''), c.get('role', ''), c.get('arc', '')))
        char_text = "\n".join(lines)
        user = self._prompts.render("series_plan_characters_review.md", {"characters": char_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_characters_review", system, user, get_schema("series_plan_characters_review"))

    def _revise_plan_characters(self, characters: dict, review: dict, system: str) -> dict:
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            lines.append(f"  [{issue.get('severity', '')}] {issue.get('category', '')}: {issue.get('description', '')}")
        for s in review.get("suggestions", []):
            lines.append(f"  推奨: {s}")
        review_text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_characters_revision.md",
            {"current_characters": json.dumps(characters, ensure_ascii=False), "review": review_text, "lang": self._lang},
        )
        return self._llm.complete_json("series_plan_characters_revision", system, user, get_schema("series_plan_characters"))

    def _review_and_revise_plan_characters(self, characters: dict, core: dict, system: str) -> dict:
        review = self._review_plan_characters(characters, core, system)
        all_reviews = [{"version": 0, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])}]
        for retry in range(3):
            blocker_issues = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
            major_issues = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
            revision_needed = len(blocker_issues) > 0 or len(critical_issues) > 0 or len(major_issues) >= 2
            if not revision_needed:
                break
            self._log.warning(
                "  [CHAR REVIEW] blocker=%d critical=%d major=%d retry=%d/3",
                len(blocker_issues), len(critical_issues), len(major_issues), retry + 1,
            )
            characters = self._revise_plan_characters(characters, review, system)
            # 修正版を版番号付きで保存
            self._save_path(0, "series_characters.json", characters, version=retry + 1)
            review = self._review_plan_characters(characters, core, system)
            all_reviews.append({"version": retry + 1, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
        # レビュー結果を保存（全履歴）
        review_dir = self._series_dir / "review"
        self._save_review(review_dir, "series_characters_review", {"reviews": all_reviews})
        return characters

    # ── Phase 3: Volumes ─────────────────────────────────────────────────

    def _generate_plan_volumes(self, core: dict, characters: dict, system: str) -> dict:
        core_text = f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n世界観: {core.get('world', {}).get('summary', '')}"
        char_lines = ["メインキャラクター:"]
        for c in characters.get("main_characters", []):
            char_lines.append("  - {}（{}）: {}".format(c.get('name', ''), c.get('role', ''), c.get('arc', '')))
        char_text = "\n".join(char_lines)
        user = self._prompts.render(
            "series_plan_volumes.md",
            {"core_text": core_text, "characters_text": char_text, "lang": self._lang},
        )
        return self._llm.complete_json("series_plan_volumes", system, user, get_schema("series_plan_volumes"))

    def _review_plan_volumes(self, volumes: dict, core: dict, characters: dict, system: str) -> dict:
        lines = ["シリーズ核:", f"  タイトル: {core.get('title', '')}", f"  あらすじ: {core.get('logline', '')}", "", "各巻:"]
        for v in volumes.get("planned_volumes", []):
            lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
        vol_text = "\n".join(lines)
        user = self._prompts.render("series_plan_volumes_review.md", {"volumes": vol_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_volumes_review", system, user, get_schema("series_plan_volumes_review"))

    def _revise_plan_volumes(self, volumes: dict, review: dict, system: str) -> dict:
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            lines.append(f"  [{issue.get('severity', '')}] {issue.get('category', '')}: {issue.get('description', '')}")
        for s in review.get("suggestions", []):
            lines.append(f"  推奨: {s}")
        review_text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_volumes_revision.md",
            {"current_volumes": json.dumps(volumes, ensure_ascii=False), "review": review_text, "lang": self._lang},
        )
        return self._llm.complete_json("series_plan_volumes_revision", system, user, get_schema("series_plan_volumes"))

    def _review_and_revise_plan_volumes(self, volumes: dict, core: dict, characters: dict, system: str) -> dict:
        review = self._review_plan_volumes(volumes, core, characters, system)
        all_reviews = [{"version": 0, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])}]
        for retry in range(3):
            blocker_issues = [i for i in review.get("issues", []) if i.get("severity") == "致命的"]
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "重大"]
            major_issues = [i for i in review.get("issues", []) if i.get("severity") == "重要"]
            revision_needed = len(blocker_issues) > 0 or len(critical_issues) > 0 or len(major_issues) >= 2
            if not revision_needed:
                break
            self._log.warning(
                "  [VOL REVIEW] blocker=%d critical=%d major=%d retry=%d/3",
                len(blocker_issues), len(critical_issues), len(major_issues), retry + 1,
            )
            volumes = self._revise_plan_volumes(volumes, review, system)
            # 修正版を版番号付きで保存
            self._save_path(0, "series_volumes.json", volumes, version=retry + 1)
            review = self._review_plan_volumes(volumes, core, characters, system)
            all_reviews.append({"version": retry + 1, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
        # レビュー結果を保存（全履歴）
        review_dir = self._series_dir / "review"
        self._save_review(review_dir, "series_volumes_review", {"reviews": all_reviews})
        return volumes

    # ── Utility ──────────────────────────────────────────────────────────

    @staticmethod
    def _slugify(title: str) -> str:
        import re
        romaji_parts = re.findall(r'[a-zA-Z][a-zA-Z0-9]*', title)
        if romaji_parts:
            slug = "-".join(p.lower() for p in romaji_parts)
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            if slug:
                return slug[:200]
        import hashlib
        h = hashlib.md5(title.encode()).hexdigest()[:12]
        return f"series-{h}"
