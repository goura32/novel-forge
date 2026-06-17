"""Series plan generation — plan, _generate_plan, _revise_plan, _review_series_plan."""

from __future__ import annotations

from typing import Any

from novel_forge.schemas import get_schema


class PlanMixin:
    """Series plan generation methods for NovelEngine."""

    def plan(self, keywords: str) -> dict[str, Any]:
        # Auto-generate config.yaml if missing
        self._ensure_config()
        system = self._prompts.render("system.md", {"lang": self._lang})
        schema = get_schema("series_plan")

        result = self._generate_plan(keywords, system, schema)
        review = self._review_series_plan(result)

        # Review → Revise loop (max 3 retries)
        for retry in range(3):
            score = review.get("score", 0)
            critical_issues = [i for i in review.get("issues", []) if i.get("severity") == "critical"]
            if score >= 70 and len(critical_issues) == 0:
                break
            print(f"  [REVIEW] score={score}, critical={len(critical_issues)}, retry={retry+1}/3", flush=True)
            result = self._revise_plan(result, review, system, schema)
            review = self._review_series_plan(result)

        self._state.series_title = result.get("title", "")
        self._state.status = "計画中"
        self._save_path(0, "series_plan.json", result)
        self._save_path(0, "series_plan_review.json", review)
        self._save()
        return result

    def _generate_plan(self, keywords: str, system: str, schema: dict) -> dict:
        user = self._prompts.render(
            "series_plan.md",
            {"keywords": keywords, "lang": self._lang},
        )
        result = self._llm.complete_json("series_plan", system, user, schema)
        if result.get("slug") and len(result["slug"]) > 256:
            result["slug"] = result["slug"][:256].rstrip("-")
        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i
        return result

    def _revise_plan(self, plan: dict, review: dict, system: str, schema: dict) -> dict:
        """Revise series plan based on review issues."""
        # Build review text (no JSON keys)
        lines = ["レビュー結果:"]
        for issue in review.get("issues", []):
            sev = issue.get("severity", "")
            cat = issue.get("category", "")
            desc = issue.get("description", "")
            sug = issue.get("suggestion", "")
            lines.append(f"  [{sev}] {cat}: {desc}")
            if sug:
                lines.append(f"    提案: {sug}")
        for s in review.get("strengths", []):
            lines.append(f"  強み: {s}")
        for r in review.get("recommendations", []):
            lines.append(f"  推奨: {r}")
        review_text = "\n".join(lines)

        # Build current plan text
        plan_lines = [
            f"タイトル: {plan.get('title', '')}",
            f"あらすじ: {plan.get('logline', '')}",
            f"ジャンル: {plan.get('genre', '')}",
            f"ターゲット読者: {plan.get('target_audience', '')}",
            f"テーマ: {', '.join(plan.get('themes', []))}",
            f"売りポイント: {'; '.join(plan.get('selling_points', []))}",
            f"世界観: {plan.get('world', {}).get('summary', '')}",
            f"世界観ルール: {'; '.join(plan.get('world', {}).get('rules', []))}",
            "メインキャラクター:",
        ]
        for c in plan.get("main_characters", []):
            plan_lines.append(f"  - {c.get('name', '')}（{c.get('role', '')}）: {c.get('arc', '')}")
        plan_lines.append("各巻:")
        for v in plan.get("planned_volumes", []):
            plan_lines.append(f"  - {v.get('title', '')}: {v.get('premise', '')}")
        plan_text = "\n".join(plan_lines)

        user = self._prompts.render(
            "series_plan_revision.md",
            {
                "current_plan": plan_text,
                "review": review_text,
                "lang": self._lang,
            },
        )
        result = self._llm.complete_json("series_plan_revision", system, user, schema)
        if result.get("slug") and len(result["slug"]) > 256:
            result["slug"] = result["slug"][:256].rstrip("-")
        for i, vol in enumerate(result.get("planned_volumes", []), 1):
            vol["number"] = i
        return result

    def _review_series_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        system = self._prompts.render("system.md", {"lang": self._lang})
        filtered = {
            "title": plan.get("title", ""),
            "logline": plan.get("logline", ""),
            "genre": plan.get("genre", ""),
            "target_audience": plan.get("target_audience", ""),
            "themes": plan.get("themes", []),
            "selling_points": plan.get("selling_points", []),
            "world_summary": plan.get("world", {}).get("summary", ""),
            "world_rules": plan.get("world", {}).get("rules", []),
            "main_characters": [
                {"name": c.get("name", ""), "arc": c.get("arc", "")}
                for c in plan.get("main_characters", [])
            ],
            "planned_volumes": [
                {"title": v.get("title", ""), "premise": v.get("premise", "")}
                for v in plan.get("planned_volumes", [])
            ],
        }
        lines = [
            f"タイトル: {filtered['title']}",
            f"あらすじ: {filtered['logline']}",
            f"ジャンル: {filtered['genre']}",
            f"ターゲット読者: {filtered['target_audience']}",
            f"テーマ: {', '.join(filtered['themes'])}",
            f"売りポイント: {'; '.join(filtered['selling_points'])}",
            f"世界観: {filtered['world_summary']}",
            f"世界観ルール: {'; '.join(filtered['world_rules'])}",
            "メインキャラクター:",
        ]
        for c in filtered["main_characters"]:
            lines.append(f"  - {c['name']}: {c['arc']}")
        lines.append("各巻:")
        for v in filtered["planned_volumes"]:
            lines.append(f"  - {v['title']}: {v['premise']}")
        plan_text = "\n".join(lines)
        user = self._prompts.render(
            "series_plan_review.md",
            {"plan": plan_text, "lang": self._lang},
        )
        return self._llm.complete_json("series_plan_review", system, user, get_schema("series_plan_review"))
