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
            elif isinstance(val, dict):
                # world のようなネストオブジェクトの内部チェック
                for sub_field in val.get("_check_required", []):
                    sub_val = val.get(sub_field)
                    if sub_val is None or (isinstance(sub_val, str) and not sub_val.strip()) or (isinstance(sub_val, list) and len(sub_val) == 0):
                        errors.append(f"{field}.{sub_field}")
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
        """LLM呼び出し → バリデーション → 失敗時リトライ。

        Args:
            generate_fn: LLMを呼んでdictを返す関数
            validate_fn: バリデーション関数。問題フィールド名のリストを返す（空なら合格）
            system: システムプロンプト
            user_prompt: 初回のユーザープロンプト
            kind: LLM呼び出しの種別（ログ用）
            max_retries: 最大試行回数

        Returns:
            バリデーション合格のdict

        Raises:
            RuntimeError: max_retries回すべて失敗した場合
        """
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
        # Remove phase-internal fields that don't belong in the merged plan
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
        # Clear _series_dir cache before setting slug so final dir is computed fresh
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
        # 各phase別ファイル + 統合ファイルを保存
        self._save_path(0, "series_core.json", core)
        self._save_path(0, "series_characters.json", characters)
        self._save_path(0, "series_volumes.json", volumes)
        self._save_path(0, "series_plan.json", result)
        self._save()
        self._log.info(f"Plan finished: title='{result.get('title', '?')}' slug='{self._slug}'")
        return result

    # ── Phase 1: Core ────────────────────────────────────────────────────

    def _generate_plan_core(self, keywords: str, system: str) -> dict:
        user_prompt = self._prompts.render("series_plan_core.md", {"keywords": keywords, "lang": self._lang})
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
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            lines.append(f"  [{issue.get('severity', '')}] {issue.get('category', '')}: {issue.get('description', '')}")
        for s in review.get("suggestions", []):
            lines.append(f"  推奨: {s}")
        review_text = "\n".join(lines)
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
        # レビュー結果を保存（全履歴）
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
        result = self._fix_character_duplicates(result)
        return result

    @staticmethod
    def _fix_character_duplicates(characters: dict) -> dict:
        """Detect and fix duplicate characters, role conflicts, and empty growth fields.

        This is a fail-safe for when the LLM ignores prompt-level duplicate prevention.
        """
        chars = characters.get("main_characters", [])
        if not chars:
            return characters

        # 1. Detect duplicate names
        seen_names: dict[str, int] = {}
        for i, c in enumerate(chars):
            name = c.get("name", "")
            if name in seen_names:
                # Duplicate found — rename with suffix
                new_name = f"{name}（{seen_names[name] + 1}）"
                c["name"] = new_name
                seen_names[name] += 1
                # Also change role to avoid role conflict
                existing_roles = {ch.get("role", "") for j, ch in enumerate(chars) if j != i}
                for alt_role in ["ヒロイン", "相棒", "師匠", "仲間", "敵対者"]:
                    if alt_role not in existing_roles:
                        c["role"] = alt_role
                        break
            else:
                seen_names[name] = 1

        # 2. Fix empty growth fields
        for c in chars:
            if not c.get("growth") or not c.get("growth", "").strip():
                arc = c.get("arc", "") or "物語を通じた成長"
                role = c.get("role", "")
                c["growth"] = f"{arc}を経て、最終的に自己の課題を克服し、新たな境地へ到達する"

        # 3. Ensure role uniqueness (first occurrence wins)
        used_roles: set[str] = set()
        available_roles = ["主人公", "ヒロイン", "相棒", "敵対者", "師匠", "仲間"]
        for c in chars:
            role = c.get("role", "")
            if role in used_roles:
                for alt in available_roles:
                    if alt not in used_roles:
                        c["role"] = alt
                        used_roles.add(alt)
                        break
            else:
                used_roles.add(role)

        characters["main_characters"] = chars
        return characters

    def _review_plan_characters(self, characters: dict, core: dict, system: str, seed_offset: int = 0) -> dict:
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
        # レビュー結果を保存（全履歴）
        self._save_path(0, "series_characters_review.json", {"reviews": all_reviews})
        return characters

    # ── Phase 3: Volumes ─────────────────────────────────────────────────

    def _generate_plan_volumes(self, core: dict, characters: dict, system: str) -> dict:
        core_text = f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n世界観: {core.get('world', {}).get('summary', '')}"
        char_lines = ["メインキャラクター:"]
        for c in characters.get("main_characters", []):
            char_lines.append("  - {}（{}）: {}".format(c.get('name', ''), c.get('role', ''), c.get('arc', '')))
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
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            lines.append(f"  [{issue.get('severity', '')}] {issue.get('category', '')}: {issue.get('description', '')}")
        for s in review.get("suggestions", []):
            lines.append(f"  推奨: {s}")
        review_text = "\n".join(lines)
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
        # レビュー結果を保存（全履歴）
        self._save_path(0, "series_volumes_review.json", {"reviews": all_reviews})
        return volumes

    # ── Utility ──────────────────────────────────────────────────────────

    @staticmethod
    def _slugify(title: str) -> str:
        romaji_parts = re.findall(r'[a-zA-Z][a-zA-Z0-9]*', title)
        if romaji_parts:
            slug = "-".join(p.lower() for p in romaji_parts)
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            if slug:
                return slug[:200]
        h = hashlib.md5(title.encode()).hexdigest()[:12]
        return f"series-{h}"
