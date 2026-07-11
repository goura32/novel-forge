"""Real LLM-backed task runner for RuntimeWorkflow.

This is the production task_runner passed to ``RuntimeWorkflow``.  It owns the
LLM interaction only; all immutable persistence, snapshot selection, retry
looping, and review/summary bookkeeping live in ``RuntimeWorkflow``.

Contract (per RUNTIME_ARTIFACT_RETENTION_REDESIGN.md):
  * The runner receives ``(task_id, values)`` from ``RuntimeWorkflow``.
  * ``values`` keys are task-specific (see ``_TASK_VARIABLES``).
  * Every value is serialized to a JSON string and injected as a ``{key}``
    placeholder into the task prompt via ``PromptManager.render_task``.
  * The simplified schema is injected automatically by ``render_task``.
  * The LLM response is validated against the task schema by ``LLMClient``.
"""

from __future__ import annotations

import json
from typing import Any

from novel_forge.llm_client import LLMClient
from novel_forge.prompts import PromptManager

# Maps each RuntimeWorkflow task_id to the prompt variable keys it expects.
# RuntimeWorkflow passes these exact keys (see workflow_runtime.py):
#   plan.series.generate    -> {keywords, existing_slugs}
#   design.volume.generate  -> {series_plan, volume_number, volume_title, genre,
#                               previous_design, canon_context}
#   write.draft.generate   -> {writer_context, previous_summary}
#   write.draft.review      -> {writer_context, draft}
#   write.draft.revise      -> {writer_context, draft, review}
#   write.summary.generate  -> {writer_context, draft, previous_summary}
#   write.summary.review     -> {draft, summary}
#   write.summary.revise     -> {draft, summary, review}
_TASK_VARIABLES: dict[str, tuple[str, ...]] = {
    "plan.series.generate": ("keywords", "existing_slugs"),
    "design.volume.generate": (
        "series_plan",
        "volume_number",
        "volume_title",
        "genre",
        "previous_design",
        "canon_context",
    ),
    "design.chapter.generate": (
        "series_plan",
        "volume_number",
        "volume_title",
        "volume_premise",
        "chapter_number",
        "chapter_title",
        "chapter_purpose",
        "previous_chapter_outcome",
        "previous_volume_summary",
        "canon_context",
    ),
    "design.scene.generate": (
        "series_plan",
        "volume_number",
        "volume_title",
        "volume_premise",
        "chapter_number",
        "chapter_title",
        "chapter_purpose",
        "chapter_theme",
        "chapter_emotional_arc",
        "chapter_foreshadowing_notes",
        "chapter_subplot_notes",
        "scene_number",
        "scene_count",
        "chapter_scene_number",
        "chapter_scene_count",
        "scene_seed",
        "previous_outcome",
        "previous_volume_summary",
        "canon_context",
    ),
    "write.draft.generate": ("writer_context", "previous_summary"),
    "write.draft.review": ("writer_context", "draft"),
    "write.draft.revise": ("writer_context", "draft", "review"),
    "write.summary.generate": ("writer_context", "draft", "previous_summary"),
    "write.summary.review": ("draft", "summary"),
    "write.summary.revise": ("draft", "summary", "review"),
}


def make_task_runner(client: LLMClient, manager: PromptManager | None = None) -> Any:
    """Build a ``TaskRunner`` callable bound to ``client``.

    The returned callable matches ``workflow_runtime.TaskRunner``::

        def task_runner(task_id: str, values: dict[str, Any]) -> dict[str, Any]: ...
    """

    pm = manager or PromptManager()
    from novel_forge.task_registry import DEFAULT_TASK_REGISTRY

    def task_runner(task_id: str, values: dict[str, Any]) -> dict[str, Any]:
        expected = _TASK_VARIABLES.get(task_id)
        if expected is None:
            raise ValueError(f"task_runner received unknown task_id: {task_id}")
        missing = [k for k in expected if k not in values]
        if missing:
            raise ValueError(f"task_runner missing variables for {task_id}: {missing}")
        variables = {key: json.dumps(values[key], ensure_ascii=False) for key in expected}
        user_prompt = pm.render_task(task_id, variables)
        operation = task_id.rsplit(".", 1)[-1]
        schema = DEFAULT_TASK_REGISTRY.load_schema(task_id)
        return client.complete_json(
            kind=operation,
            system_prompt="あなたは小説執筆支援AIです。与えられた指示と入力に従い、要求されたJSONのみを出力してください。",
            user_prompt=user_prompt,
            schema=schema,
        )

    def set_attempt_capture(capture: Any | None) -> None:
        """Bind raw LLM capture to the immutable attempt currently being executed."""
        client._capture = capture

    task_runner.set_attempt_capture = set_attempt_capture  # type: ignore[attr-defined]
    return task_runner
