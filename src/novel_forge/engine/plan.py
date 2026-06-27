"""Series plan generation — 3-phase: core → characters → volumes."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from novel_forge.bible_manager import BibleManager
from novel_forge.engine.review import format_review_text
from novel_forge.name_registry import load_used_names, record_names
from novel_forge.schemas import get_schema
from novel_forge.storage import BibleStorage, BlackboardStorage

if TYPE_CHECKING:
    from novel_forge.engine.base import NovelEngineBase
else:
    NovelEngineBase = object


class PlanMixin(NovelEngineBase):  # type: ignore[misc]
    """Series plan generation methods for NovelEngine."""

    # ── Orchestrator ──────────────────────────────────────────────────

    def plan(self, keywords: str) -> dict:
        """Generate a complete series plan (core → characters → volumes)."""
        system = self._prompts.render("system.md", {"lang": self._lang})

        # Phase 1: Core (title, logline, world)
        self._log.info(f"▶ Plan: keywords='{keywords}'")
        existing_slugs = self._get_existing_slugs()
        core, core_review = self._generate_plan_core(keywords, system, existing_slugs)
        title = core.get("title", "")
        slug = core.get("slug", "")
        if not slug:
            slug = self._slugify(title)
        slug = slug[:32]
        self._slug = slug

        # Phase 2: Characters
        used_names = load_used_names(self._workdir)
        characters, chars_review = self._generate_plan_characters(core, system, used_names)

        # Phase 3: Volumes
        volumes, vols_review = self._generate_plan_volumes(core, characters, system)

        # Add number to each volume
        planned_volumes = []
        for i, v in enumerate(volumes.get("planned_volumes", []), 1):
            planned_volumes.append({**v, "number": i})

        # Save reviews
        self._move_to_final_dir()
        self._save_path(0, "series_core_review.json", {"issues": core_review.get("issues", [])})
        self._save_path(0, "series_characters_review.json", {"issues": chars_review.get("issues", [])})
        self._save_path(0, "series_volumes_review.json", {"issues": vols_review.get("issues", [])})

        # Assemble and save
        result = {
            "title": title,
            "slug": slug,
            **characters,
            "main_characters": characters.get("main_characters", []),
            "planned_volumes": planned_volumes,
        }

        # Save to series_dir/series_plan.json
        self._save_path(0, "series_plan.json", result)
        self._state.status = "企画済"
        self._save()
        self._log.info(f"✓ Plan complete: title='{title}' slug='{slug}'")

        # Record character names for future dedup
        new_names = {c.get("name", "") for c in characters.get("main_characters", []) if c.get("name")}
        if new_names:
            record_names(self._workdir, new_names)

        return result

    # ── Validation helpers ─────────────────────────────────────────────

    def _validate_plan_core(self, core: dict) -> list[str]:
        required = ["title", "logline", "genre", "world"]
        errors = []
        for field in required:
            val = core.get(field)
            if (
                val is None
                or (isinstance(val, str) and not val.strip())
                or (isinstance(val, list) and len(val) == 0)
            ):
                errors.append(field)
        if isinstance(core.get("world"), dict):
            if not core["world"].get("summary"):
                errors.append("world.summary")
        else:
            errors.append("world")
        return errors

    def _validate_plan_characters(self, characters: dict) -> list[str]:
        required = ["main_characters"]
        errors = []
        for field in required:
            val = characters.get(field)
            if (
                val is None
                or (isinstance(val, str) and not val.strip())
                or (isinstance(val, list) and len(val) == 0)
            ):
                errors.append(field)
        if not errors:
            for i, c in enumerate(characters["main_characters"]):
                if not c.get("name"):
                    errors.append(f"main_characters[{i}].name")
                if not c.get("role"):
                    errors.append(f"main_characters[{i}].role")
        return errors

    def _validate_plan_volumes(self, volumes: dict) -> list[str]:
        required = ["planned_volumes"]
        errors = []
        for field in required:
            val = volumes.get(field)
            if (
                val is None
                or (isinstance(val, str) and not val.strip())
                or (isinstance(val, list) and len(val) == 0)
            ):
                errors.append(field)
        if not errors:
            for i, v in enumerate(volumes["planned_volumes"]):
                if not v.get("title"):
                    errors.append(f"planned_volumes[{i}].title")
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

    # ── Phase 1: Core ──────────────────────────────────────────────────

    def _generate_plan_core(self, keywords: str, system: str, existing_slugs: set[str]) -> tuple[dict, dict]:
        hint = ""
        if existing_slugs:
            hint = f"\n\n## 注意: 以下のslugは既存シリーズで使用済み: {', '.join(sorted(existing_slugs))}\n重複しないslugを生成すること。"
        prompt = (
            self._prompts.render("series_plan_core.md", {"keywords": keywords, "lang": self._lang})
            + hint
        )
        return self._generate_and_review(
            generate_fn=lambda p, s: self._llm.complete_json(
                "series_plan_core", system, p, get_schema("series_plan_core"), seed_offset=s
            ),
            validate_fn=self._validate_plan_core,
            review_fn=self._review_plan_core,
            revise_fn=self._revise_plan_core,
            system=system,
            user_prompt=prompt,
            kind="series_plan_core",
        )

    def _review_plan_core(self, core: dict, system: str) -> dict:
        text = (
            f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n"
            f"ジャンル: {', '.join(core.get('genre', []))}\nターゲット読者: {core.get('target_audience', '')}\n"
            f"テーマ: {', '.join(core.get('themes', []))}\n売りポイント: {'; '.join(core.get('selling_points', []))}\n"
            f"世界観: {core.get('world', {}).get('summary', '')}\n"
            f"世界観ルール: {'; '.join(core.get('world', {}).get('rules', []))}"
        )
        user = self._prompts.render(
            "series_plan_core_review.md", {"plan_text": text, "lang": self._lang}
        )
        return self._llm.complete_json(
            "series_plan_core_review", system, user, get_schema("series_plan_core_review")
        )

    def _revise_plan_core(
        self, core: dict, review: dict, system: str, seed_offset: int = 0
    ) -> dict:
        review_text = format_review_text(review)
        prompt = self._prompts.render(
            "series_plan_core_revision.md",
            {"current_plan": json.dumps(core, ensure_ascii=False), "review": review_text},
        )
        return self._llm.complete_json(
            "series_plan_core", system, prompt, get_schema("series_plan_core")
        )

    # ── Phase 2: Characters ──────────────────────────────────────────────

    def _generate_plan_characters(self, core: dict, system: str, used_names: set[str]) -> tuple[dict, dict]:
        existing_hint = ""
        if used_names:
            existing_hint = f"\n\n## 注意: 以下の名前は既存シリーズで使用済みのため使用不可: {', '.join(sorted(used_names))}\n新しいキャラクターには、これらの名前と重複しない名前を割り当てること。"
        prompt = (
            self._prompts.render(
                "series_plan_characters.md",
                {
                    "world_summary": core.get("world", {}).get("summary", ""),
                    "world_rules": "; ".join(core.get("world", {}).get("rules", [])),
                    "lang": self._lang,
                },
            )
            + existing_hint
        )
        return self._generate_and_review(
            generate_fn=lambda p, s: self._llm.complete_json(
                "series_plan_characters",
                system,
                p,
                get_schema("series_plan_characters"),
                seed_offset=s,
            ),
            validate_fn=self._validate_plan_characters,
            review_fn=lambda r, sys: self._review_plan_characters(r, core, sys),
            revise_fn=lambda r, rv, sys, so=0: self._revise_plan_characters(r, rv, sys, so),
            system=system,
            user_prompt=prompt,
            kind="series_plan_characters",
        )

    def _review_plan_characters(self, characters: dict, core: dict, system: str) -> dict:
        lines = ["世界観:", core.get("world", {}).get("summary", ""), "", "メインキャラクター:"]
        for c in characters.get("main_characters", []):
            lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_characters_review.md", {"characters": text, "lang": self._lang}
        )
        return self._llm.complete_json(
            "series_plan_characters_review",
            system,
            user,
            get_schema("series_plan_characters_review"),
        )

    def _revise_plan_characters(
        self, characters: dict, review: dict, system: str, seed_offset: int = 0
    ) -> dict:
        review_text = format_review_text(review)
        prompt = self._prompts.render(
            "series_plan_characters_revision.md",
            {
                "current_characters": json.dumps(characters, ensure_ascii=False),
                "review": review_text,
            },
        )
        return self._llm.complete_json(
            "series_plan_characters", system, prompt, get_schema("series_plan_characters")
        )

    # ── Phase 3: Volumes ─────────────────────────────────────────────────

    def _generate_plan_volumes(self, core: dict, characters: dict, system: str) -> tuple[dict, dict]:
        char_lines = ["メインキャラクター:"]
        for c in characters.get("main_characters", []):
            char_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        prompt = self._prompts.render(
            "series_plan_volumes.md",
            {
                "core_text": f"タイトル: {core.get('title', '')}\nあらすじ: {core.get('logline', '')}\n世界観: {core.get('world', {}).get('summary', '')}",
                "characters_text": "\n".join(char_lines),
                "lang": self._lang,
            },
        )
        return self._generate_and_review(
            generate_fn=lambda p, s: self._llm.complete_json(
                "series_plan_volumes", system, p, get_schema("series_plan_volumes"), seed_offset=s
            ),
            validate_fn=self._validate_plan_volumes,
            review_fn=lambda r, sys: self._review_plan_volumes(r, core, characters, sys),
            revise_fn=lambda r, rv, sys, so=0: self._revise_plan_volumes(r, rv, sys, so),
            system=system,
            user_prompt=prompt,
            kind="series_plan_volumes",
        )

    def _review_plan_volumes(
        self, volumes: dict, core: dict, characters: dict, system: str
    ) -> dict:
        lines = [
            f"シリーズ核:\n  タイトル: {core.get('title', '')}\n  あらすじ: {core.get('logline', '')}",
            "",
            "各巻:",
        ]
        for v in volumes.get("planned_volumes", []):
            lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
        text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_volumes_review.md", {"volumes": text, "lang": self._lang}
        )
        return self._llm.complete_json(
            "series_plan_volumes_review", system, user, get_schema("series_plan_volumes_review")
        )

    def _revise_plan_volumes(
        self, volumes: dict, review: dict, system: str, seed_offset: int = 0
    ) -> dict:
        review_text = format_review_text(review)
        prompt = self._prompts.render(
            "series_plan_volumes_revision.md",
            {"current_volumes": json.dumps(volumes, ensure_ascii=False), "review": review_text},
        )
        return self._llm.complete_json(
            "series_plan_volumes", system, prompt, get_schema("series_plan_volumes")
        )

    # ── Utility ──────────────────────────────────────────────────────────

    @staticmethod
    def _slugify(title: str) -> str:
        """フォールバック用slug生成。英数字がなければハッシュを使用。"""
        romaji_parts = re.findall(r"[a-zA-Z][a-zA-Z0-9]*", title)
        if romaji_parts:
            slug = "_".join(p.lower() for p in romaji_parts)
            slug = re.sub(r"[^a-z0-9_]", "", slug)
            if slug:
                return slug[:32]
        h = hashlib.md5(title.encode()).hexdigest()[:12]
        return f"series_{h}"
