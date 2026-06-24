"""Series plan generation — 3-phase: core → characters → volumes."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, Callable

from novel_forge.bible_manager import BibleManager
from novel_forge.name_registry import load_used_names, record_names
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
        errors = []
        for field in required_fields:
            val = data.get(field)
            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
                errors.append(field)
        return errors

    def _get_existing_slugs(self) -> set[str]:
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
                    data = json.loads(plan_path.read_text(encoding="utf-8"))
                    slug = data.get("slug", "")
                    if slug:
                        existing.add(slug)
                except Exception:
                    pass
        return existing

    def _generate_and_review(
        self,
        generate_fn: Callable,
        validate_fn: Callable[[dict], list[str]],
        review_fn: Callable,
        revise_fn: Callable,
        system: str,
        user_prompt: str,
        kind: str,
        on_revise: Callable | None = None,
        existing_slugs: set[str] | None = None,
    ) -> dict:
        """generation → validation → review → revise ループ。"""
        max_retries = self._quality.max_retries
        seed_offset = 0
        result = None

        while seed_offset < max_retries:
            result = generate_fn(user_prompt, seed_offset)
            seed_offset += 1

            errors = validate_fn(result)
            if errors:
                self._log.warning("  [VALIDATION FAIL] %s: %s attempt=%d/%d", kind, errors, seed_offset, max_retries)
                continue

            review = review_fn(result, system)
            blocker = [i for i in review.get("issues", []) if i.get("severity") == self._BLOCKER]
            critical = [i for i in review.get("issues", []) if i.get("severity") == self._CRITICAL]
            major = [i for i in review.get("issues", []) if i.get("severity") == self._MAJOR]
            revision_needed = len(blocker) > 0 or len(critical) > 0 or len(major) >= 2

            if not revision_needed:
                return result

            if seed_offset >= max_retries:
                self._log.warning("  [REVIEW] %s: revision needed but max retries reached (%d/%d)", kind, seed_offset, max_retries)
                return result

            result = revise_fn(result, review, system, seed_offset)
            seed_offset += 1

            if on_revise:
                on_revise(result, seed_offset)

            errors = validate_fn(result)
            if errors:
                self._log.warning("  [POST-REVISION VALIDATION] %s: %s attempt=%d/%d", kind, errors, seed_offset, max_retries)
                continue

            review = review_fn(result, system)
            blocker = [i for i in review.get("issues", []) if i.get("severity") == self._BLOCKER]
            critical = [i for i in review.get("issues", []) if i.get("severity") == self._CRITICAL]
            major = [i for i in review.get("issues", []) if i.get("severity") == self._MAJOR]
            if len(blocker) == 0 and len(critical) == 0 and len(major) < 2:
                return result

        return result

    def _validate_plan_core(self, data: dict) -> list[str]:
        errors = self._validate_required(data, [
            "title", "slug", "logline", "genre", "themes",
            "selling_points", "target_audience",
        ], "plan_core")
        slug = data.get("slug", "")
        if slug and slug.strip():
            if len(slug) > 32:
                errors.append("slug: 32文字以内である必要があります")
            if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', slug):
                errors.append("slug: 英数字とハイフンのみ")
            if slug in self._get_existing_slugs():
                errors.append(f"slug: '{slug}' は既存と重複")
        world = data.get("world", {})
        if not world.get("summary", "").strip():
            errors.append("world.summary")
        if not world.get("rules") or len(world.get("rules", [])) == 0:
            errors.append("world.rules")
        return errors

    def _validate_plan_characters(self, data: dict) -> list[str]:
        errors = self._validate_required(data, ["main_characters"], "plan_characters")
        if errors:
            return errors

        # Name dedup: within same series + across existing series
        existing_names = load_used_names(self._workdir)
        seen = set()
        for ch in data.get("main_characters", []):
            name = ch.get("name", "")
            if not name:
                errors.append("character: name is required")
                continue
            if name in seen:
                errors.append(f"character: duplicate name '{name}' in this series")
            elif name in existing_names:
                errors.append(f"character: '{name}' is already used in another series")
            seen.add(name)
        return errors

    def _validate_plan_volumes(self, data: dict) -> list[str]:
        return self._validate_required(data, ["planned_volumes"], "plan_volumes")

    # ── Main pipeline ──────────────────────────────────────────────────

    def plan(self, keywords: str) -> dict[str, Any]:
        slug = getattr(self, "_slug", "")
        self._log.info(f"▶ Plan: keywords='{keywords}'")
        system = self._prompts.render("system.md", {"lang": self._lang})

        # Lock check
        if self._slug and (self._workdir / self._slug).exists():
            raise FileNotFoundError(f"Series '{slug}' already exists in {self._workdir}")

        existing_slugs = self._get_existing_slugs()
        used_names = load_used_names(self._workdir)

        # Phase 1: Core
        self._log.info("  ▶ core — [1/3]")
        core = self._generate_plan_core(keywords, system, existing_slugs)
        self._log.info(f"  ✓ core — title='{core.get('title', '?')}' slug='{core.get('slug', '?')}'")

        self._log.info("  ▶ characters — [2/3]")
        characters = self._generate_plan_characters(core, system, used_names)
        self._log.info(f"  ✓ characters — {len(characters.get('main_characters', []))} chars")

        self._log.info("  ▶ volumes — [3/3]")
        volumes = self._generate_plan_volumes(core, characters, system)
        self._log.info(f"  ✓ volumes — {len(volumes.get('planned_volumes', []))} vols")

        # Save results
        self._save_path(0, "series_core.json", core)
        self._save_path(0, "series_characters.json", characters)
        self._save_path(0, "series_volumes.json", volumes)
        self._save_path(0, "series_core_review.json", {"reviews": [{"version": 0, "issues": self._review_plan_core(core, system).get("issues", [])}]})
        self._save_path(0, "series_characters_review.json", {"reviews": [{"version": 0, "issues": self._review_plan_characters(characters, core, system).get("issues", [])}]})
        self._save_path(0, "series_volumes_review.json", {"reviews": [{"version": 0, "issues": self._review_plan_volumes(volumes, core, characters, system).get("issues", [])}]})

        # Merge
        result = {k: v for k, v in {**core, **characters, **volumes}.items() if k != "changes"}
        if not result.get("slug"):
            result["slug"] = self._slugify(result.get("title", ""))

        # Record new character names
        new_names = {c.get("name", "") for c in characters.get("main_characters", []) if c.get("name")}
        if new_names:
            record_names(self._workdir, new_names)

        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i

        # Update state
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
        self._save_path(0, "series_plan.json", result)
        self._save()
        self._log.info(f"✓ Plan complete: title='{result.get('title', '?')}' slug='{self._slug}'")
        return result

    # ── Phase 1: Core ────────────────────────────────────────────────────

    def _generate_plan_core(self, keywords: str, system: str, existing_slugs: set[str]) -> dict:
        hint = ""
        if existing_slugs:
            hint = f"\n\n## 注意: 以下のslugは既存シリーズで使用済み: {', '.join(sorted(existing_slugs))}\n重複しないslugを生成すること。"
        prompt = self._prompts.render("series_plan_core.md", {"keywords": keywords, "lang": self._lang}) + hint
        return self._generate_and_review(
            generate_fn=lambda p, s: self._llm.complete_json("series_plan_core", system, p, get_schema("series_plan_core"), seed_offset=s),
            validate_fn=self._validate_plan_core,
            review_fn=self._review_plan_core,
            revise_fn=self._revise_plan_core,
            system=system, user_prompt=prompt, kind="series_plan_core", existing_slugs=existing_slugs,
        )

    def _review_plan_core(self, core: dict, system: str) -> dict:
        text = (f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n"
                f"ジャンル: {', '.join(core.get('genre', []))}\nターゲット読者: {core.get('target_audience', '')}\n"
                f"テーマ: {', '.join(core.get('themes', []))}\n売りポイント: {'; '.join(core.get('selling_points', []))}\n"
                f"世界観: {core.get('world', {}).get('summary', '')}\n"
                f"世界観ルール: {'; '.join(core.get('world', {}).get('rules', []))}")
        user = self._prompts.render("series_plan_core_review.md", {"plan_text": text, "lang": self._lang})
        return self._llm.complete_json("series_plan_core_review", system, user, get_schema("series_plan_core_review"))

    def _revise_plan_core(self, core: dict, review: dict, system: str, seed_offset: int = 0) -> dict:
        review_text = self._format_review_text(review)
        prompt = self._prompts.render("series_plan_core_revision.md",
                                      {"current_plan": json.dumps(core, ensure_ascii=False), "review": review_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_core_revision", system, prompt, get_schema("series_plan_core_revision"))

    # ── Phase 2: Characters ──────────────────────────────────────────────

    def _generate_plan_characters(self, core: dict, system: str, used_names: set[str]) -> dict:
        existing_hint = ""
        if used_names:
            existing_hint = f"\n\n## 注意: 以下の名前は既存シリーズで使用済みのため使用不可: {', '.join(sorted(used_names))}\n新しいキャラクターには、これらの名前と重複しない名前を割り当てること。"
        prompt = self._prompts.render("series_plan_characters.md",
                                      {"world_summary": core.get("world", {}).get("summary", ""),
                                       "world_rules": "; ".join(core.get("world", {}).get("rules", [])),
                                       "lang": self._lang}) + existing_hint
        return self._generate_and_review(
            generate_fn=lambda p, s: self._llm.complete_json("series_plan_characters", system, p, get_schema("series_plan_characters"), seed_offset=s),
            validate_fn=self._validate_plan_characters,
            review_fn=lambda r, sys: self._review_plan_characters(r, core, sys),
            revise_fn=lambda r, rv, sys, so=0: self._revise_plan_characters(r, rv, sys, so),
            system=system, user_prompt=prompt, kind="series_plan_characters",
        )

    def _review_plan_characters(self, characters: dict, core: dict, system: str) -> dict:
        lines = ["世界観:", core.get("world", {}).get("summary", ""), "", "メインキャラクター:"]
        for c in characters.get("main_characters", []):
            lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        text = "\n".join(lines)
        user = self._prompts.render("series_plan_characters_review.md", {"characters": text, "lang": self._lang})
        return self._llm.complete_json("series_plan_characters_review", system, user, get_schema("series_plan_characters_review"))

    def _revise_plan_characters(self, characters: dict, review: dict, system: str, seed_offset: int = 0) -> dict:
        review_text = self._format_review_text(review)
        prompt = self._prompts.render("series_plan_characters_revision.md",
                                      {"current_characters": json.dumps(characters, ensure_ascii=False),
                                       "review": review_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_characters_revision", system, prompt, get_schema("series_plan_characters_revision"))

    # ── Phase 3: Volumes ─────────────────────────────────────────────────

    def _generate_plan_volumes(self, core: dict, characters: dict, system: str) -> dict:
        char_lines = ["メインキャラクター:"]
        for c in characters.get("main_characters", []):
            char_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        prompt = self._prompts.render("series_plan_volumes.md",
                                      {"core_text": f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n世界観: {core.get('world', {}).get('summary', '')}",
                                       "characters_text": "\n".join(char_lines), "lang": self._lang})
        return self._generate_and_review(
            generate_fn=lambda p, s: self._llm.complete_json("series_plan_volumes", system, p, get_schema("series_plan_volumes"), seed_offset=s),
            validate_fn=self._validate_plan_volumes,
            review_fn=lambda r, sys: self._review_plan_volumes(r, core, characters, sys),
            revise_fn=lambda r, rv, sys, so=0: self._revise_plan_volumes(r, rv, sys, so),
            system=system, user_prompt=prompt, kind="series_plan_volumes",
        )

    def _review_plan_volumes(self, volumes: dict, core: dict, characters: dict, system: str) -> dict:
        lines = [f"シリーズ核:\n  タイトル: {core.get('title', '')}\n  あらすじ: {core.get('logline', '')}", "", "各巻:"]
        for v in volumes.get("planned_volumes", []):
            lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
        text = "\n".join(lines)
        user = self._prompts.render("series_plan_volumes_review.md", {"volumes": text, "lang": self._lang})
        return self._llm.complete_json("series_plan_volumes_review", system, user, get_schema("series_plan_volumes_review"))

    def _revise_plan_volumes(self, volumes: dict, review: dict, system: str, seed_offset: int = 0) -> dict:
        review_text = self._format_review_text(review)
        prompt = self._prompts.render("series_plan_volumes_revision.md",
                                      {"current_volumes": json.dumps(volumes, ensure_ascii=False),
                                       "review": review_text, "lang": self._lang})
        return self._llm.complete_json("series_plan_volumes_revision", system, prompt, get_schema("series_plan_volumes_revision"))

    # ── Utility ──────────────────────────────────────────────────────────

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
