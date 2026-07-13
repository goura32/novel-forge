"""Production adapters for the first PNCA authoring task."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

from novel_forge.pnca.defaults import default_pnca_task_registry
from novel_forge.pnca.registry import PNCATaskExecutor
from novel_forge.prompts import PromptManager
from novel_forge.runtime import ArtifactReference, RunHandle, RunRepository

_SYSTEM_PROMPT = "あなたは小説執筆支援AIです。与えられた指示と入力に従い、要求されたJSONのみを出力してください。"


def stage_series_request(
    *,
    repository: RunRepository,
    run: RunHandle,
    slug: str,
    keywords: str,
    existing_slugs: tuple[str, ...],
) -> ArtifactReference:
    """Commit unmodified CLI planning intent before it reaches an LLM."""
    attempt = repository.start_attempt(
        run,
        task_id="pnca.series.request",
        phase="plan",
        reason="stage immutable series request",
    )
    return repository.commit_artifact(
        attempt,
        artifact_type="pnca.series.request",
        logical_key=f"pnca.series.request.{slug}",
        payload={"slug": slug, "keywords": keywords, "existing_slugs": list(existing_slugs)},
        payload_name="request.json",
    )


def make_pnca_task_executor(*, client: Any, manager: PromptManager | None = None) -> PNCATaskExecutor:
    """Build the production provider adapter from registered PNCA task resources."""
    prompt_manager = manager or PromptManager()
    schema = json.loads(
        (resources.files("novel_forge") / "resources" / "schemas" / "pnca_series_contract.json").read_text(
            encoding="utf-8"
        )
    )

    def provider(task_id: str, projection: dict[str, Any], operation_key: str) -> Any:
        if task_id != "pnca.series.contract":
            raise ValueError(f"production PNCA provider does not implement task: {task_id}")
        user_prompt = prompt_manager.render(
            "pnca_series_contract.md",
            {
                "request": json.dumps(projection["request"], ensure_ascii=False),
                "schema": json.dumps(schema, ensure_ascii=False, indent=2),
            },
        )
        return client.complete_json(
            kind=task_id,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=schema,
        )

    return PNCATaskExecutor(registry=default_pnca_task_registry(), provider=provider)
