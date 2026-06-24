"""Series plan generation — 3-phase: core → characters → volumes, each with review/revise loop."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Callable

from novel_forge.bible_manager import BibleManager
from novel_forge.schemas import get_schema
from novel_forge.storage import BibleStorage, BlackboardStorage

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase
else:
    NovelEngineBase = object


class PlanMixin(NovelEngineBase):  # type: ignore[misc]
    """Series plan generation methods for NovelEngine."""

    # ── Validation helpers ─────────────────────────────────────────────

    @staticmethod
    def _validate_required(data: dict, required_fields: list[str], label: str) -> list[str]:
        """必須フィールドの空チェック。問題のあるフィールド名のリストを返す。"""
        errors = []
        for field in required_fields:
            val = data.get(field)
            if val is None:
                errors.append(field)
            elif isinstance(val, str) and not val.strip():
                errors.append(field)
            elif isinstance(val, list) and len(val) == 0:
                errors.append(field)
        return errors

    def _validate_and_retry(
        self,
        generate_fn: Callable,
        validate_fn: Callable[[dict], list[str]],
        system: str,
        user_prompt: str,
        kind: str,
        max_retries: int = 3,
    ) -> dict:
        """LLM呼び出し → バリデーション → 失敗時リトライ。"""
        current_prompt = user_prompt
        for attempt in range(max_retries):
            result = generate_fn(current_prompt)
            errors = validate_fn(result)
            if not errors:
                return result
            self._log.warning(
                "  [VALIDATION RETRY] %s: 問題フィールド=%s attempt=%d/%d",
                kind, errors, attempt + 1, max_retries,
            )
            current_prompt = (
                f"前回の出力に問題がありました。以下のフィールドが空または不正です: {errors}\n"
                f"これらのフィールドを必ず正しい値で埋めてください。\n\n"
                f"元の指示:\n{user_prompt}"
            )
        raise RuntimeError(
            f"{kind} のバリデーションに失敗しました。{max_retries}回試行しましたが合格しませんでした。"
        )

    def _get_existing_slugs(self) -> set[str]:
        """workdir に存在する既存シリーズの slug を取得する"""
        existing = set()
        workdir = self._workdir
        if not workdir.exists():
            return existing
        for d in workdir.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue
            plan_path = d / "series_plan.json"
            if plan_path.exists():
                try:
                    import json as _json
                    data = _json.loads(plan_path.read_text(encoding="utf-8"))
                    slug = data.get("slug", "")
                    if slug:
                        existing.add(slug)
                except Exception:
                    pass
        return existing

    def _validate_plan_core(self, data: dict) -> list[str]:
        """series_plan_core のバリデーション。"""
        errors = self._validate_required(data, [
            "title", "slug", "logline", "genre", "themes",
            "selling_points", "target_audience",
        ], "plan_core")
        # slug の詳細チェック
        slug = data.get("slug", "")
        if slug and slug.strip():
            if len(slug) > 32:
                errors.append("slug: 32文字以内である必要があります")
            if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', slug):
                errors.append("slug: 英数字とハイフンのみ。ハイフンで始終不可、連続ハイフン不可")
            # 既存slugとの重複チェック
            if slug in self._get_existing_slugs():
                errors.append(f"slug: '{slug}' は既存シリーズと重複します。別のslugを生成してください")
        # world の内部チェック
        world = data.get("world", {})
        if not world.get("summary", "").strip():
            errors.append("world.summary")
        if not world.get("rules") or len(world.get("rules", [])) == 0:
            errors.append("world.rules")
        return errors

    def _validate_plan_characters(self, data: dict) -> list[str]:
        """series_plan_characters のバリデーション。"""
        return self._validate_required(data, ["main_characters"], "plan_characters")

    def _validate_plan_volumes(self, data: dict) -> list[str]:
        """series_plan_volumes のバリデーション。"""
        return self._validate_required(data, ["planned_volumes"], "plan_volumes")

    # ── Main pipeline ──────────────────────────────────────────────────

    def plan(self, keywords: str) -> dict[str, Any]:
        """3-phase series plan: core → characters → volumes, each with review/revise."""
        slug = getattr(self, "_slug", "?")
        self._log.info(f"Plan started: keywords='{keywords}' slug='{slug}'")
        system = self._prompts.render("system.md", {"lang": self._lang})

        # Check if series directory already exists
        if self._slug:
            series_dir = self._workdir / self._slug
            if series_dir.exists():
                raise FileNotFoundError(
                    f"Series directory '{series_dir}' already exists. "
                    f"Use a different slug or remove the existing directory."
                )

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
        core_clean = {k: v for k, v in core.items() if k != "changes"}
        characters_clean = {k: v for k, v in characters.items() if k != "changes"}
        volumes_clean = {k: v for k, v in volumes.items() if k != "changes"}
        result = {**core_clean, **characters_clean, **volumes_clean}

        # Slug fallback (should not happen due to validation, but just in case)
        if not result.get("slug"):
            result["slug"] = self._slugify(result.get("title", ""))
        if result.get("slug") and len(result["slug"]) > 200:
            result["slug"] = result["slug"][:200].rstrip("-")

        # Auto-number volumes
        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i

        self._state.series_title = result.get("title", "")
        self._state.status = "計画中"
        if hasattr(self, "_cached_series_dir"):
            del self._cached_series_dir
        self._slug = result.get("slug", "")
        self._move_to_final_dir()
        self._scene_writer._series_dir = self._series_dir
        self._ctx_builder._series_dir = self._series_dir
        self._bb_storage = BlackboardStorage(self._series_dir)
        self._bible_storage = BibleStorage(self._series_dir)
        self._bible_mgr = BibleManager(self._bible_storage)
        self._scene_writer._bb_storage = self._bb_storage
        self._scene_writer._bible_storage = self._bible_storage
        self._scene_writer._bible_mgr = self._bible_mgr
        self._save_path(0, "series_core.json", core)
        self._save_path(0, "series_characters.json", characters)
        self._save_path(0, "series_volumes.json", volumes)
        self._save_path(0, "series_plan.json", result)
        self._save()
        self._log.info(f"Plan finished: title='{result.get('title', '?')}' slug='{self._slug}'")
        return result

    # ── Phase 1: Core ────────────────────────────────────────────────────

    def _generate_plan_core(self, keywords: str, system: str) -> dict:
        # 既存slugをプロンプトに渡して重複回避
        existing_slugs = sorted(self._get_existing_slugs())
        existing_hint = ""
        if existing_slugs:
            existing_hint = f"\n\n## 注意: 以下のslugは既存シリーズで使用されているため使用不可: {', '.join(existing_slugs)}\nこれらと重複しない新しいslugを生成すること。"
        user_prompt = self._prompts.render("series_plan_core.md", {"keywords": keywords, "lang": self._lang}) + existing_hint
        return self._validate_and_retry(
            generate_fn=lambda prompt: self._llm.complete_json("series_plan_core", system, prompt, get_schema("series_plan_core")),
            validate_fn=self._validate_plan_core,
            system=system,
            user_prompt=user_prompt,
            kind="series_plan_core",
        )

    def _review_plan_core(self, core: dict, system: str, seed_offset: int = 0) -> dict:
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
        review_text = self._format_review_text(review)
        user_prompt = self._prompts.render(
            "series_plan_core_revision.md",
            {"current_plan": json.dumps(core, ensure_ascii=False), "review": review_text, "lang": self._lang},
        )
        return self._validate_and_retry(
            generate_fn=lambda prompt: self._llm.complete_json("series_plan_core_revision", system, prompt, get_schema("series_plan_core_revision")),
            validate_fn=self._validate_plan_core,
            system=system,
            user_prompt=user_prompt,
            kind="series_plan_core_revision",
        )

    def _review_and_revise_plan_core(self, core: dict, system: str) -> dict:
        all_reviews = []
        def _on_revise(revised, version):
            self._save_path(0, "series_core.json", revised, version=version)
            all_reviews.append({"version": version, "issues": self._review_plan_core(revised, system).get("issues", []), "suggestions": self._review_plan_core(revised, system).get("suggestions", [])})
        core = self._review_and_revise(
            item=core,
            review_fn=self._review_plan_core,
            revise_fn=self._revise_plan_core,
            system=system,
            label="CORE REVIEW",
            on_revise=_on_revise,
        )
        self._save_path(0, "series_core_review.json", {"reviews": all_reviews})
        return core

    # ── Phase 2: Characters ──────────────────────────────────────────────

    def _generate_plan_characters(self, core: dict, system: str) -> dict:
        world_text = core.get("world", {}).get("summary", "")
        rules_text = "; ".join(core.get("world", {}).get("rules", []))
        user_prompt = self._prompts.render(
            "series_plan_characters.md",
            {"world_summary": world_text, "world_rules": rules_text, "lang": self._lang},
        )
        result = self._validate_and_retry(
            generate_fn=lambda prompt: self._llm.complete_json("series_plan_characters", system, prompt, get_schema("series_plan_characters")),
            validate_fn=self._validate_plan_characters,
            system=system,
            user_prompt=user_prompt,
            kind="series_plan_characters",
        )
        return result

    def _review_plan_characters(self, characters: dict, core: dict, system: str, seed_offset: int = 0) -> dict:
        lines = ["世界観:", core.get("world", {}).get("summary", ""), "", "メインキャラクター:"]
        for c in characters.get("main_characters", []):
            lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        char_text = "\n".join(lines)
        user = self._prompts.render("series_plan_characters_review.md", {"characters": char_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_characters_review", system, user, get_schema("series_plan_characters_review"))

    def _revise_plan_characters(self, characters: dict, review: dict, system: str) -> dict:
        review_text = self._format_review_text(review)
        user_prompt = self._prompts.render(
            "series_plan_characters_revision.md",
            {"current_characters": json.dumps(characters, ensure_ascii=False), "review": review_text, "lang": self._lang},
        )
        return self._validate_and_retry(
            generate_fn=lambda prompt: self._llm.complete_json("series_plan_characters_revision", system, prompt, get_schema("series_plan_characters_revision")),
            validate_fn=self._validate_plan_characters,
            system=system,
            user_prompt=user_prompt,
            kind="series_plan_characters_revision",
        )

    def _review_and_revise_plan_characters(self, characters: dict, core: dict, system: str) -> dict:
        all_reviews = []
        def _on_revise(revised, version):
            self._save_path(0, "series_characters.json", revised, version=version)
            review = self._review_plan_characters(revised, core, system)
            all_reviews.append({"version": version, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
        characters = self._review_and_revise(
            item=characters,
            review_fn=lambda item, sys, seed_offset=0: self._review_plan_characters(item, core, sys),
            revise_fn=self._revise_plan_characters,
            system=system,
            label="CHAR REVIEW",
            on_revise=_on_revise,
        )
        self._save_path(0, "series_characters_review.json", {"reviews": all_reviews})
        return characters

    # ── Phase 3: Volumes ─────────────────────────────────────────────────

    def _generate_plan_volumes(self, core: dict, characters: dict, system: str) -> dict:
        core_text = f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n世界観: {core.get('world', {}).get('summary', '')}"
        char_lines = ["メインキャラクター:"]
        for c in characters.get("main_characters", []):
            char_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        char_text = "\n".join(char_lines)
        user_prompt = self._prompts.render(
            "series_plan_volumes.md",
            {"core_text": core_text, "characters_text": char_text, "lang": self._lang},
        )
        return self._validate_and_retry(
            generate_fn=lambda prompt: self._llm.complete_json("series_plan_volumes", system, prompt, get_schema("series_plan_volumes")),
            validate_fn=self._validate_plan_volumes,
            system=system,
            user_prompt=user_prompt,
            kind="series_plan_volumes",
        )

    def _review_plan_volumes(self, volumes: dict, core: dict, characters: dict, system: str, seed_offset: int = 0) -> dict:
        lines = ["シリーズ核:", f"  タイトル: {core.get('title', '')}", f"  あらすじ: {core.get('logline', '')}", "", "各巻:"]
        for v in volumes.get("planned_volumes", []):
            lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
        vol_text = "\n".join(lines)
        user = self._prompts.render("series_plan_volumes_review.md", {"volumes": vol_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_volumes_review", system, user, get_schema("series_plan_volumes_review"))

    def _revise_plan_volumes(self, volumes: dict, review: dict, system: str) -> dict:
        review_text = self._format_review_text(review)
        user_prompt = self._prompts.render(
            "series_plan_volumes_revision.md",
            {"current_volumes": json.dumps(volumes, ensure_ascii=False), "review": review_text, "lang": self._lang},
        )
        return self._validate_and_retry(
            generate_fn=lambda prompt: self._llm.complete_json("series_plan_volumes_revision", system, prompt, get_schema("series_plan_volumes_revision")),
            validate_fn=self._validate_plan_volumes,
            system=system,
            user_prompt=user_prompt,
            kind="series_plan_volumes_revision",
        )

    def _review_and_revise_plan_volumes(self, volumes: dict, core: dict, characters: dict, system: str) -> dict:
        all_reviews = []
        def _on_revise(revised, version):
            self._save_path(0, "series_volumes.json", revised, version=version)
            review = self._review_plan_volumes(revised, core, characters, system)
            all_reviews.append({"version": version, "issues": review.get("issues", []), "suggestions": review.get("suggestions", [])})
        volumes = self._review_and_revise(
            item=volumes,
            review_fn=lambda item, sys, seed_offset=0: self._review_plan_volumes(item, core, characters, sys),
            revise_fn=self._revise_plan_volumes,
            system=system,
            label="VOL REVIEW",
            on_revise=_on_revise,
        )
        self._save_path(0, "series_volumes_review.json", {"reviews": all_reviews})
        return volumes

    # ── Utility ──────────────────────────────────────────────────────────

    @staticmethod
    def _format_review_text(review: dict) -> str:
        """Format review result into text for revision prompt."""
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

    @staticmethod
    def _slugify(title: str) -> str:
        """Convert title to URL-safe slug."""
        romaji_parts = re.findall(r'[a-zA-Z][a-zA-Z0-9]*', title)
        if romaji_parts:
            slug = "-".join(p.lower() for p in romaji_parts)
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            if slug:
                return slug[:200]
        h = hashlib.md5(title.encode()).hexdigest()[:12]
        return f"series-{h}"
