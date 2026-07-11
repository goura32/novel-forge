"""The sole source of truth for LLM task, prompt, and schema ownership."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    prompt: str
    schema: str


_TASK_ROWS = (
    ("plan.concept", "plan_concept"),
    ("plan.characters", "plan_characters"),
    ("plan.volumes", "plan_volumes"),
    ("design.volume", "design_volume"),
    ("design.chapter", "design_chapter"),
    ("design.scene", "design_scene"),
    ("write.draft", "write_draft"),
)
# write.draft uses the v2 continuity-handoff prompt files; review uses review_issues.
_PROMPT_OVERRIDES = {
    "write.draft.generate": "scene_draft_v2.md",
    "write.draft.review": "scene_review_v2.md",
    "write.draft.revise": "scene_revision_v2.md",
}
_OPERATIONS = ("generate", "review", "revise")


def _build_tasks() -> dict[str, TaskSpec]:
    tasks: dict[str, TaskSpec] = {}
    for stem, resource_stem in _TASK_ROWS:
        for operation in _OPERATIONS:
            task_id = f"{stem}.{operation}"
            prompt = _PROMPT_OVERRIDES.get(task_id, f"{resource_stem}_{operation}.md")
            tasks[task_id] = TaskSpec(
                task_id=task_id,
                prompt=prompt,
                schema="review_issues" if operation == "review" else resource_stem,
            )
    return tasks


TASKS = _build_tasks()


class TaskRegistry:
    """Resolve task metadata without inferring schemas from resource filenames."""

    def get(self, task_id: str) -> TaskSpec:
        try:
            return TASKS[task_id]
        except KeyError as exc:
            raise KeyError(f"Unknown task ID: {task_id}") from exc

    def all(self) -> tuple[TaskSpec, ...]:
        return tuple(TASKS.values())

    def load_schema(self, task_id: str) -> dict:
        """Return the resolved JSON schema dict for a task (raises if missing)."""
        spec = self.get(task_id)
        schema_path = resources.files("novel_forge") / "resources" / "schemas" / f"{spec.schema}.json"
        try:
            raw = schema_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as exc:
            raise KeyError(f"schema resource not found for {task_id}: {spec.schema}.json") from exc
        import json as _json
        data: dict[str, Any] = _json.loads(raw)
        return data

    def validate_resources(self) -> list[str]:
        prompt_dir = resources.files("novel_forge") / "resources" / "prompts"
        schema_dir = resources.files("novel_forge") / "resources" / "schemas"
        errors: list[str] = []
        for spec in self.all():
            if not (prompt_dir / spec.prompt).is_file():
                errors.append(f"missing prompt for {spec.task_id}: {spec.prompt}")
            if not (schema_dir / f"{spec.schema}.json").is_file():
                errors.append(f"missing schema for {spec.task_id}: {spec.schema}.json")
        return errors


DEFAULT_TASK_REGISTRY = TaskRegistry()
